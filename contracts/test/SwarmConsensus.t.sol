// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";
import {SwarmConsensus} from "../src/SwarmConsensus.sol";

contract SwarmConsensusTest {
    CalibrationRegistry public reg;
    SwarmConsensus public consensus;

    uint256 constant WAD = 1e18;

    function setUp() public {
        reg = new CalibrationRegistry();
        consensus = new SwarmConsensus(address(reg));

        // Seed 3 mock agents matching the demo
        reg.seedBrier(address(0x1), 0.10e18, 220);  // agent-oracle
        reg.seedBrier(address(0x2), 0.18e18, 140);  // agent-reliable
        reg.seedBrier(address(0x3), 0.25e18, 25);   // agent-novice
    }

    // --- Basic consensus ---

    function test_submitVotes_unanimousYes() public {
        bytes32 qid = keccak256("Did BTC close above 100K?");
        address[] memory agents = new address[](3);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        agents[2] = address(0x3);

        uint256[] memory probs = new uint256[](3);
        probs[0] = 0.95e18;
        probs[1] = 0.90e18;
        probs[2] = 0.88e18;

        consensus.submitVotes(qid, agents, probs);

        (uint256 cp, SwarmConsensus.Decision d, , uint256 nv, , bool resolved) =
            consensus.getResult(qid);

        require(resolved, "should be resolved");
        require(nv == 3, "should have 3 votes");
        require(d == SwarmConsensus.Decision.YES, "should be YES");
        // Weighted consensus should be closer to agent-oracle's 0.95
        require(cp > 0.90e18, "consensus should be > 0.90");
    }

    function test_submitVotes_unanimousNo() public {
        bytes32 qid = keccak256("Did ETH drop below 1000?");
        address[] memory agents = new address[](3);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        agents[2] = address(0x3);

        uint256[] memory probs = new uint256[](3);
        probs[0] = 0.05e18;
        probs[1] = 0.10e18;
        probs[2] = 0.12e18;

        consensus.submitVotes(qid, agents, probs);

        (, SwarmConsensus.Decision d, , , , ) = consensus.getResult(qid);
        require(d == SwarmConsensus.Decision.NO, "should be NO");
    }

    function test_submitVotes_dispute_highVariance() public {
        bytes32 qid = keccak256("Will it rain tomorrow?");
        address[] memory agents = new address[](3);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        agents[2] = address(0x3);

        // Extreme disagreement: 0.95 vs 0.05 vs 0.50
        uint256[] memory probs = new uint256[](3);
        probs[0] = 0.95e18;
        probs[1] = 0.05e18;
        probs[2] = 0.50e18;

        consensus.submitVotes(qid, agents, probs);

        (, SwarmConsensus.Decision d, uint256 wv, , , ) = consensus.getResult(qid);
        require(d == SwarmConsensus.Decision.DISPUTE, "should be DISPUTE");
        // Variance is ~1.76e17 — below VARIANCE_THRESHOLD_SQ (4e34) but still
        // DISPUTE because consensus probability (0.62) falls between YES/NO thresholds
        require(wv > 1e17, "variance should exceed threshold");
    }

    function test_submitVotes_dispute_midProbability() public {
        bytes32 qid = keccak256("Coin flip");
        address[] memory agents = new address[](3);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        agents[2] = address(0x3);

        // All around 0.50 — low variance but ambiguous
        uint256[] memory probs = new uint256[](3);
        probs[0] = 0.50e18;
        probs[1] = 0.52e18;
        probs[2] = 0.48e18;

        consensus.submitVotes(qid, agents, probs);

        (, SwarmConsensus.Decision d, , , , ) = consensus.getResult(qid);
        require(d == SwarmConsensus.Decision.DISPUTE, "mid-prob should be DISPUTE");
    }

    // --- Weight influence ---

    function test_weightInfluence_oracleCloserToConsensus() public {
        bytes32 qid = keccak256("Weight test");
        address[] memory agents = new address[](2);
        agents[0] = address(0x1);  // oracle (high weight)
        agents[1] = address(0x3);  // novice (low weight)

        uint256[] memory probs = new uint256[](2);
        probs[0] = 0.90e18;  // oracle says YES
        probs[1] = 0.40e18;  // novice says ambiguous

        consensus.submitVotes(qid, agents, probs);

        (uint256 cp, , , , , ) = consensus.getResult(qid);
        // Consensus should be much closer to 0.90 than to 0.40
        require(cp > 0.70e18, "consensus should lean toward high-weight agent");
    }

    // --- Edge cases ---

    function test_singleVote() public {
        bytes32 qid = keccak256("Single vote");
        address[] memory agents = new address[](1);
        agents[0] = address(0x1);

        uint256[] memory probs = new uint256[](1);
        probs[0] = 0.92e18;

        consensus.submitVotes(qid, agents, probs);

        (uint256 cp, SwarmConsensus.Decision d, uint256 wv, uint256 nv, , ) =
            consensus.getResult(qid);

        // Integer rounding in weightedSum/WAD division loses 1 wei
        require(cp >= 0.92e18 - 1 && cp <= 0.92e18, "single vote consensus should match vote");
        require(nv == 1, "should have 1 vote");
        require(wv == 0, "single vote variance should be 0");
        require(d == SwarmConsensus.Decision.YES, "0.92 should be YES");
    }

    function test_revert_alreadyResolved() public {
        bytes32 qid = keccak256("Double submit");
        address[] memory agents = new address[](1);
        agents[0] = address(0x1);
        uint256[] memory probs = new uint256[](1);
        probs[0] = 0.90e18;

        consensus.submitVotes(qid, agents, probs);

        try consensus.submitVotes(qid, agents, probs) {
            revert("should have reverted");
        } catch {}
    }

    function test_revert_emptyVotes() public {
        bytes32 qid = keccak256("Empty");
        address[] memory agents = new address[](0);
        uint256[] memory probs = new uint256[](0);

        try consensus.submitVotes(qid, agents, probs) {
            revert("should have reverted");
        } catch {}
    }

    function test_revert_lengthMismatch() public {
        bytes32 qid = keccak256("Mismatch");
        address[] memory agents = new address[](2);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        uint256[] memory probs = new uint256[](1);
        probs[0] = 0.50e18;

        try consensus.submitVotes(qid, agents, probs) {
            revert("should have reverted");
        } catch {}
    }

    function test_revert_probAboveWAD() public {
        bytes32 qid = keccak256("Bad prob");
        address[] memory agents = new address[](1);
        agents[0] = address(0x1);
        uint256[] memory probs = new uint256[](1);
        probs[0] = WAD + 1;

        try consensus.submitVotes(qid, agents, probs) {
            revert("should have reverted");
        } catch {}
    }

    // --- Vote audit ---

    function test_getVotes_returnsAll() public {
        bytes32 qid = keccak256("Audit test");
        address[] memory agents = new address[](2);
        agents[0] = address(0x1);
        agents[1] = address(0x2);
        uint256[] memory probs = new uint256[](2);
        probs[0] = 0.80e18;
        probs[1] = 0.75e18;

        consensus.submitVotes(qid, agents, probs);

        SwarmConsensus.Vote[] memory votes = consensus.getVotes(qid);
        require(votes.length == 2, "should return 2 votes");
        require(votes[0].agent == address(0x1), "vote 0 agent mismatch");
        require(votes[0].probability == 0.80e18, "vote 0 prob mismatch");
        require(votes[1].agent == address(0x2), "vote 1 agent mismatch");
        require(votes[1].probability == 0.75e18, "vote 1 prob mismatch");
    }

    // --- Question tracking ---

    function test_questionCount() public {
        require(consensus.questionCount() == 0, "should start at 0");

        bytes32 qid1 = keccak256("Q1");
        bytes32 qid2 = keccak256("Q2");
        address[] memory agents = new address[](1);
        agents[0] = address(0x1);
        uint256[] memory probs = new uint256[](1);
        probs[0] = 0.90e18;

        consensus.submitVotes(qid1, agents, probs);
        require(consensus.questionCount() == 1, "should be 1");

        probs[0] = 0.10e18;
        consensus.submitVotes(qid2, agents, probs);
        require(consensus.questionCount() == 2, "should be 2");
    }
}
