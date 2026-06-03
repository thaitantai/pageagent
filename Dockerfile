# Fanpage Agent — Docker image
# Build:   docker build -t fanpage-agent:latest .
# Run:     docker run --rm -v $(pwd)/.env:/app/.env fanpage-agent:latest config
# Run CLI: docker run --rm -v $(pwd)/.env:/app/.env fanpage-agent:latest config check

# ── Stage 1: base ──────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps: libcurl for curl_cffi, build tools
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

# Install build deps first (will be cached unless requirements change)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: final ─────────────────────────────────────────────
FROM deps AS final

# Copy project files
COPY . .

# Install package in editable mode so entry points work
RUN pip install --no-cache-dir -e .

# Make scripts executable
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Default: management CLI
ENTRYPOINT ["fanpage-manager"]
CMD ["help"]


# ── Stage 4: dev — for development with live-reload ────────────
FROM deps AS dev

RUN pip install --no-cache-dir watchdog

COPY . .
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["fanpage-manager"]
CMD ["help"]
