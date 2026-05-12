"""Python → Solidity bridge for the Swarm Oracle protocol.

Submits agent votes on-chain and reads consensus results.
Requires web3.py and deployed contract addresses.

Usage:
    from contracts.bridge import SwarmBridge

    bridge = SwarmBridge(rpc_url="https://sepolia.base.org", private_key="0x...")
    bridge.set_addresses(registry="0x...", consensus="0x...")

    # Seed agent Brier scores from Python pipeline
    bridge.seed_brier("0xAgentAddr", brier=0.10, num_predictions=220)

    # Submit votes after swarm verification
    bridge.submit_votes(
        question="Will BTC close above 100K?",
        agents=["0xAddr1", "0xAddr2", "0xAddr3"],
        probabilities=[0.92, 0.85, 0.70],
    )

    # Read result
    result = bridge.get_result("Will BTC close above 100K?")
    print(result)
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

WAD = 10**18

# ABI fragments — enough to call the contracts without full compilation
REGISTRY_ABI = [
    {
        "inputs": [
            {"name": "agent", "type": "address"},
            {"name": "brier", "type": "uint256"},
            {"name": "n", "type": "uint256"},
        ],
        "name": "seedBrier",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "agentAddrs", "type": "address[]"},
            {"name": "briers", "type": "uint256[]"},
            {"name": "ns", "type": "uint256[]"},
        ],
        "name": "seedBrierBatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "agent", "type": "address"},
            {"name": "prediction", "type": "uint256"},
            {"name": "outcome", "type": "uint256"},
        ],
        "name": "updateBrier",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "agent", "type": "address"}],
        "name": "computeWeight",
        "outputs": [{"name": "weight", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "agentAddrs", "type": "address[]"}],
        "name": "computeWeights",
        "outputs": [{"name": "weights", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "agent", "type": "address"}],
        "name": "getAgent",
        "outputs": [
            {"name": "brierScore", "type": "uint256"},
            {"name": "numPredictions", "type": "uint256"},
            {"name": "lastUpdated", "type": "uint256"},
            {"name": "registered", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

CONSENSUS_ABI = [
    {
        "inputs": [
            {"name": "questionId", "type": "bytes32"},
            {"name": "agentAddrs", "type": "address[]"},
            {"name": "probabilities", "type": "uint256[]"},
        ],
        "name": "submitVotes",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "questionId", "type": "bytes32"}],
        "name": "getResult",
        "outputs": [
            {"name": "consensusProbability", "type": "uint256"},
            {"name": "decision", "type": "uint8"},
            {"name": "weightedVariance", "type": "uint256"},
            {"name": "numVotes", "type": "uint256"},
            {"name": "resolvedAt", "type": "uint256"},
            {"name": "resolved", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

DECISION_MAP = {0: "PENDING", 1: "YES", 2: "NO", 3: "DISPUTE"}


@dataclass
class OnChainResult:
    question: str
    question_id: bytes
    consensus_probability: float
    decision: str
    weighted_variance: float
    num_votes: int
    resolved_at: int
    resolved: bool


def question_to_id(question: str) -> bytes:
    """Deterministic bytes32 ID from question text (keccak256)."""
    return hashlib.sha256(question.encode("utf-8")).digest()


def to_wad(x: float) -> int:
    """Convert float to WAD (18 decimal fixed point)."""
    return int(x * WAD)


def from_wad(x: int) -> float:
    """Convert WAD to float."""
    return x / WAD


class SwarmBridge:
    """Bridge between Python swarm_oracle and on-chain contracts."""

    def __init__(self, rpc_url: str | None = None, private_key: str | None = None):
        self.rpc_url = rpc_url or os.environ.get("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
        self.private_key = private_key or os.environ.get("DEPLOYER_KEY", "")
        self._web3 = None
        self._registry = None
        self._consensus = None
        self._registry_addr = None
        self._consensus_addr = None

    @property
    def web3(self):
        if self._web3 is None:
            try:
                from web3 import Web3
                self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            except ImportError:
                raise ImportError("web3 required: pip install web3")
        return self._web3

    def set_addresses(self, registry: str, consensus: str):
        """Set deployed contract addresses."""
        self._registry_addr = self.web3.to_checksum_address(registry)
        self._consensus_addr = self.web3.to_checksum_address(consensus)
        self._registry = self.web3.eth.contract(
            address=self._registry_addr, abi=REGISTRY_ABI
        )
        self._consensus = self.web3.eth.contract(
            address=self._consensus_addr, abi=CONSENSUS_ABI
        )

    def _send_tx(self, fn):
        """Build, sign, and send a transaction."""
        acct = self.web3.eth.account.from_key(self.private_key)
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": self.web3.eth.get_transaction_count(acct.address),
            "gas": 500_000,
            "gasPrice": self.web3.eth.gas_price,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    # --- Registry operations ---

    def seed_brier(self, agent: str, brier: float, num_predictions: int):
        """Seed an agent's Brier score on-chain."""
        agent_addr = self.web3.to_checksum_address(agent)
        return self._send_tx(
            self._registry.functions.seedBrier(
                agent_addr, to_wad(brier), num_predictions
            )
        )

    def update_brier(self, agent: str, prediction: float, outcome: bool):
        """Update agent's running Brier with a new observation."""
        agent_addr = self.web3.to_checksum_address(agent)
        outcome_wad = WAD if outcome else 0
        return self._send_tx(
            self._registry.functions.updateBrier(
                agent_addr, to_wad(prediction), outcome_wad
            )
        )

    def get_weight(self, agent: str) -> float:
        """Read an agent's calibration weight."""
        agent_addr = self.web3.to_checksum_address(agent)
        w = self._registry.functions.computeWeight(agent_addr).call()
        return from_wad(w)

    def get_agent(self, agent: str) -> dict:
        """Read an agent's full record."""
        agent_addr = self.web3.to_checksum_address(agent)
        b, n, updated, registered = self._registry.functions.getAgent(agent_addr).call()
        return {
            "brier_score": from_wad(b),
            "num_predictions": n,
            "last_updated": updated,
            "registered": registered,
        }

    # --- Consensus operations ---

    def submit_votes(
        self,
        question: str,
        agents: list[str],
        probabilities: list[float],
    ):
        """Submit agent votes and trigger on-chain consensus."""
        qid = question_to_id(question)
        agent_addrs = [self.web3.to_checksum_address(a) for a in agents]
        probs_wad = [to_wad(p) for p in probabilities]
        return self._send_tx(
            self._consensus.functions.submitVotes(qid, agent_addrs, probs_wad)
        )

    def get_result(self, question: str) -> OnChainResult:
        """Read consensus result for a question."""
        qid = question_to_id(question)
        prob, decision, var, nvotes, resolved_at, resolved = (
            self._consensus.functions.getResult(qid).call()
        )
        return OnChainResult(
            question=question,
            question_id=qid,
            consensus_probability=from_wad(prob),
            decision=DECISION_MAP.get(decision, f"UNKNOWN({decision})"),
            weighted_variance=from_wad(var),
            num_votes=nvotes,
            resolved_at=resolved_at,
            resolved=resolved,
        )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Swarm Oracle bridge CLI")
    parser.add_argument("--rpc", default=None, help="RPC URL")
    parser.add_argument("--key", default=None, help="Private key")
    parser.add_argument("--registry", required=True, help="CalibrationRegistry address")
    parser.add_argument("--consensus", required=True, help="SwarmConsensus address")
    parser.add_argument("--action", choices=["seed", "vote", "result", "weight"], required=True)
    parser.add_argument("--agent", help="Agent address")
    parser.add_argument("--brier", type=float, help="Brier score")
    parser.add_argument("--n", type=int, help="Number of predictions")
    parser.add_argument("--question", help="Question text")
    parser.add_argument("--agents", nargs="+", help="Agent addresses for voting")
    parser.add_argument("--probs", nargs="+", type=float, help="Probabilities for voting")

    args = parser.parse_args()
    bridge = SwarmBridge(rpc_url=args.rpc, private_key=args.key)
    bridge.set_addresses(registry=args.registry, consensus=args.consensus)

    if args.action == "seed":
        receipt = bridge.seed_brier(args.agent, args.brier, args.n)
        print(f"Seeded agent {args.agent}: brier={args.brier}, n={args.n}")
        print(f"Tx: {receipt.transactionHash.hex()}")

    elif args.action == "vote":
        receipt = bridge.submit_votes(args.question, args.agents, args.probs)
        print(f"Votes submitted for: {args.question}")
        print(f"Tx: {receipt.transactionHash.hex()}")

    elif args.action == "result":
        result = bridge.get_result(args.question)
        print(f"Question: {result.question}")
        print(f"Consensus: {result.consensus_probability:.4f}")
        print(f"Decision: {result.decision}")
        print(f"Votes: {result.num_votes}")
        print(f"Resolved: {result.resolved}")

    elif args.action == "weight":
        w = bridge.get_weight(args.agent)
        info = bridge.get_agent(args.agent)
        print(f"Agent: {args.agent}")
        print(f"Weight: {w:.4f}")
        print(f"Brier: {info['brier_score']:.4f}")
        print(f"Predictions: {info['num_predictions']}")
