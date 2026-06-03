# Fetch recent posts for brand analysis
import subprocess, json

TOKEN = "EAGJVdGWynR4BRjpwqVFhMGoNlr8EVjtgGrl2Edyh73Ci4Sa1rvSHZBTiBQXLvuIBGapfkCBtnYjPVoUzXbXSsVjbiJRp9oEyzPgZAzqVZALWJ5r6Katist9m8bZC71ZCD5FOtHfEOcDf9MtiWCvWLBVnKGIFgL0RTuXdecJDMv3yhlPrQd6BxWzSxtY7n6xMZAEwyTZB7v8HZCbHhUBXQd4gCVhNkx2rt5srVoVkwxwZD"
PAGE_ID = "883890888134656"

url = f"https://graph.facebook.com/v21.0/{PAGE_ID}/posts?fields=message,created_time,permalink_url&access_token={TOKEN}&limit=8"
r = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=30)
data = json.loads(r.stdout)

for p in data.get("data", []):
    msg = (p.get("message") or "")
    print(f"=== {p.get('created_time','')[:10]} ===")
    print(msg[:400])
    print()
