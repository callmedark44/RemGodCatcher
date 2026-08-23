import os, json, time
from dotenv import load_dotenv
from curl_cffi import requests as curl_requests

load_dotenv()
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = HERE if os.path.isdir(os.path.join(HERE, "database")) else os.path.join(HERE, "Rem-s-Dl-test")
OUT = os.path.join(REPO, "database", "gelbooru_tag_names.json")
load_dotenv(os.path.join(REPO, ".env"))
API = "https://gelbooru.com/index.php"
PAGE_SIZE = 1000

def fetch_page(s, pid):
    params = {"page": "dapi", "s": "tag", "q": "index", "json": 1,
              "limit": PAGE_SIZE, "pid": pid,
              "api_key": os.getenv("GELBOORU_API_KEY", ""),
              "user_id": os.getenv("GELBOORU_USER_ID", "")}
    for attempt in range(6):
        try:
            r = s.get(API, params=params, timeout=30)
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"\n429 rate-limited, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == 5:
                raise
            print(f"\nretry {attempt + 1}: {e}", flush=True)
            time.sleep(5)
    return {}

def main():
    s = curl_requests.Session(impersonate="chrome131")
    pairs, total = [], None
    # ponytail: resume = names-only checkpoint loses popularity ranks for old entries; full-pairs progress file would preserve them
    if os.path.exists(OUT):
        try:
            saved = json.load(open(OUT))
            pairs = [(n, 0) for n in saved]
            print(f"Resuming with {len(pairs)} tags already fetched.")
        except Exception:
            pass
    pid = len(pairs) // PAGE_SIZE
    while True:
        data = fetch_page(s, pid)
        total = int(data.get("@attributes", {}).get("count", total or 0))
        batch = data.get("tag") or data.get("TAGS") or []
        batch = [(t["name"], int(t.get("count", 0))) for t in batch if isinstance(t, dict) and t.get("name")]
        if not batch:
            break
        pairs.extend(batch)
        print(f"\r{len(pairs)}/{total} tags (page {pid})", end="", flush=True)
        if len(pairs) >= total:
            break
        pid += 1
        time.sleep(0.1)
        # ponytail: checkpoint every 100 pages so a crash doesn't lose an hour
        if pid % 100 == 0:
            json.dump([n for n, _ in pairs], open(OUT, "w"))

    best = {}
    for name, count in pairs:
        if name not in best or count > best[name]:
            best[name] = count
    ordered = [n for n, _ in sorted(best.items(), key=lambda kv: -kv[1])]
    json.dump(ordered, open(OUT, "w"))
    print(f"\nSaved {len(ordered)} tags to {OUT}", flush=True)

if __name__ == "__main__":
    main()
