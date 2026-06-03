# Fanpage Agent V2 — Docker image
# Build:   docker build -t fanpage-agent-v2:latest -f Dockerfile.v2 .
# Run:     docker compose --profile v2 up -d

# ── Stage 1: base ──────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps
RUN apt-get update -qq && apt-get install -y -qq \
    libcurl4-openssl-dev \
    libssl-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# ── Stage 2: deps ──────────────────────────────────────────────
FROM base AS deps

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: final ─────────────────────────────────────────────
FROM deps AS final

COPY . .
RUN pip install --no-cache-dir -e .

# V2 daemon entry point
ENTRYPOINT ["python", "-m", "fanpage_agent_v2.main"]
CMD ["daemon"]
