// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// Foundry-style test (run with `forge test`)
// If Foundry isn't installed, use the Python test harness instead.

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";

contract CalibrationRegistryTest {
    CalibrationRegistry public reg;

    uint256 constant WAD = 1e18;

    function setUp() public {
        reg = new CalibrationRegistry();
    }

    // --- Weight computation matches weights.py ---

    function test_newAgent_getsBaseWeight() public view {
        // Unknown agent → BASE_WEIGHT
        uint256 w = reg.computeWeight(address(0x1));
        require(w == WAD, "should be BASE_WEIGHT");
    }

    function test_fewPredictions_getsBaseWeight() public {
        reg.seedBrier(address(0x1), 0.10e18, 15);  // n=15 < MIN_PREDICTIONS=20
        uint256 w = reg.computeWeight(address(0x1));
        require(w == WAD, "should be BASE_WEIGHT for n < 20");
    }

    function test_perfectBrier_highWeight() public {
        // brier = 0.0, n = 100
        reg.seedBrier(address(0x1), 0, 100);
        uint256 w = reg.computeWeight(address(0x1));
        // raw = WAD^2 / (0 + EPSILON) = 1e36 / 1e15 = 1e21 = 1000 WAD
        // confidence = min(WAD, 100*WAD/100) = WAD
        // weight = 1000 * WAD = 1000e18
        require(w == 1000e18, "perfect brier should give 1000 WAD weight");
    }

    function test_midBrier_scaledWeight() public {
        // brier = 0.25, n = 100
        reg.seedBrier(address(0x1), 0.25e18, 100);
        uint256 w = reg.computeWeight(address(0x1));
        // raw = 1e36 / (0.25e18 + 1e15) = 1e36 / 251e15 ≈ 3.984e18
        // confidence = WAD (n=100 = CONFIDENCE_THRESHOLD)
        // weight ≈ 3.984e18
        // Python: 1/(0.25+0.001) = 3.984...
        require(w > 3.98e18 && w < 3.99e18, "mid brier weight out of range");
    }

    function test_confidenceScaling() public {
        // brier = 0.10, n = 50 (half of CONFIDENCE_THRESHOLD)
        reg.seedBrier(address(0x1), 0.10e18, 50);
        uint256 w = reg.computeWeight(address(0x1));
        // raw = 1e36 / (0.10e18 + 1e15) = 1e36 / 101e15 ≈ 9.9009e18
        // confidence = 50 * WAD / 100 = 0.5 * WAD
        // weight = raw * 0.5 ≈ 4.950e18
        require(w > 4.9e18 && w < 5.0e18, "confidence scaling off");
    }

    // --- Incremental Brier update ---

    function test_updateBrier_firstPrediction() public {
        // prediction = 0.8 (YES), outcome = YES (1.0)
        // brier_term = (0.8 - 1.0)^2 = 0.04
        reg.updateBrier(address(0x1), 0.8e18, WAD);
        (uint256 brier, uint256 n, , ) = reg.getAgent(address(0x1));
        require(n == 1, "n should be 1");
        // 0.04 in WAD = 0.04e18 = 4e16
        require(brier == 4e16, "brier should be 0.04 WAD");
    }

    function test_updateBrier_runningAverage() public {
        // First: prediction=0.8, outcome=YES → brier=0.04
        reg.updateBrier(address(0x1), 0.8e18, WAD);
        // Second: prediction=0.3, outcome=NO → brier_term=(0.3-0)^2 = 0.09
        reg.updateBrier(address(0x1), 0.3e18, 0);
        (uint256 brier, uint256 n, , ) = reg.getAgent(address(0x1));
        require(n == 2, "n should be 2");
        // running avg = (0.04 + 0.09) / 2 = 0.065 = 65e15
        require(brier == 65e15, "running average brier should be 0.065 WAD");
    }

    function test_updateBrier_wrongPrediction() public {
        // prediction=0.9 YES, outcome=NO → (0.9-0)^2 = 0.81
        reg.updateBrier(address(0x1), 0.9e18, 0);
        (uint256 brier, , , ) = reg.getAgent(address(0x1));
        require(brier == 81e16, "brier should be 0.81 WAD");
    }

    // --- Batch seed ---

    function test_seedBrierBatch() public {
        address[] memory addrs = new address[](2);
        addrs[0] = address(0x1);
        addrs[1] = address(0x2);
        uint256[] memory briers = new uint256[](2);
        briers[0] = 0.10e18;
        briers[1] = 0.25e18;
        uint256[] memory ns = new uint256[](2);
        ns[0] = 220;
        ns[1] = 140;
        reg.seedBrierBatch(addrs, briers, ns);

        (uint256 b1, uint256 n1, , ) = reg.getAgent(address(0x1));
        (uint256 b2, uint256 n2, , ) = reg.getAgent(address(0x2));
        require(b1 == 0.10e18 && n1 == 220, "agent 1 seed failed");
        require(b2 == 0.25e18 && n2 == 140, "agent 2 seed failed");
        require(reg.agentCount() == 2, "agent count should be 2");
    }

    // --- Batch weight computation ---

    function test_computeWeightsBatch() public {
        reg.seedBrier(address(0x1), 0.10e18, 220);
        reg.seedBrier(address(0x2), 0.18e18, 140);

        address[] memory addrs = new address[](3);
        addrs[0] = address(0x1);
        addrs[1] = address(0x2);
        addrs[2] = address(0x3);  // unregistered

        uint256[] memory ws = reg.computeWeights(addrs);
        require(ws.length == 3, "should return 3 weights");
        require(ws[2] == WAD, "unregistered agent should get BASE_WEIGHT");
        require(ws[0] > ws[1], "better calibrated agent should have higher weight");
    }

    // --- Access control ---

    function test_seedBrier_requiresBrier_lteMAX() public {
        // Should revert if brier > MAX_BRIER
        try reg.seedBrier(address(0x1), WAD + 1, 10) {
            revert("should have reverted");
        } catch {}
    }

    function test_updateBrier_requiresPrediction_lteWAD() public {
        try reg.updateBrier(address(0x1), WAD + 1, 0) {
            revert("should have reverted");
        } catch {}
    }

    function test_updateBrier_requiresBinaryOutcome() public {
        // outcome must be 0 or WAD
        try reg.updateBrier(address(0x1), 0.5e18, 0.5e18) {
            revert("should have reverted");
        } catch {}
    }
}
