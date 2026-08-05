#!/usr/bin/env python3
"""Fetch the complete Gelbooru tag list from gelbooru.com for autocomplete.

Gelbooru's tag list paginates at 1000 tags per page. URL format:
  https://gelbooru.com/index.php?page=tags&s=list&pid=0
  https://gelbooru.com/index.php?page=tags&s=list&pid=1000
  ...

Each page returns an HTML table where every row's <a> tag contains the tag
name. The script parses these out, writes them to database/gelbooru_tag_names.json,
and checkpoints for resume.

Usage: python3 scripts/fetch_gelbooru_tags.py [--refresh]
"""
import os, re, json, time, sys
import urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "database", "gelbooru_tag_names.json")
CHECKPOINT = os.path.join(HERE, "database", "gelbooru_tags_checkpoint.txt")
PAGE_SIZE = 1000
SLEEP = 0.5

# Match tag links in the tag list table rows
# Format: <a href="/index.php?page=tags&s=list&pid=...&tag=example_tag">example_tag</a>
TAG_RE = re.compile(r'<a href="[^"]*tag=([^&"]+)"[^>]*>([^<]+)</a>')


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_page(page):
    """Fetch one tag list page, return list of tag names."""
    pid = (page - 1) * PAGE_SIZE
    url = f"https://gelbooru.com/index.php?page=tags&s=list&pid={pid}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://gelbooru.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            log(f"  HTTP {e.code} — rate limited, waiting 10s...")
            time.sleep(10)
            return fetch_page(page)
        log(f"  HTTP {e.code} — stopping")
        return []
    except Exception as e:
        log(f"  Error: {e} — skipping page {page}")
        return []

    tags = []
    for m in TAG_RE.finditer(html):
        # m.group(1) is URL-encoded tag from href, m.group(2) is display name
        # Prefer the display name (already decoded) unless empty
        display = m.group(2).strip()
        if display:
            tags.append(display)
    return tags


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            d = json.load(f)
            return d.get("next_page", 1), d.get("total", 0)
    return 1, 0


def save_checkpoint(next_page, total):
    with open(CHECKPOINT, "w") as f:
        json.dump({"next_page": next_page, "total": total}, f)


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(os.path.dirname(DB), exist_ok=True)

    # Load existing tags (for resume/append)
    all_tags = []
    if os.path.exists(DB) and not refresh:
        with open(DB, encoding="utf-8") as f:
            all_tags = json.load(f)
        log(f"Resuming with {len(all_tags)} existing tags")

    next_page, total = load_checkpoint()
    if refresh or not os.path.exists(CHECKPOINT):
        next_page = 1

    log(f"Starting from page {next_page} (PAGE_SIZE={PAGE_SIZE})")
    seen = set(all_tags)
    batches_done = 0

    while True:
        if (batches_done + 1) % 20 == 1:
            save_checkpoint(next_page, len(all_tags))

        tags = fetch_page(next_page)
        if not tags:
            log(f"No tags on page {next_page} — reached end of tag list")
            break

        new = 0
        for t in tags:
            if t not in seen:
                seen.add(t)
                all_tags.append(t)
                new += 1

        batches_done += 1
        log(f"page {next_page}: {len(tags)} raw, {new} new | total={len(all_tags)}, seen={len(seen)}")

        if len(tags) < PAGE_SIZE:
            log("Fewer tags than PAGE_SIZE — reached end of tag list")
            break

        next_page += 1
        time.sleep(SLEEP)

    all_tags.sort()
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(all_tags, f, indent=2, ensure_ascii=False)

    log(f"=== DONE ===")
    log(f"Wrote {len(all_tags)} tags to {DB}")
    save_checkpoint(next_page, len(all_tags))


if __name__ == "__main__":
    main()
