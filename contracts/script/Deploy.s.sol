// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title DeploySwarmOracle
 * @notice Foundry deployment script for the full Swarm Oracle contract suite.
 *
 *         Usage:
 *           forge script script/Deploy.s.sol:DeploySwarmOracle \
 *               --rpc-url $BASE_SEPOLIA_RPC \
 *               --private-key $DEPLOYER_KEY \
 *               --broadcast \
 *               -vvvv
 *
 *         With Basescan verification (optional):
 *           forge script script/Deploy.s.sol:DeploySwarmOracle \
 *               --rpc-url $BASE_SEPOLIA_RPC \
 *               --private-key $DEPLOYER_KEY \
 *               --broadcast \
 *               --verify \
 *               --etherscan-api-key $BASESCAN_API_KEY \
 *               -vvvv
 *
 *         Deploys (in order):
 *           1. CalibrationRegistry — stores agent Brier scores + computes weights
 *           2. SwarmConsensus — aggregates votes using registry weights
 *           3. RewardDistribution — splits ETH reward pools among agents
 *           4. AgentIdentity — soulbound ERC-721 for agent reputation
 *           5. Seeds 3 mock agents with Brier scores + mints identity tokens
 *
 * @dev Uses an inline Vm interface so forge-std is not required as a dependency.
 *      The cheatcode address (0x7109709E...) is the canonical Foundry hevm address.
 */

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";
import {SwarmConsensus} from "../src/SwarmConsensus.sol";
import {RewardDistribution} from "../src/RewardDistribution.sol";
import {AgentIdentity} from "../src/AgentIdentity.sol";

// ---------------------------------------------------------------------------
// Minimal Vm interface — avoids forge-std dependency while enabling broadcast
// ---------------------------------------------------------------------------
interface Vm {
    function startBroadcast() external;
    function startBroadcast(address signer) external;
    function stopBroadcast() external;
}

// Canonical Foundry hevm cheat code address (same across all EVM forks)
address constant VM_ADDR = address(uint160(uint256(keccak256("hevm cheat code"))));

// ---------------------------------------------------------------------------
// Deployment script
// ---------------------------------------------------------------------------
contract DeploySwarmOracle {
    /// @notice Emitted once per deployment so forge `-vvvv` prints all addresses.
    event Deployed(
        address indexed calibrationRegistry,
        address indexed swarmConsensus,
        address indexed rewardDistribution,
        address agentIdentity
    );

    /// @dev Public slots so `forge inspect` and block explorers can read them.
    address public calibrationRegistry;
    address public swarmConsensus;
    address public rewardDistribution;
    address public agentIdentity;

    function run() external {
        Vm vm = Vm(VM_ADDR);

        // ── 1. Start broadcasting — all new() calls below send real txns ──────
        vm.startBroadcast();

        // ── 2. Deploy core contracts ──────────────────────────────────────────
        CalibrationRegistry registry = new CalibrationRegistry();
        SwarmConsensus consensus     = new SwarmConsensus(address(registry));
        RewardDistribution rewards   = new RewardDistribution(
            address(registry),
            address(consensus)
        );
        AgentIdentity identity       = new AgentIdentity(address(registry));

        // ── 3. Seed 3 demo agents (mirrors swarm_oracle/weights.py defaults) ──
        //    agent-oracle:    brier=0.10, n=220  (best calibrated)
        //    agent-reliable:  brier=0.18, n=140  (solid performer)
        //    agent-novice:    brier=0.25, n=25   (learning)
        address agentOracle   = address(0x0001);
        address agentReliable = address(0x0002);
        address agentNovice   = address(0x0003);

        address[] memory agents = new address[](3);
        agents[0] = agentOracle;
        agents[1] = agentReliable;
        agents[2] = agentNovice;

        uint256[] memory briers = new uint256[](3);
        briers[0] = 0.10e18;
        briers[1] = 0.18e18;
        briers[2] = 0.25e18;

        uint256[] memory ns = new uint256[](3);
        ns[0] = 220;
        ns[1] = 140;
        ns[2] = 25;

        registry.seedBrierBatch(agents, briers, ns);

        // ── 4. Grant roles ────────────────────────────────────────────────────
        registry.setUpdater(address(consensus), true);

        // ── 5. Mint soulbound identity tokens ─────────────────────────────────
        string[] memory labels = new string[](3);
        labels[0] = "agent-oracle";
        labels[1] = "agent-reliable";
        labels[2] = "agent-novice";

        string[] memory uris = new string[](3);
        uris[0] = "";
        uris[1] = "";
        uris[2] = "";

        identity.mintBatch(agents, labels, uris);

        // ── 6. Stop broadcasting ──────────────────────────────────────────────
        vm.stopBroadcast();

        // ── 7. Store addresses (visible in forge output + block explorer) ─────
        calibrationRegistry = address(registry);
        swarmConsensus      = address(consensus);
        rewardDistribution  = address(rewards);
        agentIdentity       = address(identity);

        emit Deployed(
            address(registry),
            address(consensus),
            address(rewards),
            address(identity)
        );
    }
}
