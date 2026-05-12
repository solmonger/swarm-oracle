// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title Deploy
 * @notice Foundry deployment script for the full Swarm Oracle contract suite.
 *
 *         Usage:
 *           forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC \
 *               --private-key $DEPLOYER_KEY --broadcast
 *
 *         Deploys:
 *           1. CalibrationRegistry — stores agent Brier scores + computes weights
 *           2. SwarmConsensus — aggregates votes using registry weights
 *           3. RewardDistribution — splits ETH reward pools among agents
 *           4. AgentIdentity — soulbound ERC-721 for agent reputation
 *           5. Seeds 3 mock agents with Brier scores + mints identity tokens
 */

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";
import {SwarmConsensus} from "../src/SwarmConsensus.sol";
import {RewardDistribution} from "../src/RewardDistribution.sol";
import {AgentIdentity} from "../src/AgentIdentity.sol";

contract Deploy {
    function run() external {
        // --- Deploy core contracts ---
        CalibrationRegistry registry = new CalibrationRegistry();
        SwarmConsensus consensus = new SwarmConsensus(address(registry));
        RewardDistribution rewards = new RewardDistribution(
            address(registry),
            address(consensus)
        );
        AgentIdentity identity = new AgentIdentity(address(registry));

        // --- Seed mock agents (matches swarm_oracle/weights.py mock_brier_history) ---
        // agent-oracle:   brier=0.10, n=220  (best calibrated)
        // agent-reliable:  brier=0.18, n=140  (solid performer)
        // agent-novice:    brier=0.25, n=25   (learning)

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

        // --- Grant roles ---
        // Consensus contract can call registry if extended
        registry.setUpdater(address(consensus), true);

        // --- Mint soulbound identity tokens ---
        string[] memory labels = new string[](3);
        labels[0] = "agent-oracle";
        labels[1] = "agent-reliable";
        labels[2] = "agent-novice";

        string[] memory uris = new string[](3);
        uris[0] = "";
        uris[1] = "";
        uris[2] = "";

        identity.mintBatch(agents, labels, uris);
    }
}
