#!/usr/bin/env python3
"""Fetch the complete Gelbooru tag list from gelbooru.com for autocomplete.

Gelbooru's tag list paginates at 50 tags per page. URL format:
  https://gelbooru.com/index.php?page=tags&s=list&pid=0
  https://gelbooru.com/index.php?page=tags&s=list&pid=50
  ...

Each page returns an HTML table where rows contain:
  <span class="tag-type-XXX"><a href="index.php?page=post&s=list&tags=TAG_NAME">DISPLAY_NAME</a></span> <span class="tag-count">COUNT</span>

The script normalizes tag names to Gelbooru's underscore format (spaces->_ )
and writes them to database/gelbooru_tag_names.json, with checkpoints for resume.

Usage: python3 scripts/fetch_gelbooru_tags.py [--refresh]
"""
import os, re, json, time, sys, html
import urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "database", "gelbooru_tag_names.json")
CHECKPOINT = os.path.join(HERE, "database", "gelbooru_tags_checkpoint.txt")
PAGE_SIZE = 50  # Gelbooru returns 50 tags per page in the tag list
SLEEP = 0.5
MAX_WORKERS = 20
MAX_PAGES = 5000  # Safeguard — should never hit this

# Match the tag display name from the tag list table rows
# Format: <span class="tag-type-XXX"><a href="...&tags=TAG_NAME">DISPLAY_NAME</a></span> <span class="tag-count">COUNT</span>
# We capture the display name between <a> and </a>, excluding "edit" links
TAG_RE = re.compile(r'<a href="[^"]*tags=[^"]*">([^<]*(?:</a>[^<]*<[^>]*>\\s*[^<]*<[^>]*>)*<span[^>]*>([^<]+)</span>)')
# Simpler: match the display text directly from <a ...>TEXT</a>
# But there are multiple <a> per row (post link + edit link)
# Use the tag-count span as an anchor
TAG_ROW_RE = re.compile(
    r'<span class="tag-type-[^"]+">'
    r'<a href="index\.php\?page=post&amp;s=list&amp;tags=([^"]+)">([^<]+)</a>'
    r'</span>\s*<span class="tag-count">[^<]*</span>'
)


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_page(page):
    """Fetch one tag list page, return list of tag names (underscore format)."""
    pid = (page - 1) * PAGE_SIZE
    url = f"https://gelbooru.com/index.php?page=tags&s=list&pid={pid}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://gelbooru.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            html_content = r.read().decode("utf-8", errors="replace")
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
    for m in TAG_ROW_RE.finditer(html_content):
        url_encoded_tag = m.group(1)
        display_name = m.group(2).strip()
        
        # Decode HTML entities
        display_name = html.unescape(display_name)
        
        # Normalize: spaces to underscores (Gelbooru tag format)
        tag = display_name.replace(" ", "_")
        
        if tag:
            tags.append(tag)
    
    return tags


def fetch_page_with_retry(page, max_retries=3):
    """Fetch a page with retry logic for SSL/network errors."""
    for attempt in range(max_retries):
        tags = fetch_page(page)
        if tags is not None:
            return tags
        if attempt < max_retries - 1:
            log(f"  Retrying page {page} (attempt {attempt + 2}/{max_retries})...")
            time.sleep(3)
    return []


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

    log(f"Starting from page {next_page} (PAGE_SIZE={PAGE_SIZE}, WORKERS={MAX_WORKERS})")
    seen = set(all_tags)
    batches_done = 0
    consecutive_empty = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while next_page <= MAX_PAGES:
            if (batches_done + 1) % 20 == 1:
                save_checkpoint(next_page, len(all_tags))

            # Submit batch of pages
            futures = {}
            batch_size = min(MAX_WORKERS, MAX_PAGES - next_page + 1)
            for i in range(batch_size):
                page_num = next_page + i
                futures[executor.submit(fetch_page_with_retry, page_num)] = page_num

            # Process results in order
            has_data_this_batch = False
            
            for page_num in range(next_page, next_page + batch_size):
                future = {v: k for k, v in futures.items()}[page_num]
                try:
                    tags = future.result()
                    if not tags:
                        continue
                    
                    has_data_this_batch = True
                    consecutive_empty = 0
                    new = 0
                    for t in tags:
                        if t not in seen:
                            seen.add(t)
                            all_tags.append(t)
                            new += 1
                    
                    log(f"page {page_num}: {len(tags)} raw, {new} new | total={len(all_tags)}, seen={len(seen)}")
                    batches_done += 1
                except Exception as e:
                    log(f"Page {page_num}: error — {e}")

            if not has_data_this_batch:
                consecutive_empty += 1
                log(f"Empty batch at page {next_page}, streak={consecutive_empty}")
                if consecutive_empty >= 3:
                    log("3 consecutive empty batches — reached end of tag list")
                    break

            if batches_done >= MAX_PAGES:
                break

            next_page += batch_size
            time.sleep(SLEEP)

    all_tags.sort()
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(all_tags, f, indent=2, ensure_ascii=False)

    log(f"=== DONE ===")
    log(f"Wrote {len(all_tags)} tags to {DB}")
    save_checkpoint(next_page, len(all_tags))


if __name__ == "__main__":
    main()
