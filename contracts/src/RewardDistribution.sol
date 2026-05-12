// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CalibrationRegistry} from "./CalibrationRegistry.sol";
import {SwarmConsensus} from "./SwarmConsensus.sol";

/**
 * @title RewardDistribution
 * @notice Distributes ETH rewards to agents proportional to their calibration
 *         weight and prediction accuracy on resolved questions.
 *
 *         Flow:
 *           1. Anyone funds a question's reward pool via `fundQuestion()`.
 *           2. After SwarmConsensus resolves the question, the owner calls
 *              `distributeRewards()` to split the pool among participating agents.
 *           3. Each agent receives: pool * (agent_weight / total_weight) *
 *              accuracy_bonus, where accuracy_bonus rewards agents whose
 *              vote aligned with consensus.
 *           4. Agents call `withdraw()` to pull their accumulated balance.
 *
 * @dev    Pull-payment pattern: rewards accumulate in `balances`, agents withdraw.
 *         This avoids reentrancy and failed-send issues.
 */
contract RewardDistribution {
    // -----------------------------------------------------------------------
    // Constants
    // -----------------------------------------------------------------------

    uint256 public constant WAD = 1e18;

    /// @notice Fraction of pool reserved for accuracy bonus (30%).
    uint256 public constant ACCURACY_POOL_FRACTION = 30e16;  // 0.30 WAD

    /// @notice Fraction of pool distributed by weight alone (70%).
    uint256 public constant BASE_POOL_FRACTION = 70e16;  // 0.70 WAD

    // -----------------------------------------------------------------------
    // Immutables & state
    // -----------------------------------------------------------------------

    CalibrationRegistry public immutable REGISTRY;
    SwarmConsensus public immutable CONSENSUS;

    address public owner;
    mapping(address => bool) public distributors;

    /// @notice ETH reward pool per question.
    mapping(bytes32 => uint256) public questionPools;

    /// @notice Whether rewards have been distributed for a question.
    mapping(bytes32 => bool) public distributed;

    /// @notice Accumulated withdrawable balance per agent.
    mapping(address => uint256) public balances;

    /// @notice Total rewards distributed across all questions.
    uint256 public totalDistributed;

    /// @notice Per-question distribution record for transparency.
    struct DistributionRecord {
        bytes32 questionId;
        uint256 poolSize;
        uint256 numRecipients;
        uint256 distributedAt;
    }

    mapping(bytes32 => DistributionRecord) public distributions;
    bytes32[] public distributionHistory;

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event QuestionFunded(bytes32 indexed questionId, address indexed funder, uint256 amount);
    event RewardsDistributed(bytes32 indexed questionId, uint256 poolSize, uint256 numRecipients);
    event AgentRewarded(bytes32 indexed questionId, address indexed agent, uint256 amount);
    event Withdrawn(address indexed agent, uint256 amount);
    event DistributorSet(address indexed distributor, bool allowed);

    // -----------------------------------------------------------------------
    // Modifiers
    // -----------------------------------------------------------------------

    modifier onlyOwner() {
        _onlyOwner();
        _;
    }

    modifier onlyDistributor() {
        _onlyDistributor();
        _;
    }

    function _onlyOwner() internal view {
        require(msg.sender == owner, "RewardDistribution: not owner");
    }

    function _onlyDistributor() internal view {
        require(
            distributors[msg.sender] || msg.sender == owner,
            "RewardDistribution: not distributor"
        );
    }

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor(address _registry, address _consensus) {
        REGISTRY = CalibrationRegistry(_registry);
        CONSENSUS = SwarmConsensus(_consensus);
        owner = msg.sender;
        distributors[msg.sender] = true;
    }

    // -----------------------------------------------------------------------
    // Admin
    // -----------------------------------------------------------------------

    function setDistributor(address distributor, bool allowed) external onlyOwner {
        distributors[distributor] = allowed;
        emit DistributorSet(distributor, allowed);
    }

    // -----------------------------------------------------------------------
    // Fund — deposit ETH into a question's reward pool
    // -----------------------------------------------------------------------

    /**
     * @notice Fund a question's reward pool. Can be called multiple times
     *         to top up the pool before distribution.
     * @param questionId  The question identifier (must match SwarmConsensus).
     */
    function fundQuestion(bytes32 questionId) external payable {
        require(msg.value > 0, "RewardDistribution: zero value");
        require(!distributed[questionId], "RewardDistribution: already distributed");
        questionPools[questionId] += msg.value;
        emit QuestionFunded(questionId, msg.sender, msg.value);
    }

    // -----------------------------------------------------------------------
    // Distribute — split pool among agents after consensus resolution
    // -----------------------------------------------------------------------

    /**
     * @notice Distribute rewards for a resolved question.
     *
     * @dev    Two-part distribution:
     *         1. BASE_POOL (70%): split proportional to calibration weights.
     *         2. ACCURACY_POOL (30%): split among agents whose vote aligned
     *            with the consensus decision, weighted by calibration.
     *
     *         If no agents voted correctly (e.g., DISPUTE), the accuracy pool
     *         is distributed entirely by weight.
     *
     * @param questionId  Must be resolved in SwarmConsensus and have a pool > 0.
     */
    function distributeRewards(bytes32 questionId) external onlyDistributor {
        require(!distributed[questionId], "RewardDistribution: already distributed");
        uint256 pool = questionPools[questionId];
        require(pool > 0, "RewardDistribution: no pool");

        // Read consensus result
        (
            uint256 consensusProb,
            SwarmConsensus.Decision decision,
            ,  // weightedVariance
            uint256 numVotes,
            ,  // resolvedAt
            bool resolved
        ) = CONSENSUS.getResult(questionId);
        require(resolved, "RewardDistribution: not resolved");
        require(numVotes > 0, "RewardDistribution: no votes");

        // Get votes
        SwarmConsensus.Vote[] memory votes = CONSENSUS.getVotes(questionId);

        // Fetch weights from registry
        address[] memory agentAddrs = new address[](votes.length);
        for (uint256 i = 0; i < votes.length; i++) {
            agentAddrs[i] = votes[i].agent;
        }
        uint256[] memory weights = REGISTRY.computeWeights(agentAddrs);

        // Compute total weight
        uint256 totalWeight = 0;
        for (uint256 i = 0; i < weights.length; i++) {
            totalWeight += weights[i];
        }
        require(totalWeight > 0, "RewardDistribution: zero total weight");

        // Determine which agents voted "correctly" (aligned with decision)
        bool[] memory correct = new bool[](votes.length);
        uint256 correctWeight = 0;

        if (decision == SwarmConsensus.Decision.YES || decision == SwarmConsensus.Decision.NO) {
            for (uint256 i = 0; i < votes.length; i++) {
                // More nuanced: reward agents closer to consensus
                // "Correct" = within 0.15 of consensus probability
                uint256 diff;
                if (votes[i].probability >= consensusProb) {
                    diff = votes[i].probability - consensusProb;
                } else {
                    diff = consensusProb - votes[i].probability;
                }
                // Consider aligned if within 15% of consensus
                if (diff <= 15e16) {  // 0.15 WAD
                    correct[i] = true;
                    correctWeight += weights[i];
                }
            }
        }
        // --- Split pool & credit rewards (extracted to avoid stack-too-deep) ---
        uint256 basePool = (pool * BASE_POOL_FRACTION) / WAD;
        uint256 accuracyPool = pool - basePool;  // avoids rounding dust

        uint256 totalCredited = _creditRewards(
            questionId, agentAddrs, weights, correct,
            totalWeight, correctWeight, basePool, accuracyPool
        );

        // Mark as distributed
        distributed[questionId] = true;
        totalDistributed += totalCredited;

        distributions[questionId] = DistributionRecord({
            questionId: questionId,
            poolSize: pool,
            numRecipients: votes.length,
            distributedAt: block.timestamp
        });
        distributionHistory.push(questionId);

        emit RewardsDistributed(questionId, pool, votes.length);
    }

    // -----------------------------------------------------------------------
    // Internal — reward crediting (extracted to avoid stack-too-deep)
    // -----------------------------------------------------------------------

    function _creditRewards(
        bytes32 questionId,
        address[] memory agentAddrs,
        uint256[] memory weights,
        bool[] memory correct,
        uint256 totalWeight,
        uint256 correctWeight,
        uint256 basePool,
        uint256 accuracyPool
    ) internal returns (uint256 totalCredited) {
        bool hasCorrect = correctWeight > 0;

        for (uint256 i = 0; i < agentAddrs.length; i++) {
            uint256 reward = 0;

            // Base reward: proportional to weight
            reward += (basePool * weights[i]) / totalWeight;

            // Accuracy reward
            if (hasCorrect && correct[i]) {
                reward += (accuracyPool * weights[i]) / correctWeight;
            } else if (!hasCorrect) {
                // No correct agents → distribute accuracy pool by weight too
                reward += (accuracyPool * weights[i]) / totalWeight;
            }
            // else: agent was wrong and others were right → no accuracy bonus

            if (reward > 0) {
                balances[agentAddrs[i]] += reward;
                totalCredited += reward;
                emit AgentRewarded(questionId, agentAddrs[i], reward);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Withdraw — pull payment pattern
    // -----------------------------------------------------------------------

    /**
     * @notice Withdraw accumulated rewards.
     */
    function withdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "RewardDistribution: nothing to withdraw");

        balances[msg.sender] = 0;

        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "RewardDistribution: transfer failed");

        emit Withdrawn(msg.sender, amount);
    }

    /**
     * @notice Withdraw to a specific address (owner only, for agents without EOAs).
     */
    function withdrawFor(address agent, address payable recipient) external onlyOwner {
        uint256 amount = balances[agent];
        require(amount > 0, "RewardDistribution: nothing to withdraw");

        balances[agent] = 0;

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "RewardDistribution: transfer failed");

        emit Withdrawn(agent, amount);
    }

    // -----------------------------------------------------------------------
    // Read
    // -----------------------------------------------------------------------

    function getDistributionHistory() external view returns (bytes32[] memory) {
        return distributionHistory;
    }

    function getDistributionCount() external view returns (uint256) {
        return distributionHistory.length;
    }

    /// @notice Check contract's ETH balance (undistributed pools + unclaimed rewards).
    function totalBalance() external view returns (uint256) {
        return address(this).balance;
    }

    // Allow receiving ETH directly (for simple funding without specifying question)
    receive() external payable {}
}
