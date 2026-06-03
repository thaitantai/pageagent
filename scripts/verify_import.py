#!/usr/bin/env python3
"""Verify import_post_history results in Google Sheets."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fanpage_agent.config import Settings
from google.oauth2 import service_account
from googleapiclient.discovery import build

settings = Settings.from_env(root_dir=ROOT)
creds = service_account.Credentials.from_service_account_file(
    settings.google_service_account_file,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
service = build("sheets", "v4", credentials=creds)
tab = f"{settings.google_sheets_tabs_prefix}_post_history"

result = service.spreadsheets().values().get(
    spreadsheetId=settings.google_sheets_id,
    range=f"{tab}!A:H"
).execute()

rows = result.get("values", [])
print(f"Total rows (incl. header): {len(rows)}")
if rows:
    print(f"\nHeader: {rows[0]}")
    print(f"\nFirst 3 entries:")
    for r in rows[1:4]:
        print(f"  {r[0]} | {r[3]}/{r[4]} | {r[1][:50]}...")
    print(f"\nLast 3 entries:")
    for r in rows[-3:]:
        print(f"  {r[0]} | {r[3]}/{r[4]} | {r[1][:50]}...")
    
    # Summary
    pillars = {}
    for r in rows[1:]:
        p = r[3] if len(r) > 3 else "?"
        pillars[p] = pillars.get(p, 0) + 1
    print(f"\nPillars: {json.dumps(pillars, ensure_ascii=False)}")
    print("\n✅ Google Sheets verification complete!")
