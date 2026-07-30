#!/usr/bin/env python3
"""Scrape e-shuushuu user profiles from /users/{id}, save to database/eshuushuu_users.json.

Starts at id 1, walks upward. Stops after 5000 consecutive 404s.
Extracts profile data from embedded SvelteKit __sveltekit_ data.
Multi-worker with checkpoint/resume, per-batch logging.

Usage: python3 scripts/scrape_eshuushuu_users.py
"""

import os, re, json, time, sys, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "eshuushuu_users.json")
CHECKPOINT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "eshuushuu_users_checkpoint.txt")
WORKERS = 32
CONSECUTIVE_404_LIMIT = 5000

# Regex to extract the profileUser object from embedded SvelteKit data
# Handles nested braces (interests can contain {} characters)
PROFILE_RE = re.compile(r'profileUser:(\{(?:[^{}]|\{[^{}]*\})*\})')

# Fields that always exist (non-nullable)
INT_FIELDS = ["posts", "image_posts", "favorites", "user_id"]
STR_FIELDS = ["username", "date_joined", "last_login", "last_active"]
# Fields that can be null or empty string
OPT_STR_FIELDS = ["location", "website", "interests", "user_title", "gender", "avatar"]
OPT_INT_FIELDS = ["maximgperday"]
BOOL_FIELDS = ["active", "admin"]


def parse_profile(raw):
    """Parse profileUser JSON-like embedded data, return dict or None."""
    m = PROFILE_RE.search(raw)
    if not m:
        return None
    block = m.group(1)
    data = {}

    # Required string fields
    for key in STR_FIELDS:
        g = re.search(rf'{key}:"([^"]*)"', block)
        if g:
            data[key] = g.group(1)
        else:
            return None  # missing required field

    # Required int fields
    for key in INT_FIELDS:
        g = re.search(rf'{key}:(\d+)', block)
        if g:
            data[key] = int(g.group(1))
        else:
            data[key] = 0

    # Optional string fields (can be null, "", or a value)
    for key in OPT_STR_FIELDS:
        g = re.search(rf'{key}:"([^"]*)"', block)
        if g:
            data[key] = g.group(1)
        elif re.search(rf'{key}:null', block):
            data[key] = None
        else:
            data[key] = None

    # Optional int fields
    for key in OPT_INT_FIELDS:
        g = re.search(rf'{key}:(\d+)', block)
        if g:
            data[key] = int(g.group(1))
        else:
            data[key] = None

    # Boolean fields
    for key in BOOL_FIELDS:
        data[key] = f'{key}:true' in block

    return data


def fetch_user(uid):
    """Fetch a user page, return (uid, data_dict or None)."""
    url = f"https://e-shuushuu.net/users/{uid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (uid, None)
        return (uid, None)
    except Exception:
        return (uid, None)

    # 404 check from title/content
    if "Page Not Found" in html[:3000]:
        return (uid, None)

    data = parse_profile(html)
    return (uid, data)


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            d = json.load(f)
            return d.get("next_id", 1), d.get("consecutive_404", 0), d.get("total", 0)
    return 1, 0, 0


def save_checkpoint(next_id, consec, total, elapsed=None):
    with open(CHECKPOINT, "w") as f:
        obj = {"next_id": next_id, "consecutive_404": consec, "total": total}
        if elapsed is not None:
            obj["elapsed"] = elapsed
        json.dump(obj, f)


def append_user(data):
    with open(DB, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Main ──

next_id, consec_404, total = load_checkpoint()
start_ts = time.time()
os.makedirs(os.path.dirname(DB), exist_ok=True)

log(f"Starting scrape from user_id={next_id}, consec_404={consec_404}, already_found={total}")
log(f"Workers={WORKERS}, 404_limit={CONSECUTIVE_404_LIMIT}")

batch_num = 0
while consec_404 < CONSECUTIVE_404_LIMIT:
    batch_num += 1
    batch = list(range(next_id, next_id + WORKERS))
    batch_404s = 0
    batch_found = 0
    results = [None] * len(batch)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fut_map = {pool.submit(fetch_user, uid): i for i, uid in enumerate(batch)}
        for fut in as_completed(fut_map):
            idx = fut_map[fut]
            results[idx] = fut.result()

    for uid, data in results:
        if data:
            append_user(data)
            total += 1
            batch_found += 1
            consec_404 = 0
        else:
            batch_404s += 1
            consec_404 += 1
        next_id = uid + 1

    elapsed = time.time() - start_ts
    rate = next_id / elapsed if elapsed > 0 else 0
    log(f"batch #{batch_num} | ids {batch[0]}–{batch[-1]} | +{batch_found} found, {batch_404s} 404 | "
        f"total_found={total} | consec_404={consec_404} | "
        f"{elapsed/60:.1f}m elapsed | {rate:.0f} ids/min")

    # Checkpoint every 10 batches to reduce I/O overhead
    if batch_num % 10 == 0 or consec_404 >= CONSECUTIVE_404_LIMIT:
        save_checkpoint(next_id, consec_404, total, elapsed)

log(f"=== DONE ===")
log(f"Scanned up to id={next_id-1}, total_users_found={total}, stopped by {CONSECUTIVE_404_LIMIT}x consecutive 404")
save_checkpoint(next_id, consec_404, total, time.time() - start_ts)