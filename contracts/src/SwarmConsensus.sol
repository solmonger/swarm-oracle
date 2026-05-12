// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CalibrationRegistry} from "./CalibrationRegistry.sol";

/**
 * @title SwarmConsensus
 * @notice On-chain consensus aggregation for the Swarm Oracle protocol.
 *         Mirrors swarm_oracle/consensus.py — calibration-weighted linear opinion pool.
 *
 *         Flow:
 *           1. Oracle updater submits agent votes for a question.
 *           2. Contract reads weights from CalibrationRegistry.
 *           3. Computes weighted consensus probability + decision (YES/NO/DISPUTE).
 *           4. Emits QuestionResolved event.
 *
 * @dev    All probabilities are in WAD (1e18 = 1.0 = 100%).
 */
contract SwarmConsensus {
    // -----------------------------------------------------------------------
    // Constants — match consensus.py
    // -----------------------------------------------------------------------

    uint256 public constant WAD = 1e18;
    uint256 public constant YES_THRESHOLD = 85e16;          // 0.85
    uint256 public constant NO_THRESHOLD = 15e16;            // 0.15
    uint256 public constant VARIANCE_THRESHOLD_SQ = 4e34;    // 0.20^2 in WAD^2 (for comparison without sqrt)

    // -----------------------------------------------------------------------
    // Types
    // -----------------------------------------------------------------------

    enum Decision { PENDING, YES, NO, DISPUTE }

    struct Vote {
        address agent;
        uint256 probability;   // P(YES) in WAD
    }

    struct QuestionResult {
        bytes32     questionId;
        uint256     consensusProbability;  // weighted mean, WAD
        Decision    decision;
        uint256     weightedVariance;      // WAD^2 (compare with VARIANCE_THRESHOLD_SQ)
        uint256     numVotes;
        uint256     resolvedAt;            // block.timestamp
        bool        resolved;
    }

    // -----------------------------------------------------------------------
    // Storage
    // -----------------------------------------------------------------------

    CalibrationRegistry public immutable REGISTRY;
    address public owner;
    mapping(address => bool) public submitters;

    mapping(bytes32 => QuestionResult) public results;
    mapping(bytes32 => Vote[]) internal questionVotes;   // preserved for audit
    bytes32[] public questionIds;
    uint256 public questionCount;

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event QuestionResolved(
        bytes32 indexed questionId,
        uint256 consensusProbability,
        Decision decision,
        uint256 numVotes
    );
    event VotesSubmitted(bytes32 indexed questionId, uint256 numVotes);
    event SubmitterSet(address indexed submitter, bool allowed);

    // -----------------------------------------------------------------------
    // Modifiers
    // -----------------------------------------------------------------------

    modifier onlyOwner() {
        _onlyOwner();
        _;
    }

    modifier onlySubmitter() {
        _onlySubmitter();
        _;
    }

    function _onlyOwner() internal view {
        require(msg.sender == owner, "SwarmConsensus: not owner");
    }

    function _onlySubmitter() internal view {
        require(
            submitters[msg.sender] || msg.sender == owner,
            "SwarmConsensus: not submitter"
        );
    }

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor(address _registry) {
        REGISTRY = CalibrationRegistry(_registry);
        owner = msg.sender;
        submitters[msg.sender] = true;
    }

    // -----------------------------------------------------------------------
    // Admin
    // -----------------------------------------------------------------------

    function setSubmitter(address submitter, bool allowed) external onlyOwner {
        submitters[submitter] = allowed;
        emit SubmitterSet(submitter, allowed);
    }

    // -----------------------------------------------------------------------
    // Core — submit votes + resolve consensus
    // -----------------------------------------------------------------------

    /**
     * @notice Submit agent votes for a question and compute consensus.
     * @param questionId  Unique identifier (e.g. keccak256 of question text).
     * @param agentAddrs  Ordered list of agent addresses.
     * @param probabilities  Each agent's P(YES) in WAD, same order.
     *
     * Requirements:
     *   - Question must not already be resolved.
     *   - At least 1 vote.
     *   - Arrays must be same length.
     *   - Each probability ≤ WAD.
     */
    function submitVotes(
        bytes32 questionId,
        address[] calldata agentAddrs,
        uint256[] calldata probabilities
    ) external onlySubmitter {
        require(!results[questionId].resolved, "SwarmConsensus: already resolved");
        require(agentAddrs.length > 0, "SwarmConsensus: no votes");
        require(
            agentAddrs.length == probabilities.length,
            "SwarmConsensus: length mismatch"
        );

        uint256 n = agentAddrs.length;

        // --- Fetch weights from CalibrationRegistry ---
        uint256[] memory weights = REGISTRY.computeWeights(agentAddrs);

        // --- Compute total weight ---
        uint256 totalWeight = 0;
        for (uint256 i = 0; i < n; i++) {
            require(probabilities[i] <= WAD, "SwarmConsensus: prob > 1.0");
            totalWeight += weights[i];
        }

        // --- Weighted mean ---
        uint256 consensusProb;
        if (totalWeight == 0) {
            // Degenerate: equal vote
            uint256 sum = 0;
            for (uint256 i = 0; i < n; i++) {
                sum += probabilities[i];
            }
            consensusProb = sum / n;
        } else {
            uint256 weightedSum = 0;
            for (uint256 i = 0; i < n; i++) {
                weightedSum += (probabilities[i] * weights[i]) / WAD;
            }
            // weightedSum is in WAD because each term = (WAD * WAD_weight) / WAD
            // Normalize: consensusProb = weightedSum * WAD / totalWeight
            consensusProb = (weightedSum * WAD) / totalWeight;
        }

        // --- Weighted variance (WAD^2 scale) ---
        uint256 weightedVariance = _weightedVariance(
            probabilities, weights, totalWeight, consensusProb, n
        );

        // --- Decision ---
        Decision decision = _classify(consensusProb, weightedVariance);

        // --- Store votes for audit ---
        delete questionVotes[questionId];
        for (uint256 i = 0; i < n; i++) {
            questionVotes[questionId].push(Vote({
                agent: agentAddrs[i],
                probability: probabilities[i]
            }));
        }

        // --- Store result ---
        if (!results[questionId].resolved && results[questionId].resolvedAt == 0) {
            questionIds.push(questionId);
            questionCount++;
        }

        results[questionId] = QuestionResult({
            questionId: questionId,
            consensusProbability: consensusProb,
            decision: decision,
            weightedVariance: weightedVariance,
            numVotes: n,
            resolvedAt: block.timestamp,
            resolved: true
        });

        emit VotesSubmitted(questionId, n);
        emit QuestionResolved(questionId, consensusProb, decision, n);
    }

    // -----------------------------------------------------------------------
    // Read
    // -----------------------------------------------------------------------

    function getResult(bytes32 questionId)
        external
        view
        returns (
            uint256 consensusProbability,
            Decision decision,
            uint256 weightedVariance,
            uint256 numVotes,
            uint256 resolvedAt,
            bool resolved
        )
    {
        QuestionResult storage r = results[questionId];
        return (
            r.consensusProbability,
            r.decision,
            r.weightedVariance,
            r.numVotes,
            r.resolvedAt,
            r.resolved
        );
    }

    function getVotes(bytes32 questionId)
        external
        view
        returns (Vote[] memory)
    {
        return questionVotes[questionId];
    }

    // -----------------------------------------------------------------------
    // Internal
    // -----------------------------------------------------------------------

    /**
     * @dev Weighted population variance in WAD^2.
     *      Var = Σ(w_i * (p_i - mean)^2) / Σw_i
     *      where w_i is raw weight and mean is the consensus probability.
     */
    function _weightedVariance(
        uint256[] calldata probs,
        uint256[] memory weights,
        uint256 totalWeight,
        uint256 mean,
        uint256 n
    ) internal pure returns (uint256) {
        if (totalWeight == 0 || n <= 1) return 0;

        uint256 varSum = 0;
        for (uint256 i = 0; i < n; i++) {
            uint256 diff;
            if (probs[i] >= mean) {
                diff = probs[i] - mean;
            } else {
                diff = mean - probs[i];
            }
            // diff is WAD; diff^2 is WAD^2; scale by weight (WAD) / WAD → WAD^2
            uint256 term = (diff * diff * weights[i]) / WAD;
            varSum += term;
        }
        // varSum is WAD^2 * WAD (from weight multiplication), divide by totalWeight (WAD)
        return varSum / totalWeight;
    }

    /**
     * @dev Map (probability, variance) → Decision.
     *      Mirrors _classify in consensus.py.
     *      Variance comparison uses squared threshold to avoid on-chain sqrt.
     */
    function _classify(uint256 prob, uint256 variance)
        internal
        pure
        returns (Decision)
    {
        // Check variance first (high disagreement → DISPUTE)
        if (variance > VARIANCE_THRESHOLD_SQ) {
            return Decision.DISPUTE;
        }

        if (prob >= YES_THRESHOLD) {
            return Decision.YES;
        }
        if (prob <= NO_THRESHOLD) {
            return Decision.NO;
        }

        return Decision.DISPUTE;
    }
}
