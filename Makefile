.PHONY: test test-python test-solidity demo api lint clean

# Run all Python tests
test: test-python

test-python:
	python3 -m pytest tests/ -v --tb=short

# Run Foundry tests (requires forge)
test-solidity:
	cd contracts && forge test -v

# Run demo mode (no LLM server needed)
demo:
	python3 swarm_verify.py --demo "Did BTC close above $$100K on May 5, 2026?"

# Start API server
api:
	python3 -m swarm_oracle.api

# Record demo for video
record-demo:
	bash record-demo.sh

# Clean build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ .pytest_cache/ pytest-cache-files-*
	cd contracts && rm -rf out/ cache/ 2>/dev/null || true
