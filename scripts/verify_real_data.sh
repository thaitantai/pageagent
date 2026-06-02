#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="/home/tantai/.hermes/fanpage-agent"
cd "$PROJECT_DIR"

echo "=== Verify real data paths ==="

echo ""
echo "--- Brand file ---"
ls -la data/real/brand_profile.json 2>&1

echo ""
echo "--- Data files ---"
ls -la data/real/*.csv data/real/*.json 2>&1

echo ""
echo "--- Smoke: load brand profile ---"
python3 -c "
from fanpage_agent.loaders.brand_loader import load_brand_profile
profile = load_brand_profile('data/real/brand_profile.json')
print(f'brand_id:     {profile.brand_id}')
print(f'brand_name:   {profile.brand_name}')
print(f'industry:     {profile.industry}')
print(f'content_pillars: {len(profile.content_pillars)}')
print(f'target_audiences: {len(profile.target_audiences)}')
print(f'products_services: {len(profile.products_services)}')
"
