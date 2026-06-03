#!/usr/bin/env python3
"""Publish approved items from Google Sheets to Facebook, then update sheet."""
import sys, json, os, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

from fanpage_agent.config import Settings
from fanpage_agent.adapters.store_factory import build_store
from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.models import BrandProfile

class MockArgs: store_backend = "google"; calendar_file = None; history_file = None; metrics_file = None; triage_file = None

settings = Settings.from_env(root_dir=ROOT)
store = build_store(settings, MockArgs())
fb = FacebookClient(settings)

today = datetime.date.today().isoformat()
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

items = store.list_calendar_items(approval_status="approved")
due = [i for i in items if i.get("date","") <= today and i.get("status") != "published"]

if not due:
    print(json.dumps({"published": [], "message": "No due items to publish"}))
    sys.exit(0)

results = []
for item in due:
    cal_id = item.get("calendar_id", "")
    topic = item.get("topic", "")
    caption_ref = item.get("final_caption_ref", "") or ""
    
    # Read caption content
    caption_text = topic
    if caption_ref:
        cap_path = Path(caption_ref)
        if not cap_path.is_absolute():
            cap_path = ROOT / cap_path
        if cap_path.exists():
            try:
                cap_data = json.loads(cap_path.read_text(encoding="utf-8"))
                variants = cap_data.get("variants", [])
                if variants:
                    caption_text = variants[0].get("caption", topic)
            except Exception:
                caption_text = topic
        else:
            # Try data/real/ prefix
            cap_path2 = ROOT / "data/real" / caption_ref
            if cap_path2.exists():
                cap_data = json.loads(cap_path2.read_text(encoding="utf-8"))
                variants = cap_data.get("variants", [])
                if variants:
                    caption_text = variants[0].get("caption", topic)
    
    # Post to Facebook
    try:
        fb_result = fb.post_to_page(caption_text)
        post_id = fb_result.get("id", "")
        permalink = fb_result.get("permalink_url", "") or fb_result.get("permalink", "")
            
        # If no permalink, build it from post_id
        display_link = f"https://facebook.com/{post_id}" if post_id else (permalink or "")
        
        # Update sheet
        result = store.publish_calendar_item(
            calendar_id=cal_id,
            published_at=now,
            permalink=display_link or "",
        )
        results.append({"calendar_id": cal_id, "status": "published", "post_id": post_id, "permalink": display_link})
        print(f"✅ {cal_id}: posted -> {display_link}", file=sys.stderr)
    except Exception as e:
        results.append({"calendar_id": cal_id, "status": "failed", "error": str(e)})
        print(f"❌ {cal_id}: {e}", file=sys.stderr)

print(json.dumps({"published": results}))
