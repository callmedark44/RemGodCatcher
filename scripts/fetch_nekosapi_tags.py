#!/usr/bin/env python3
"""Fetch NekosAPI v4 tags via offset pagination + concurrent workers.

v4 API has no /tags endpoint — tags only exist embedded in image responses.
/v4/images returns {"items": [...], "count": N}. Total is ~12877.
Strategy: fetch pages of 100 (max) concurrently, collect unique tags.
"""
import os, json, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "database", "nekosapi_tag_names.json")
CHECKPOINT = os.path.join(HERE, "database", "nekosapi_tags_checkpoint.json")
PAGE_SIZE = 100  # max per request
MAX_WORKERS = 20
SLEEP = 0.3
API_BASE = "https://api.nekosapi.com/v4"
RATINGS = ["safe", "suggestive", "borderline", "explicit"]


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def fetch_page(offset, limit=PAGE_SIZE):
    """Fetch one page of images, return list of image dicts (or None on rate-limit)."""
    try:
        resp = requests.get(
            f"{API_BASE}/images",
            params={"limit": limit, "offset": offset, "rating": RATINGS},
            timeout=20,
        )
        if resp.status_code in (403, 429):
            return None
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        log(f"  Error at offset {offset}: {e}")
        return None


def extract_tags(items):
    """Extract unique tags from a batch of image dicts."""
    tags = set()
    for img in items:
        for t in img.get("tags", []):
            if t:
                tags.add(t)
    return tags


def get_total():
    resp = requests.get(
        f"{API_BASE}/images", params={"limit": 1, "rating": RATINGS}, timeout=20
    )
    return resp.json().get("count", 0)


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            d = json.load(f)
            return d.get("next_offset", 0), set(d.get("tags", []))
    return 0, set()


def save_checkpoint(next_offset, tags):
    with open(CHECKPOINT, "w") as f:
        json.dump({"next_offset": next_offset, "tags": list(tags)}, f)


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(os.path.dirname(DB), exist_ok=True)

    if refresh:
        total = get_total()
        log(f"Total images in DB: {total}")
        next_offset = 0
        all_tags = set()
        if os.path.exists(CHECKPOINT):
            os.remove(CHECKPOINT)
    else:
        next_offset, existing = load_checkpoint()
        all_tags = existing
        total = get_total()
        log(f"Resuming from offset {next_offset}, {len(all_tags)} existing tags, total={total}")

    log(f"Starting: workers={MAX_WORKERS}, page_size={PAGE_SIZE}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while next_offset < total:
            save_checkpoint(next_offset, all_tags)

            # Submit batch of page fetches
            batch_offsets = []
            while len(batch_offsets) < MAX_WORKERS and next_offset < total:
                batch_offsets.append(next_offset)
                next_offset += PAGE_SIZE

            futures = {executor.submit(fetch_page, o, PAGE_SIZE): o for o in batch_offsets}

            has_data = False
            for fut in as_completed(futures):
                items = fut.result()
                if items is None:
                    time.sleep(5)
                    # retry not needed; just skip — ThreadPoolExecutor will naturally progress
                    continue
                if items:
                    has_data = True
                    all_tags |= extract_tags(items)

            if not has_data:
                log(f"Empty batch at offset {next_offset}, stopping.")
                break

            log(f"Progress: offset={next_offset}/{total}, {len(all_tags)} unique tags")
            time.sleep(SLEEP)

    all_tags = sorted(all_tags)
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(all_tags, f, indent=2, ensure_ascii=False)

    save_checkpoint(next_offset, all_tags)
    log(f"=== DONE ===")
    log(f"Wrote {len(all_tags)} tags to {DB}")


if __name__ == "__main__":
    main()