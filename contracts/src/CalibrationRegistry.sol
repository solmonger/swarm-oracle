// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title CalibrationRegistry
 * @notice On-chain mirror of swarm_oracle/weights.py — stores per-agent Brier
 *         scores and computes calibration weights in 18-decimal fixed-point.
 *
 *         Formula (from design doc):
 *           if numPredictions < MIN_PREDICTIONS → weight = BASE_WEIGHT
 *           else → raw = WAD / (brier + EPSILON)
 *                  confidence = min(WAD, numPredictions * WAD / CONFIDENCE_THRESHOLD)
 *                  weight = raw * confidence / WAD
 *
 * @dev    All Brier scores and weights are stored / returned as WAD (1e18 = 1.0).
 *         Brier score ∈ [0, 1e18]. Predictions and outcomes ∈ [0, 1e18].
 */
contract CalibrationRegistry {
    // -----------------------------------------------------------------------
    // Constants — match weights.py exactly
    // -----------------------------------------------------------------------

    uint256 public constant WAD = 1e18;
    uint256 public constant BASE_WEIGHT = 1e18;              // 1.0
    uint256 public constant MIN_PREDICTIONS = 20;
    uint256 public constant CONFIDENCE_THRESHOLD = 100;
    uint256 public constant EPSILON = 1e15;                   // 0.001 in WAD
    uint256 public constant MAX_BRIER = 1e18;                 // 1.0

    // -----------------------------------------------------------------------
    // Storage
    // -----------------------------------------------------------------------

    struct AgentRecord {
        uint256 brierScore;       // Running-average Brier in WAD
        uint256 numPredictions;   // Total predictions scored
        uint256 lastUpdated;      // block.timestamp of last update
        bool    registered;       // true once the agent has been seeded or updated
    }

    mapping(address => AgentRecord) public agents;
    address[] public agentList;          // enumerable for off-chain reads
    uint256 public agentCount;

    address public owner;
    mapping(address => bool) public updaters;   // ORACLE_UPDATER role

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event AgentRegistered(address indexed agent);
    event BrierUpdated(
        address indexed agent,
        uint256 prediction,
        uint256 outcome,
        uint256 newBrier,
        uint256 newN
    );
    event BrierSeeded(address indexed agent, uint256 brier, uint256 n);
    event UpdaterSet(address indexed updater, bool allowed);
    event OwnerTransferred(address indexed oldOwner, address indexed newOwner);

    // -----------------------------------------------------------------------
    // Modifiers
    // -----------------------------------------------------------------------

    modifier onlyOwner() {
        require(msg.sender == owner, "CalibrationRegistry: not owner");
        _;
    }

    modifier onlyUpdater() {
        require(
            updaters[msg.sender] || msg.sender == owner,
            "CalibrationRegistry: not updater"
        );
        _;
    }

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor() {
        owner = msg.sender;
        updaters[msg.sender] = true;
    }

    // -----------------------------------------------------------------------
    // Admin
    // -----------------------------------------------------------------------

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "CalibrationRegistry: zero address");
        emit OwnerTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setUpdater(address updater, bool allowed) external onlyOwner {
        updaters[updater] = allowed;
        emit UpdaterSet(updater, allowed);
    }

    // -----------------------------------------------------------------------
    // Write — seed from off-chain history
    // -----------------------------------------------------------------------

    /**
     * @notice Seed (or overwrite) an agent's Brier record from off-chain data.
     * @param agent   Agent address (or deterministic identity hash cast to address).
     * @param brier   Running-average Brier score in WAD (≤ MAX_BRIER).
     * @param n       Number of predictions backing this average.
     */
    function seedBrier(address agent, uint256 brier, uint256 n)
        external
        onlyUpdater
    {
        require(brier <= MAX_BRIER, "CalibrationRegistry: brier > 1.0");
        _ensureRegistered(agent);
        agents[agent].brierScore = brier;
        agents[agent].numPredictions = n;
        agents[agent].lastUpdated = block.timestamp;
        emit BrierSeeded(agent, brier, n);
    }

    /**
     * @notice Batch-seed multiple agents in one transaction.
     */
    function seedBrierBatch(
        address[] calldata agentAddrs,
        uint256[] calldata briers,
        uint256[] calldata ns
    ) external onlyUpdater {
        require(
            agentAddrs.length == briers.length && briers.length == ns.length,
            "CalibrationRegistry: length mismatch"
        );
        for (uint256 i = 0; i < agentAddrs.length; i++) {
            require(briers[i] <= MAX_BRIER, "CalibrationRegistry: brier > 1.0");
            _ensureRegistered(agentAddrs[i]);
            agents[agentAddrs[i]].brierScore = briers[i];
            agents[agentAddrs[i]].numPredictions = ns[i];
            agents[agentAddrs[i]].lastUpdated = block.timestamp;
            emit BrierSeeded(agentAddrs[i], briers[i], ns[i]);
        }
    }

    // -----------------------------------------------------------------------
    // Write — incremental update (mirrors update_brier_running_average)
    // -----------------------------------------------------------------------

    /**
     * @notice Update an agent's running-average Brier with a new (prediction, outcome) pair.
     * @param agent      Agent address.
     * @param prediction Agent's probability estimate for YES, in WAD (0..1e18).
     * @param outcome    Actual outcome — 0 (NO) or WAD (YES).
     */
    function updateBrier(address agent, uint256 prediction, uint256 outcome)
        external
        onlyUpdater
    {
        require(prediction <= WAD, "CalibrationRegistry: prediction > 1.0");
        require(outcome == 0 || outcome == WAD, "CalibrationRegistry: outcome must be 0 or WAD");

        _ensureRegistered(agent);

        AgentRecord storage rec = agents[agent];

        // new_brier_term = (prediction - outcome)^2   (in WAD)
        uint256 diff;
        if (prediction >= outcome) {
            diff = prediction - outcome;
        } else {
            diff = outcome - prediction;
        }
        // diff is in WAD; diff^2 / WAD gives WAD-scaled squared error
        uint256 brierTerm = (diff * diff) / WAD;

        if (rec.numPredictions == 0) {
            rec.brierScore = brierTerm;
            rec.numPredictions = 1;
        } else {
            // running average: new = (old * n + term) / (n + 1)
            uint256 n = rec.numPredictions;
            rec.brierScore = (rec.brierScore * n + brierTerm) / (n + 1);
            rec.numPredictions = n + 1;
        }
        rec.lastUpdated = block.timestamp;

        emit BrierUpdated(agent, prediction, outcome, rec.brierScore, rec.numPredictions);
    }

    // -----------------------------------------------------------------------
    // Read — compute weight (mirrors compute_weight in weights.py)
    // -----------------------------------------------------------------------

    /**
     * @notice Compute calibration weight for an agent.
     * @return weight Weight in WAD. Reverts if agent not registered.
     */
    function computeWeight(address agent) external view returns (uint256 weight) {
        AgentRecord storage rec = agents[agent];
        if (!rec.registered) {
            return BASE_WEIGHT;   // unknown agents get base weight
        }
        return _computeWeight(rec.brierScore, rec.numPredictions);
    }

    /**
     * @notice Batch compute weights for a list of agents (for consensus aggregation).
     */
    function computeWeights(address[] calldata agentAddrs)
        external
        view
        returns (uint256[] memory weights)
    {
        weights = new uint256[](agentAddrs.length);
        for (uint256 i = 0; i < agentAddrs.length; i++) {
            AgentRecord storage rec = agents[agentAddrs[i]];
            if (!rec.registered) {
                weights[i] = BASE_WEIGHT;
            } else {
                weights[i] = _computeWeight(rec.brierScore, rec.numPredictions);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Read — getters
    // -----------------------------------------------------------------------

    function getAgent(address agent)
        external
        view
        returns (uint256 brierScore, uint256 numPredictions, uint256 lastUpdated, bool registered)
    {
        AgentRecord storage rec = agents[agent];
        return (rec.brierScore, rec.numPredictions, rec.lastUpdated, rec.registered);
    }

    function getAgentList() external view returns (address[] memory) {
        return agentList;
    }

    // -----------------------------------------------------------------------
    // Internal
    // -----------------------------------------------------------------------

    function _ensureRegistered(address agent) internal {
        if (!agents[agent].registered) {
            agents[agent].registered = true;
            agentList.push(agent);
            agentCount++;
            emit AgentRegistered(agent);
        }
    }

    function _computeWeight(uint256 brier, uint256 n)
        internal
        pure
        returns (uint256)
    {
        if (n < MIN_PREDICTIONS) {
            return BASE_WEIGHT;
        }

        // raw = WAD / (brier + EPSILON)
        // Both brier and EPSILON are in WAD, so (brier + EPSILON) is WAD-scaled.
        // We want raw to be WAD-scaled: raw = WAD * WAD / (brier + EPSILON)
        uint256 raw = (WAD * WAD) / (brier + EPSILON);

        // confidence = min(WAD, n * WAD / CONFIDENCE_THRESHOLD)
        uint256 confidence = (n * WAD) / CONFIDENCE_THRESHOLD;
        if (confidence > WAD) {
            confidence = WAD;
        }

        // weight = raw * confidence / WAD
        return (raw * confidence) / WAD;
    }
}
