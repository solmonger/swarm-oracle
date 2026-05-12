// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title Deploy
 * @notice Foundry deployment script for Swarm Oracle contracts.
 *
 *         Usage:
 *           forge script script/Deploy.s.sol --rpc-url $BASE_SEPOLIA_RPC \
 *               --private-key $DEPLOYER_KEY --broadcast
 *
 *         Deploys:
 *           1. CalibrationRegistry — stores agent Brier scores + computes weights
 *           2. SwarmConsensus — aggregates votes using registry weights
 *           3. Seeds 3 mock agents from the design doc
 */

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";
import {SwarmConsensus} from "../src/SwarmConsensus.sol";

contract Deploy {
    function run() external {
        // --- Deploy ---
        CalibrationRegistry registry = new CalibrationRegistry();
        SwarmConsensus consensus = new SwarmConsensus(address(registry));

        // --- Seed mock agents (matches swarm_oracle/weights.py mock_brier_history) ---
        // agent-oracle:   brier=0.10, n=220
        // agent-reliable:  brier=0.18, n=140
        // agent-novice:    brier=0.25, n=25

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

        // Grant consensus contract as updater (so it can call registry if extended)
        registry.setUpdater(address(consensus), true);
    }
}
