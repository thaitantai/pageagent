#!/usr/bin/env python3
import os, sys, subprocess, json

PAGE_ID = os.environ.get("FB_PAGE_ID", "883890888134656")
LIMIT = int(os.environ.get("FB_POST_LIMIT", "25"))
TOKEN = os.environ.get("FB_PAGE_TOKEN")

if not TOKEN:
    print("ERROR: Set FB_PAGE_TOKEN env var", file=sys.stderr)
    sys.exit(1)

url = (
    f"https://graph.facebook.com/v21.0/{PAGE_ID}/posts"
    f"?fields=message,created_time,permalink_url,shares,"
    f"likes.limit(0).summary(true),comments.limit(0).summary(true)"
    f"&access_token={TOKEN}&limit={LIMIT}"
)

r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
data = json.loads(r.stdout)

if "error" in data:
    print(json.dumps(data["error"], indent=2), file=sys.stderr)
    sys.exit(1)

json.dump(data.get("data", []), sys.stdout, indent=2, ensure_ascii=False)
