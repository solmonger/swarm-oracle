.PHONY: test test-api test-integration test-solidity test-sybil test-adversarial demo api record-demo clean docker docker-demo docker-test docker-api sybil-demo sybil-demo-all adversarial-demo adversarial-compare adversarial-demo-all

# ---------- Python ----------
test:
	python3 -m pytest tests/ -v --tb=short

test-api:
	python3 -m pytest tests/test_api.py -v --tb=short

test-integration:
	python3 -m pytest tests/test_integration.py -v --tb=short

test-sybil:
	python3 -m pytest tests/test_sybil.py -v --tb=short

test-adversarial:
	python3 -m pytest tests/test_adversarial.py tests/test_adversarial_demo.py -v --tb=short

# ---------- Sybil-resistance analysis ----------
sybil-demo:
	python3 -m scripts.sybil_demo --target YES

sybil-demo-all:
	python3 -m scripts.sybil_demo --all

# ---------- Multi-vector adversarial simulation ----------
adversarial-demo:
	python3 -m scripts.adversarial_demo

adversarial-demo-all:
	python3 -m scripts.adversarial_demo --target YES
	@echo ""
	python3 -m scripts.adversarial_demo --target NO
	@echo ""
	python3 -m scripts.adversarial_demo --target DISPUTE

adversarial-compare:
	python3 -m scripts.adversarial_demo --compare

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
