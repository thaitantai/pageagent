"""Quick state check for after rebuild."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "agent" / "memory.db"

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

print("=== POSTS (newest first) ===")
for r in conn.execute(
    "SELECT package_id, variant_id, caption, hook, reach, engagements, published_at, schedule_date "
    "FROM published_posts ORDER BY published_at DESC"
):
    ts = (r["published_at"] or "")[:19]
    hook = (r["hook"] or "-")[:70]
    caption = (r["caption"] or "-")[:80]
    print(f"  [{ts}] {r['package_id']}")
    print(f"    hook: {hook}")
    print(f"    cap:  {caption}...")
    print(f"    reach:{r['reach']} eng:{r['engagements']} sched:{r['schedule_date']}")

print()
print("=== PATTERNS ===")
for r in conn.execute(
    "SELECT pattern_type, value, confidence, sample_size, avg_engagement "
    "FROM patterns ORDER BY confidence DESC LIMIT 12"
):
    v = (r["value"] or "?")[:40]
    print(f"  {r['pattern_type']}: {v}  (conf={r['confidence']:.2f}  n={r['sample_size']}  eng={r['avg_engagement']})")

print()
print("=== STATE ===")
try:
    s = json.loads((ROOT / "data" / "agent" / "state.json").read_text())
    print(f"  ticks_run: {s.get('ticks_run', 0)}")
    print(f"  total_published: {s.get('total_published', 0)}")
    print(f"  community_fetches: {s.get('community_fetches', 0)}")
    print(f"  last_tick_ts: {str(s.get('last_tick_ts', ''))[:25]}")
except Exception as e:
    print(f"  Error: {e}")

conn.close()
