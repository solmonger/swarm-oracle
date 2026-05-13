# ============================================================================
# Swarm Oracle — One-command demo container
# ============================================================================
# Build:  docker build -t swarm-oracle .
# Run:    docker run -p 8000:8000 swarm-oracle
# Demo:   docker run swarm-oracle demo
# Test:   docker run swarm-oracle test
# CLI:    docker run swarm-oracle cli "Did BTC close above 100K?"
# ============================================================================

FROM python:3.12-slim AS base

LABEL maintainer="Eshaan Mathakari"
LABEL description="Swarm Oracle — Calibration-weighted multi-agent prediction oracle"

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY swarm_oracle/ swarm_oracle/
COPY swarm_verify.py .
COPY tests/ tests/
COPY contracts/agent_registry.json contracts/agent_registry.json
COPY demo.html .
COPY README.md .

# Install with all optional deps for full functionality
RUN pip install --no-cache-dir -e ".[dev,api]"

# Expose API port
EXPOSE 8000

# Entrypoint script that dispatches based on first argument
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["api"]
