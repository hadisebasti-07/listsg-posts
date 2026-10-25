#!/usr/bin/env python3
"""
Publish queued posts to Instagram (Instagram API with Instagram Login).

Usage:
  python3 publish.py next              # publish the first approved, unposted item
  python3 publish.py next --dry-run    # show what would be posted, call nothing
  python3 publish.py check <item>      # create upload containers, never publish
  python3 publish.py refresh-token     # print a refreshed 60-day token
  python3 publish.py status            # list the queue

Env: IG_ACCESS_TOKEN, MEDIA_BASE (public URL of this repo's Pages site).
Each queue/<item>/ holds 01..NN media (.jpg/.mp4), caption.txt and post.json.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GRAPH = "https://graph.instagram.com/v21.0"
QUEUE = Path(__file__).parent / "queue"
MEDIA_EXT = {".jpg", ".jpeg", ".mp4", ".mov"}


def token() -> str:
    t = os.getenv("IG_ACCESS_TOKEN")
    if not t:
        sys.exit("IG_ACCESS_TOKEN is not set")
    return t


def api(method: str, path: str, **params) -> dict:
    params["access_token"] = token()
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.read().decode()}") from None


# ── Queue ─────────────────────────────────────────────────────────────────────

def items() -> list[Path]:
    return sorted(p for p in QUEUE.iterdir() if (p / "post.json").exists())


def meta(item: Path) -> dict:
    return json.loads((item / "post.json").read_text())


def media_files(item: Path) -> list[Path]:
    return sorted(f for f in item.iterdir() if f.suffix.lower() in MEDIA_EXT)


def media_url(item: Path, f: Path) -> str:
    base = os.getenv("MEDIA_BASE")
    if not base:
        sys.exit("MEDIA_BASE is not set")
    return f"{base.rstrip('/')}/queue/{item.name}/{f.name}"


# ── Containers ────────────────────────────────────────────────────────────────

def wait_ready(cid: str, label: str, timeout: int = 600) -> None:
    start = time.time()
    while True:
        s = api("GET", cid, fields="status_code,status")
        code = s.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"{label}: {code} {s.get('status')}")
        if time.time() - start > timeout:
            raise RuntimeError(f"{label}: still {code} after {timeout}s")
        time.sleep(5)


def child(item: Path, f: Path, carousel: bool) -> str:
    url = media_url(item, f)
    video = f.suffix.lower() in (".mp4", ".mov")
    p = {"is_carousel_item": "true"} if carousel else {}
    if video:
        p.update(media_type="VIDEO" if carousel else "REELS", video_url=url)
    else:
        p.update(image_url=url)
    return api("POST", "me/media", **p)["id"]


def build(item: Path) -> str:
    """Create all containers for an item and return the top-level container id."""
    files = media_files(item)
    caption = (item / "caption.txt").read_text().strip()
    if not files:
        raise RuntimeError(f"{item.name}: no media")
    if len(files) == 1:
        raise RuntimeError("single-media posts not supported yet")
    if len(files) > 10:
        raise RuntimeError(f"{item.name}: {len(files)} files, carousel max is 10")
    kids = []
    for f in files:
        cid = child(item, f, carousel=True)
        print(f"  {f.name} → container {cid}")
        kids.append((f.name, cid))
    for name, cid in kids:
        wait_ready(cid, name)
        print(f"  {name} ready")
    top = api("POST", "me/media", media_type="CAROUSEL",
              children=",".join(c for _, c in kids), caption=caption)["id"]
    wait_ready(top, "carousel")
    return top


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status() -> None:
    for item in items():
        m = meta(item)
        state = "posted " + m["posted_at"][:10] if m.get("posted_at") else \
                "approved" if m.get("approved") else "awaiting approval"
        print(f"{item.name:40} {len(media_files(item))} files  {state}")


def next_item() -> Path | None:
    for item in items():
        m = meta(item)
        if m.get("approved") and not m.get("posted_at"):
            return item
    return None


def cmd_next(dry: bool) -> None:
    item = next_item()
    if not item:
        # non-zero exit makes GitHub email the repo owner
        sys.exit("Nothing approved in the queue — no post went out.")
    print(f"Next: {item.name}")
    for f in media_files(item):
        print(f"  {f.name}  {media_url(item, f) if os.getenv('MEDIA_BASE') else ''}")
    if dry:
        print("(dry run — nothing posted)")
        return
    top = build(item)
    post_id = api("POST", "me/media_publish", creation_id=top)["id"]
    link = api("GET", post_id, fields="permalink").get("permalink", "")
    m = meta(item)
    m.update(posted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             media_id=post_id, permalink=link)
    (item / "post.json").write_text(json.dumps(m, indent=2) + "\n")
    print(f"Posted: {link}")


def cmd_check(name: str) -> None:
    item = QUEUE / name
    top = build(item)
    print(f"All containers accepted (carousel {top}). Nothing was published; "
          "unpublished containers expire after 24 h.")


def cmd_refresh() -> None:
    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token",
                                "access_token": token()})
    with urllib.request.urlopen(f"https://graph.instagram.com/refresh_access_token?{q}") as r:
        d = json.load(r)
    print(d["access_token"])
    print(f"expires in {d['expires_in'] // 86400} days", file=sys.stderr)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "next":
        cmd_next("--dry-run" in a)
    elif a[0] == "check" and len(a) > 1:
        cmd_check(a[1])
    elif a[0] == "refresh-token":
        cmd_refresh()
    elif a[0] == "status":
        cmd_status()
    else:
        sys.exit(__doc__)
