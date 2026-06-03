#!/usr/bin/env python3
"""Analyze imported post history to build brand profile."""
import sys, json, csv
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
history = ROOT / "data" / "real" / "post_history.csv"

rows = []
with open(history, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

print(f"Total posts: {len(rows)}")

pillars = Counter(r["pillar"] for r in rows)
objectives = Counter(r["objective"] for r in rows)
print(f"\nPillars: {dict(pillars)}")
print(f"Objectives: {dict(objectives)}")

print("\n--- Sample topics ---")
for r in rows[:20]:
    print(f"  [{r['published_at'][:10]}] {r['pillar']}: {r['topic'][:80]}")
    print(f"    Hook: {r['hook'][:80]}")
