.PHONY: test test-api test-integration test-solidity demo api record-demo clean docker docker-demo docker-test docker-api

# ---------- Python ----------
test:
	python3 -m pytest tests/ -v --tb=short

test-api:
	python3 -m pytest tests/test_api.py -v --tb=short

test-integration:
	python3 -m pytest tests/test_integration.py -v --tb=short

demo:
	python3 swarm_verify.py --demo "Did BTC close above $$100K on May 5, 2026?"
	@echo ""
	python3 swarm_verify.py --demo "Will the Lakers win tonight?"
	@echo ""
	python3 swarm_verify.py --demo --json "Is climate change accelerating?"

api:
	uvicorn swarm_oracle.api:app --host 0.0.0.0 --port 8000 --reload

# ---------- Solidity ----------
test-solidity:
	cd contracts && forge test -v

# ---------- Docker ----------
docker:
	docker build -t swarm-oracle .

docker-demo: docker
	docker run --rm swarm-oracle demo

docker-test: docker
	docker run --rm swarm-oracle test

docker-api: docker
	docker run --rm -p 8000:8000 swarm-oracle api

# ---------- Recording ----------
record-demo:
	bash record-demo.sh

# ---------- Clean ----------
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "pytest-cache-files-*" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
