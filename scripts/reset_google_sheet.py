"""Reset Google Sheet data — clear all data rows below headers in fp_test_* tabs.

Usage: python scripts/reset_google_sheet.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ── load .env ──────────────────────────────────────────────
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
env_vars: dict[str, str] = {}
for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env_vars[key.strip()] = value.strip().strip("\"'")

google_sheets_id = env_vars.get("GOOGLE_SHEETS_ID", "")
sa_file = env_vars.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
prefix = env_vars.get("GOOGLE_SHEETS_TABS_PREFIX", "")

if not google_sheets_id:
    sys.exit("ERROR: GOOGLE_SHEETS_ID not found in .env")
if not sa_file:
    sys.exit("ERROR: GOOGLE_SERVICE_ACCOUNT_FILE not found in .env")

sa_path = Path(sa_file)
if not sa_path.is_absolute():
    sa_path = Path(__file__).resolve().parent.parent / sa_file
if not sa_path.exists():
    sys.exit(f"ERROR: Service account file not found at {sa_path}")

# ── build client ───────────────────────────────────────────
creds = Credentials.from_service_account_file(
    str(sa_path),
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)
service = build("sheets", "v4", credentials=creds, cache_discovery=False)

# ── list tabs ──────────────────────────────────────────────
spreadsheet = service.spreadsheets().get(spreadsheetId=google_sheets_id).execute()
all_sheets = spreadsheet.get("sheets", [])
target_tabs = [
    s["properties"]["title"]
    for s in all_sheets
    if s["properties"]["title"].startswith(f"{prefix}_")
]

if not target_tabs:
    print("No tabs with prefix '{}_*' found.".format(prefix))
    sys.exit(0)

print(f"Spreadsheet: {google_sheets_id}")
print(f"Prefix: {prefix}")
print(f"Tabs to reset: {len(target_tabs)}\n")

# ── reset each tab ─────────────────────────────────────────
for tab_name in target_tabs:
    # Read header
    result = service.spreadsheets().values().get(
        spreadsheetId=google_sheets_id,
        range=f"{tab_name}!1:1",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    headers = result.get("values", [[]])[0]

    # Count rows
    all_data = service.spreadsheets().values().get(
        spreadsheetId=google_sheets_id,
        range=f"{tab_name}!A:Z",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    all_values = all_data.get("values", [])
    data_rows = len(all_values) - 1  # exclude header

    print(f"• {tab_name}: {data_rows} data rows, {len(headers)} cols")

    if data_rows <= 0:
        print("  → nothing to clear")
        continue

    # Show sample
    for i in [0, 1, -1]:
        if 0 <= i < len(all_values):
            label = "header" if i == 0 else "first data" if i == 1 else "last data"
            vals = [str(v)[:25] for v in all_values[i]]
            print(f"  {label}: {vals}")

    # Clear entire tab
    service.spreadsheets().values().clear(
        spreadsheetId=google_sheets_id,
        range=tab_name,
        body={},
    ).execute()

    # Re-write header
    service.spreadsheets().values().update(
        spreadsheetId=google_sheets_id,
        range=f"{tab_name}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()
    print(f"  ✅ cleared\n")

print("Done — Google Sheet reset complete.")
