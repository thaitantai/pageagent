#!/usr/bin/env python3
"""Fetch full post messages from Facebook page for analysis."""
import os, subprocess, json

TOKEN=os.environ.get("FB_PAGE_TOKEN")
PAGE_ID = os.environ.get("FB_PAGE_ID", "883890888134656")

url = (
    f"https://graph.facebook.com/v21.0/{PAGE_ID}/posts"
    f"?fields=message,created_time,permalink_url"
    f"&access_token={TOKEN}&limit=10"
)
r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
data = json.loads(r.stdout)

for p in data.get("data", []):
    msg = p.get("message", "")
    created = p.get("created_time", "")[:10]
    print(f"=== {created} ===")
    # Print first 400 chars
    print(msg[:400])
    print()
