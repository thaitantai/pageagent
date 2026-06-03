#!/usr/bin/env python3
import subprocess, json

URL = "https://graph.facebook.com/v21.0/883890888134656/posts?fields=message,created_time,permalink_url&access_token=EAGJVdGWynR4BRjpwqVFhMGoNlr8EVjtgGrl2Edyh73Ci4Sa1rvSHZBTiBQXLvuIBGapfkCBtnYjPVoUzXbXSsVjbiJRp9oEyzPgZAzqVZALWJ5r6Katist9m8bZC71ZCD5FOtHfEOcDf9MtiWCvWLBVnKGIFgL0RTuXdecJDMv3yhlPrQd6BxWzSxtY7n6xMZAEwyTZB7v8HZCbHhUBXQd4gCVhNkx2rt5srVoVkwxwZD&limit=5"

r = subprocess.run(["curl", "-s", URL], capture_output=True, text=True, timeout=30)
data = json.loads(r.stdout)

for p in data.get("data", []):
    msg = (p.get("message") or "")
    print("=== " + p.get("created_time","")[:10] + " ===")
    print(msg[:400])
    print()
