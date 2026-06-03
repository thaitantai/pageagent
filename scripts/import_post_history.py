#!/usr/bin/env python3
"""
import_post_history.py — Import Facebook Page posts into Google Sheets.

Usage:
    FB_PAGE_TOKEN="..." python3 scripts/import_post_history.py

Transforms Facebook posts → PostHistoryEntry format and writes
to the fp_test_post_history tab in Google Sheets.
"""

import os, sys, subprocess, json, csv, io
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOKEN = os.environ.get("FB_PAGE_TOKEN")
if not TOKEN:
    print("ERROR: Set FB_PAGE_TOKEN env var", file=sys.stderr)
    sys.exit(1)

PAGE_ID = os.environ.get("FB_PAGE_ID", "883890888134656")
LIMIT = int(os.environ.get("FB_POST_LIMIT", "100"))

# ── 1. Fetch posts from Facebook Graph API ────────────────────────────
def fetch_posts() -> list[dict]:
    url = (
        f"https://graph.facebook.com/v21.0/{PAGE_ID}/posts"
        f"?fields=message,created_time,permalink_url,shares,"
        f"likes.limit(0).summary(true),comments.limit(0).summary(true)"
        f"&access_token={TOKEN}&limit={LIMIT}"
    )
    all_posts = []
    while url:
        r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=45)
        data = json.loads(r.stdout)
        if "error" in data:
            print(f"API ERROR: {json.dumps(data['error'], indent=2)}", file=sys.stderr)
            sys.exit(1)
        all_posts.extend(data.get("data", []))
        paging = data.get("paging", {})
        url = paging.get("next", "")
    return all_posts


# ── 2. Classify post ──────────────────────────────────────────────────
# Heuristic classification based on message content

OUTFIT_KEYWORDS = ["outfit", "mix", "match", "mix-match", "phối đồ", "lên đồ",
                   "set đồ", "item", "top", "bottom", "accessories", "phụ kiện"]
LOCAL_BRAND_KEYWORDS = ["local brand", "thương hiệu", "brand", "nước nhà",
                        "thời trang việt", "nội địa", "park mall"]
SHOWROOM_KEYWORDS = ["park mall", "showroom", "cửa hàng", "ghé", "địa chỉ",
                     "chi nhánh", "trải nghiệm thực tế", "thử đồ"]
LIFESTYLE_KEYWORDS = ["sạc pin", "cạn pin", "mệt", "kiệt sức", "nghỉ ngơi",
                      "động lực", "so sánh", "bỏ cuộc", "tinh thần", "sống chậm"]
HASHTAG_PATTERNS = ["#xuhuongfb", "#thoitrang", "#aokhoacnu", "#aodaivietnam",
                    "#outfit", "#genz", "#lenam"]
TIKTOK_KEYWORDS = ["tiktok", "minhthushop"]

PILLAR_CATEGORIES = {
    "outfit_guide": {
        "keywords": OUTFIT_KEYWORDS,
        "substance": ["outfit_idea", "styling_tip", "mix_and_match"],
        "objective_hint": "engagement_ask"
    },
    "local_brand_promo": {
        "keywords": LOCAL_BRAND_KEYWORDS,
        "substance": ["brand_showcase", "local_fashion"],
        "objective_hint": "awareness"
    },
    "showroom_promo": {
        "keywords": SHOWROOM_KEYWORDS,
        "substance": ["store_visit", "retail_experience"],
        "objective_hint": "conversion"
    },
    "lifestyle": {
        "keywords": LIFESTYLE_KEYWORDS,
        "substance": ["mental_health", "self_care", "motivation"],
        "objective_hint": "engagement_ask"
    },
    "short_tip": {
        "keywords": HASHTAG_PATTERNS,
        "substance": ["fashion_tip", "trend_alert"],
        "objective_hint": "awareness"
    },
    "external_link": {
        "keywords": TIKTOK_KEYWORDS,
        "substance": ["cross_platform"],
        "objective_hint": "conversion"
    }
}

OBJECTIVE_ORDER = ["engagement_ask", "awareness", "conversion"]

def classify_post(message: str) -> tuple[str, str, str]:
    """Returns (pillar, objective, hook)."""
    msg_lower = (message or "").lower()
    
    # Pillar classification
    pillar = "outfit_guide"  # default
    pillar_score = {}
    for name, config in PILLAR_CATEGORIES.items():
        score = sum(1 for kw in config["keywords"] if kw in msg_lower)
        if score > 0:
            pillar_score[name] = score
    if pillar_score:
        pillar = max(pillar_score, key=lambda k: pillar_score[k])
    
    # Objective classification by content
    has_question = "?" in message[-200:] if message else False
    has_cta = any(w in msg_lower for w in ["ghé", "link", "comment", "nhấn", "đến ngay"])
    
    if has_question:
        objective = "engagement_ask"
    elif pillar == "showroom_promo" or pillar == "external_link":
        objective = "conversion"
    else:
        objective = PILLAR_CATEGORIES[pillar]["objective_hint"]
    
    # Hook = first sentence or first 120 chars
    hook = ""
    if message:
        sentences = message.replace("\n", " ").split(".")
        for s in sentences:
            s = s.strip()
            if len(s) > 20:
                hook = s[:150]
                break
        if not hook:
            hook = message[:150]
    
    return pillar, objective, hook


def extract_topic(message: str) -> str:
    """Extract main topic from message."""
    if not message:
        return ""
    # Take first meaningful sentence
    lines = [l.strip() for l in message.split("\n") if l.strip()]
    for line in lines:
        line = line.replace("?", " ?").replace("!", " !")
        if len(line) > 30 and line[0].isupper():
            # Remove hashtags
            clean = " ".join(w for w in line.split() if not w.startswith("#"))
            return clean[:120]
    return lines[0][:120] if lines else ""


# ── 3. Routes — write to Google Sheets ────────────────────────────────
from fanpage_agent.config import Settings
from fanpage_agent.adapters.store_factory import build_store

def write_to_store(entries: list[dict]) -> None:
    settings = Settings.from_env(root_dir=ROOT)
    
    # If using Google Sheets, import needed functions
    if settings.store_backend == "google":
        from google.oauth2 import service_account
        from googleapiclient.discovery import build as gbuild
        
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        service = gbuild("sheets", "v4", credentials=creds)
        sheet_id = settings.google_sheets_id
        tab_name = f"{settings.google_sheets_tabs_prefix}_post_history"
        
        # Check if tab exists, if not create it
        spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing_tabs = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
        
        if tab_name not in existing_tabs:
            body = {"requests": [{
                "addSheet": {"properties": {"title": tab_name}}
            }]}
            service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
            print(f"  Created new tab: {tab_name}")
        
        # Read existing published_at values to avoid duplicates
        range_name = f"{tab_name}!A:A"
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id, range=range_name
            ).execute()
            existing_dates = set()
            for row in result.get("values", []):
                if row:
                    existing_dates.add(row[0].strip())
        except Exception:
            existing_dates = set()
        
        # Write headers if empty
        headers = ["published_at", "topic", "hook", "pillar", "objective",
                    "permalink", "reach", "engagement_rate"]
        
        # Filter out duplicates
        new_entries = [e for e in entries if e["published_at"] not in existing_dates]
        
        if not new_entries:
            print("  No new entries to add (all already in sheet).")
            return
        
        rows = [[
            e["published_at"],
            e["topic"],
            e["hook"],
            e["pillar"],
            e["objective"],
            e["permalink"],
            e.get("reach", 0),
            e.get("engagement_rate", 0.0),
        ] for e in new_entries]
        
        # If tab has no data, write headers first
        write_range = f"{tab_name}!A:H"
        if not existing_dates:
            rows.insert(0, headers)
        
        body = {"values": rows}
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=write_range,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        
        print(f"  Wrote {len(new_entries)} entries to Google Sheets tab '{tab_name}'")
        if existing_dates:
            print(f"  Skipped {len(entries) - len(new_entries)} duplicates")
        
        # Also update local CSV for fallback
        history_csv = ROOT / "data" / "real" / "post_history.csv"
        write_mode = "w" if not existing_dates else "a"
        fieldnames = headers
        with open(history_csv, write_mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_mode == "w":
                writer.writeheader()
            for e in new_entries:
                writer.writerow(e)
        print(f"  Also wrote to local CSV: {history_csv}")
    else:
        # Local CSV only
        history_csv = ROOT / "data" / "real" / "post_history.csv"
        fieldnames = ["published_at", "topic", "hook", "pillar", "objective",
                      "permalink", "reach", "engagement_rate"]
        
        # Read existing dates to avoid duplicates
        existing_dates = set()
        if history_csv.exists():
            with open(history_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_dates.add(row.get("published_at", "").strip())
        
        new_entries = [e for e in entries if e["published_at"] not in existing_dates]
        if not new_entries:
            print("  No new entries to add (all already in CSV).")
            return
        
        write_mode = "a" if existing_dates else "w"
        with open(history_csv, write_mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_mode == "w":
                writer.writeheader()
            for e in new_entries:
                writer.writerow(e)
        
        print(f"  Wrote {len(new_entries)} entries to {history_csv}")
        if existing_dates:
            print(f"  Skipped {len(entries) - len(new_entries)} duplicates")


# ── Main ──────────────────────────────────────────────────────────────
def main() -> int:
    print(f"Fetching up to {LIMIT} posts from Facebook Page {PAGE_ID}...")
    posts = fetch_posts()
    print(f"  Fetched {len(posts)} posts")
    
    if not posts:
        print("No posts found.")
        return 0
    
    entries = []
    for post in posts:
        message = post.get("message", "")
        created = post.get("created_time", "")
        permalink = post.get("permalink_url", "")
        likes = post.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
        
        # Format published_at
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            published = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            published = created[:16]
        
        pillar, objective, hook = classify_post(message)
        topic = extract_topic(message)
        
        entry = {
            "published_at": published,
            "topic": topic,
            "hook": hook,
            "pillar": pillar,
            "objective": objective,
            "permalink": permalink,
            "reach": 0,  # Not available without insights permission
            "engagement_rate": 0.0,
        }
        entries.append(entry)
        
        # Print preview
        preview = f"  [{published}] {pillar}/{objective} | {topic[:60]}..."
        print(preview)
    
    print(f"\nTotal entries to write: {len(entries)}")
    
    write_to_store(entries)
    
    print("\n✅ Import complete!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
