"""Data-fetch tools: Facebook data retrieval and metric recording."""

from __future__ import annotations

from fanpage_agent.adapters.facebook_client import FacebookClient
from fanpage_agent.tools.data.data_fetch import DataFetchTool
from fanpage_agent.tools.data.metrics_auto_fetch import MetricsAutoFetchTool

from .helpers import DEFAULT_COMMENT, local_store, settings


def tool_fetch_fb_comments() -> dict:
    s = settings()
    fb = FacebookClient(s)
    try:
        posts = fb.get_page_posts(limit=5)
    except Exception as e:
        return {"error": f"Failed to fetch posts: {e}"}
    all_comments = []
    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            continue
        try:
            comments = fb.get_comments(post_id, limit=20)
        except Exception:
            comments = []
        for c in comments:
            c["post_id"] = post_id
            all_comments.append(c)
    return {"total_comments": len(all_comments), "posts_checked": len(posts)}


def tool_fetch_fb_data(
    post_limit: int = 90,
    comment_posts: int = 20,
    comment_limit: int = 25,
    skip_comments: bool = False,
) -> dict:
    s = settings()
    store = local_store()
    service = DataFetchTool(
        settings=s,
        store=store,
        comment_csv=str(DEFAULT_COMMENT) if not skip_comments else None,
    )
    result = service.fetch_all(
        post_limit=post_limit,
        comment_posts=comment_posts if not skip_comments else 0,
        comment_limit=comment_limit,
    )
    return result


def tool_record_post_metrics() -> dict:
    s = settings()
    store = local_store()
    service = MetricsAutoFetchTool(settings=s)
    result = service.auto_fetch(store=store)
    return result


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_fb_comments",
            "description": "Fetch recent comments from Facebook page posts",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_fb_data",
            "description": "Fetch full Facebook data (posts, metrics, comments) and persist to store (Google Sheets or local CSV). Agents read from the store; this tool populates it. Use after publish or periodically to keep store fresh.",
            "parameters": {
                "type": "object",
                "properties": {
                    "post_limit": {
                        "type": "integer",
                        "description": "Number of recent posts to fetch (default 90)",
                    },
                    "comment_posts": {
                        "type": "integer",
                        "description": "How many of those posts to fetch comments from (default 20)",
                    },
                    "comment_limit": {
                        "type": "integer",
                        "description": "Max comments per post (default 25)",
                    },
                    "skip_comments": {
                        "type": "boolean",
                        "description": "Skip comment fetch (default false)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_post_metrics",
            "description": "Auto-fetch and record metrics for recently published posts",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

REGISTRY_BUILDERS = {
    "fetch_fb_comments": (tool_fetch_fb_comments, {}),
    "fetch_fb_data": (
        tool_fetch_fb_data,
        {"post_limit": 90, "comment_posts": 20, "comment_limit": 25, "skip_comments": False},
    ),
    "record_post_metrics": (tool_record_post_metrics, {}),
}
