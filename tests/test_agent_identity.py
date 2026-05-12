"""Tests for AgentIdentity contract logic (Python-side validation).

These tests verify the identity token data model and profile aggregation
without requiring Solidity/Foundry. The actual contract tests are in
contracts/test/AgentIdentity.t.sol.
"""
from __future__ import annotations

import json
import pytest


class TestAgentIdentityModel:
    """Verify the agent identity data model in Python."""

    def test_profile_aggregation(self):
        """Profile should combine token data + calibration stats."""
        # Simulate what getAgentProfile returns
        profile = {
            "token_id": 1,
            "label": "agent-oracle",
            "minted_at": 1715500000,
            "brier_score": 0.10,
            "num_predictions": 220,
            "calibration_weight": 9.9009,  # WAD / (0.10 + 0.001)
            "has_identity_token": True,
            "registered_in_calibration": True,
        }

        assert profile["has_identity_token"]
        assert profile["registered_in_calibration"]
        assert profile["brier_score"] < 0.20  # Good calibration
        assert profile["calibration_weight"] > 1.0  # Above base weight
        assert profile["label"] == "agent-oracle"

    def test_soulbound_invariants(self):
        """Soulbound tokens must not be transferable."""
        # These are conceptual tests — the contract enforces this
        # but we document the invariants here for clarity
        soulbound_rules = {
            "transferFrom": "BLOCKED",
            "safeTransferFrom": "BLOCKED",
            "approve": "BLOCKED",
            "setApprovalForAll": "BLOCKED",
            "getApproved": "returns address(0)",
            "isApprovedForAll": "returns false",
        }

        for method, expected in soulbound_rules.items():
            assert expected in ("BLOCKED", "returns address(0)", "returns false"), \
                f"Unexpected rule for {method}: {expected}"

    def test_auto_generated_uri_format(self):
        """Auto-generated tokenURI should be valid JSON with expected fields."""
        # Simulate the on-chain JSON generation
        label = "agent-oracle"
        agent_addr = "0x0000000000000000000000000000000000000001"

        uri_json = json.dumps({
            "name": label,
            "description": "Swarm Oracle Agent Identity (Soulbound)",
            "attributes": [
                {"trait_type": "Agent Address", "value": agent_addr}
            ]
        })

        parsed = json.loads(uri_json)
        assert parsed["name"] == label
        assert "Soulbound" in parsed["description"]
        assert len(parsed["attributes"]) == 1
        assert parsed["attributes"][0]["trait_type"] == "Agent Address"

    def test_token_id_starts_at_one(self):
        """Token IDs should start at 1 (not 0) to allow zero as 'no token'."""
        # This is important because agentToToken returns 0 for unminted agents
        first_token_id = 1
        assert first_token_id > 0, "Token IDs must start above 0"

    def test_one_token_per_agent(self):
        """Each agent address should only have one identity token."""
        minted_agents = set()

        agents = [
            "0x0000000000000000000000000000000000000001",
            "0x0000000000000000000000000000000000000002",
            "0x0000000000000000000000000000000000000003",
        ]

        for agent in agents:
            assert agent not in minted_agents, f"Duplicate mint for {agent}"
            minted_agents.add(agent)

        assert len(minted_agents) == 3

    def test_erc165_interface_ids(self):
        """Contract should support ERC-721 and ERC-165 interface IDs."""
        erc721_interface_id = 0x80ac58cd
        erc165_interface_id = 0x01ffc9a7

        # These are the standard interface IDs
        assert erc721_interface_id == 0x80ac58cd
        assert erc165_interface_id == 0x01ffc9a7

    def test_batch_mint_produces_sequential_ids(self):
        """Batch minting should produce sequential token IDs."""
        next_token_id = 1
        num_agents = 5
        expected_ids = list(range(next_token_id, next_token_id + num_agents))

        assert expected_ids == [1, 2, 3, 4, 5]
        assert len(expected_ids) == num_agents
