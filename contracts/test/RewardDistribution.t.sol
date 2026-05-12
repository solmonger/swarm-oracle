// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CalibrationRegistry} from "../src/CalibrationRegistry.sol";
import {SwarmConsensus} from "../src/SwarmConsensus.sol";
import {RewardDistribution} from "../src/RewardDistribution.sol";

contract RewardDistributionTest {
    CalibrationRegistry public reg;
    SwarmConsensus public consensus;
    RewardDistribution public rewards;

    uint256 constant WAD = 1e18;

    // Agent addresses
    address constant ORACLE   = address(0x1);
    address constant RELIABLE = address(0x2);
    address constant NOVICE   = address(0x3);

    function setUp() public {
        reg = new CalibrationRegistry();
        consensus = new SwarmConsensus(address(reg));
        rewards = new RewardDistribution(address(reg), address(consensus));

        // Seed agents
        reg.seedBrier(ORACLE,   0.10e18, 220);
        reg.seedBrier(RELIABLE, 0.18e18, 140);
        reg.seedBrier(NOVICE,   0.25e18, 25);
    }

    // --- Helpers ---

    function _resolveQuestion(bytes32 qid) internal {
        address[] memory agents = new address[](3);
        agents[0] = ORACLE;
        agents[1] = RELIABLE;
        agents[2] = NOVICE;

        uint256[] memory probs = new uint256[](3);
        probs[0] = 0.92e18;
        probs[1] = 0.88e18;
        probs[2] = 0.85e18;

        consensus.submitVotes(qid, agents, probs);
    }

    // --- Funding ---

    function test_fundQuestion() public {
        bytes32 qid = keccak256("fund test");
        rewards.fundQuestion{value: 1 ether}(qid);
        require(rewards.questionPools(qid) == 1 ether, "pool should be 1 ETH");
    }

    function test_fundQuestion_additive() public {
        bytes32 qid = keccak256("additive test");
        rewards.fundQuestion{value: 0.5 ether}(qid);
        rewards.fundQuestion{value: 0.3 ether}(qid);
        require(rewards.questionPools(qid) == 0.8 ether, "pool should be 0.8 ETH");
    }

    function test_fundQuestion_revert_zero() public {
        bytes32 qid = keccak256("zero test");
        try rewards.fundQuestion{value: 0}(qid) {
            revert("should revert on zero");
        } catch {}
    }

    // --- Distribution ---

    function test_distributeRewards_basic() public {
        bytes32 qid = keccak256("dist test");
        _resolveQuestion(qid);

        rewards.fundQuestion{value: 1 ether}(qid);
        rewards.distributeRewards(qid);

        require(rewards.distributed(qid), "should be marked distributed");

        // All agents should have some balance
        uint256 b1 = rewards.balances(ORACLE);
        uint256 b2 = rewards.balances(RELIABLE);
        uint256 b3 = rewards.balances(NOVICE);

        require(b1 > 0, "oracle should have reward");
        require(b2 > 0, "reliable should have reward");
        require(b3 > 0, "novice should have reward");

        // Oracle should get the most (highest weight)
        require(b1 > b2, "oracle should get more than reliable");
        require(b2 > b3, "reliable should get more than novice");

        // Total credited should be <= pool (rounding dust allowed)
        uint256 total = b1 + b2 + b3;
        require(total <= 1 ether, "total should not exceed pool");
        // Should be close to 1 ether (minimal rounding dust)
        require(total > 0.99 ether, "too much rounding dust");
    }

    function test_distributeRewards_revert_notResolved() public {
        bytes32 qid = keccak256("unresolved");
        rewards.fundQuestion{value: 1 ether}(qid);

        try rewards.distributeRewards(qid) {
            revert("should revert on unresolved question");
        } catch {}
    }

    function test_distributeRewards_revert_noPool() public {
        bytes32 qid = keccak256("no pool");
        _resolveQuestion(qid);

        try rewards.distributeRewards(qid) {
            revert("should revert on empty pool");
        } catch {}
    }

    function test_distributeRewards_revert_double() public {
        bytes32 qid = keccak256("double dist");
        _resolveQuestion(qid);
        rewards.fundQuestion{value: 1 ether}(qid);
        rewards.distributeRewards(qid);

        try rewards.distributeRewards(qid) {
            revert("should revert on double distribution");
        } catch {}
    }

    function test_distributeRewards_revert_fundAfterDist() public {
        bytes32 qid = keccak256("fund after dist");
        _resolveQuestion(qid);
        rewards.fundQuestion{value: 1 ether}(qid);
        rewards.distributeRewards(qid);

        try rewards.fundQuestion{value: 0.5 ether}(qid) {
            revert("should revert funding after distribution");
        } catch {}
    }

    // --- Distribution records ---

    function test_distributionRecord() public {
        bytes32 qid = keccak256("record test");
        _resolveQuestion(qid);
        rewards.fundQuestion{value: 2 ether}(qid);
        rewards.distributeRewards(qid);

        (bytes32 rid, uint256 poolSize, uint256 numRecipients, uint256 distAt) =
            rewards.distributions(qid);

        require(rid == qid, "record questionId mismatch");
        require(poolSize == 2 ether, "record poolSize mismatch");
        require(numRecipients == 3, "record numRecipients mismatch");
        require(distAt > 0, "record timestamp should be set");
        require(rewards.getDistributionCount() == 1, "should have 1 distribution");
    }

    // --- Multiple questions ---

    function test_multipleQuestions_accumulate() public {
        bytes32 qid1 = keccak256("Q1");
        bytes32 qid2 = keccak256("Q2");

        // Resolve both
        _resolveQuestion(qid1);

        address[] memory agents = new address[](2);
        agents[0] = ORACLE;
        agents[1] = RELIABLE;
        uint256[] memory probs = new uint256[](2);
        probs[0] = 0.05e18;
        probs[1] = 0.10e18;
        consensus.submitVotes(qid2, agents, probs);

        // Fund and distribute both
        rewards.fundQuestion{value: 1 ether}(qid1);
        rewards.fundQuestion{value: 0.5 ether}(qid2);

        rewards.distributeRewards(qid1);
        uint256 oracleAfterQ1 = rewards.balances(ORACLE);

        rewards.distributeRewards(qid2);
        uint256 oracleAfterQ2 = rewards.balances(ORACLE);

        // Balance should have increased
        require(oracleAfterQ2 > oracleAfterQ1, "balance should accumulate");
        require(rewards.getDistributionCount() == 2, "should have 2 distributions");
    }

    // --- Withdraw ---

    function test_withdraw_revert_noBalance() public {
        try rewards.withdraw() {
            revert("should revert on zero balance");
        } catch {}
    }

    // Note: Full withdraw test requires a contract that can receive ETH and call withdraw.
    // For hackathon scope, we verify the balance accounting is correct above.

    // --- Total balance ---

    function test_totalBalance() public {
        bytes32 qid = keccak256("balance test");
        rewards.fundQuestion{value: 3 ether}(qid);
        require(rewards.totalBalance() == 3 ether, "total balance should match funding");
    }

    // Allow this test contract to receive ETH (for testing)
    receive() external payable {}
}
