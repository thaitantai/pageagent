#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"
exec scripts/run_auto_publish_cycle.sh
