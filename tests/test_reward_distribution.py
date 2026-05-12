"""Tests for RewardDistribution contract logic (Python-side validation).

These tests verify the reward distribution math matches expectations
without requiring Solidity/Foundry. The actual contract tests are in
contracts/test/RewardDistribution.t.sol.
"""
from __future__ import annotations

import pytest


WAD = 10**18
ACCURACY_POOL_FRACTION = int(0.30 * WAD)
BASE_POOL_FRACTION = int(0.70 * WAD)


def compute_reward_shares(
    weights: list[int],
    probabilities: list[int],
    consensus_prob: int,
    pool: int,
    alignment_threshold: int = int(0.15 * WAD),
) -> list[int]:
    """Python mirror of RewardDistribution.distributeRewards logic."""
    n = len(weights)
    total_weight = sum(weights)
    assert total_weight > 0

    # Determine correct agents (within alignment_threshold of consensus)
    correct = []
    correct_weight = 0
    for i in range(n):
        diff = abs(probabilities[i] - consensus_prob)
        if diff <= alignment_threshold:
            correct.append(i)
            correct_weight += weights[i]

    has_correct = correct_weight > 0
    base_pool = (pool * BASE_POOL_FRACTION) // WAD
    accuracy_pool = pool - base_pool

    rewards = []
    for i in range(n):
        reward = 0
        # Base reward
        reward += (base_pool * weights[i]) // total_weight
        # Accuracy reward
        if has_correct and i in correct:
            reward += (accuracy_pool * weights[i]) // correct_weight
        elif not has_correct:
            reward += (accuracy_pool * weights[i]) // total_weight
        rewards.append(reward)

    return rewards


class TestRewardMath:
    """Verify the reward splitting math in Python."""

    def test_equal_weights_equal_shares(self):
        """Three agents with equal weights should get equal base shares."""
        weights = [WAD, WAD, WAD]
        probs = [int(0.90 * WAD), int(0.88 * WAD), int(0.85 * WAD)]
        consensus = int(0.88 * WAD)
        pool = 3 * WAD  # 3 ETH

        shares = compute_reward_shares(weights, probs, consensus, pool)

        # All within alignment threshold → all get accuracy + base
        # With equal weights, shares should be equal
        assert shares[0] == shares[1] == shares[2]
        assert sum(shares) <= pool

    def test_higher_weight_gets_more(self):
        """Agent with higher calibration weight should get more reward."""
        # Oracle weight ~9.9, Reliable ~5.5, Novice ~3.98 (from contract math)
        weights = [int(9.9 * WAD), int(5.5 * WAD), int(3.98 * WAD)]
        probs = [int(0.92 * WAD), int(0.88 * WAD), int(0.85 * WAD)]
        consensus = int(0.89 * WAD)
        pool = WAD  # 1 ETH

        shares = compute_reward_shares(weights, probs, consensus, pool)

        assert shares[0] > shares[1] > shares[2]
        assert sum(shares) <= pool

    def test_wrong_agent_loses_accuracy_bonus(self):
        """Agent far from consensus should miss accuracy pool."""
        weights = [int(5 * WAD), int(5 * WAD)]
        probs = [int(0.90 * WAD), int(0.30 * WAD)]  # second agent way off
        consensus = int(0.90 * WAD)
        pool = WAD

        shares = compute_reward_shares(weights, probs, consensus, pool)

        # Agent 0 gets base + accuracy; Agent 1 gets base only
        assert shares[0] > shares[1]
        # Agent 0 should get ~85% (70% base / 2 + 30% accuracy)
        # Agent 1 should get ~35% (70% base / 2)
        expected_0 = pool * 70 // 200 + pool * 30 // 100  # 0.35 + 0.30 = 0.65
        expected_1 = pool * 70 // 200  # 0.35
        # Allow rounding
        assert abs(shares[0] - expected_0) < 10
        assert abs(shares[1] - expected_1) < 10

    def test_no_correct_agents_fallback(self):
        """When nobody is within threshold, accuracy pool splits by weight."""
        weights = [int(5 * WAD), int(5 * WAD)]
        probs = [int(0.90 * WAD), int(0.10 * WAD)]
        consensus = int(0.50 * WAD)  # both far from consensus
        pool = WAD
        # threshold is 0.15 — both are >0.15 away from 0.50

        shares = compute_reward_shares(weights, probs, consensus, pool)

        # Equal weights, both miss accuracy → equal shares
        assert shares[0] == shares[1]
        assert sum(shares) <= pool

    def test_total_distributed_near_pool(self):
        """Total distributed should be very close to pool (minimal rounding dust)."""
        weights = [int(9.9 * WAD), int(5.5 * WAD), int(3.98 * WAD)]
        probs = [int(0.92 * WAD), int(0.88 * WAD), int(0.85 * WAD)]
        consensus = int(0.89 * WAD)
        pool = 10 * WAD  # 10 ETH

        shares = compute_reward_shares(weights, probs, consensus, pool)
        total = sum(shares)

        assert total <= pool
        # Less than 0.001 ETH rounding dust
        assert pool - total < int(0.001 * WAD)

    def test_single_agent_gets_full_pool(self):
        """Single agent should receive the entire pool."""
        weights = [int(5 * WAD)]
        probs = [int(0.90 * WAD)]
        consensus = int(0.90 * WAD)
        pool = WAD

        shares = compute_reward_shares(weights, probs, consensus, pool)

        assert shares[0] == pool

    def test_pool_fractions_sum_to_one(self):
        """BASE_POOL_FRACTION + ACCURACY_POOL_FRACTION should equal WAD."""
        assert BASE_POOL_FRACTION + ACCURACY_POOL_FRACTION == WAD
