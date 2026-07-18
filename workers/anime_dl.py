#!/usr/bin/env python3
"""Search anime-pictures.net by tag, download N full-resolution images.

Cookie bypass detail
────────────────────
The origin server at api.anime-pictures.net/pictures/download_image/
rejects requests (403) unless two cookies are present:

    time_zone=<browser timezone>     # e.g. Asia/Tehran, UTC
    sitelang=<site language>         # e.g. en

The site's JavaScript sets these on page load via
Intl.DateTimeFormat and the language selector.  Without them,
every download request gets a hard 403 from the origin WAF,
even with perfect TLS impersonation (curl_cffi, cloudscraper, etc.).

How to rediscover if they change
────────────────────────────────
1. Open Firefox/Chrome headless with Selenium/Playwright
2. Visit https://anime-pictures.net/posts/<any_id>?lang=en
3. Read driver.get_cookies()
4. Find the two cookies above — they're what the origin checks.
5. Update make_session() with any working values.

Example Selenium snippet (runs as-is with Firefox):

    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    opts = Options(); opts.binary_location = "/usr/bin/firefox"; opts.headless = True
    driver = webdriver.Firefox(options=opts)
    driver.get("https://anime-pictures.net/posts/923483?lang=en")
    print(driver.get_cookies())
    driver.quit()
"""

import sys, os, time, json, threading, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
import shared

API = "https://api.anime-pictures.net/api/v3"
PER_PAGE = 80


def worker_anime_dl(tag, amount, net_config):
    name = "anime_dl"
    if name in shared.STOP_EVENTS and shared.STOP_EVENTS[name] is not None:
        shared.STOP_EVENTS[name].set()

    my_stop_event = threading.Event()
    shared.STOP_EVENTS[name] = my_stop_event
    stop_event = my_stop_event

    tag = tag.strip().lower()
    shared.log_msg(name, f"Initializing worker for tag: '{tag}'")

    site_root = os.path.join(shared.MASTER_FOLDER, "AnimePictures")
    os.makedirs(site_root, exist_ok=True)

    tag_slug = tag.replace(" ", "_")
    outdir = os.path.join(site_root, tag_slug)
    os.makedirs(outdir, exist_ok=True)

    session = make_session(net_config)

    post_ids = []
    page = 0
    while not stop_event.is_set() and len(post_ids) < amount:
        posts, total = search_posts(session, tag, page)
        if not posts:
            break
        page += 1
        for p in posts:
            if p["id"] not in post_ids:
                post_ids.append(p["id"])
        if page * PER_PAGE >= total:
            break

    post_ids = post_ids[:amount]
    if not post_ids:
        shared.log_msg(name, "No posts found.")
        shared.log_msg(name, "--- Worker Terminated ---")
        return

    shared.log_msg(name, f"Found {len(post_ids)} posts, downloading...")

    saved = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(download_one, session, pid, tag_slug, outdir): pid for pid in post_ids}
        for fut in as_completed(futs):
            if stop_event.is_set():
                break
            pid, result = fut.result()
            if result.startswith("no_") or result.startswith("http_"):
                shared.log_msg(name, f"[FAILED] {pid}: {result}")
            else:
                saved += 1
                filename = os.path.basename(result)
                rel = os.path.relpath(result, shared.MASTER_FOLDER)
                shared.add_to_gallery(name, filename, rel, [tag], [])
                shared.send_tags(name, filename, [tag])
                shared.log_msg(name, f"[SUCCESS] Downloaded {filename} ({saved}/{amount})")

    shared.log_msg(name, f"--- All {saved}/{amount} downloads completed ---")
    shared.log_msg(name, "--- Worker Terminated ---")


def make_session(net_config=None):
    s = requests.Session()
    s.impersonate = "chrome131"
    if net_config and net_config.get("use_proxy"):
        p = net_config.get("proxy_url", "")
        s.proxies = {"http": p, "https": p}
    s.cookies.set("time_zone", "UTC", domain=".anime-pictures.net")
    s.cookies.set("sitelang", "en", domain=".anime-pictures.net")
    return s


def search_posts(session, tag, page=0):
    r = session.get(f"{API}/posts", params={
        "page": page, "limit": PER_PAGE,
        "search_tag": tag, "lang": "en"
    }, timeout=30)
    if r.status_code != 200:
        return None, 0
    data = r.json()
    return data.get("posts", []), data.get("posts_count", 0)


def get_post_detail(session, post_id):
    r = session.get(f"{API}/posts/{post_id}", params={"lang": "en"}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def download_one(session, post_id, tag_slug, outdir):
    detail = get_post_detail(session, post_id)
    if not detail:
        return (post_id, "no_detail")
    file_url = detail.get("file_url", "")
    if not file_url:
        return (post_id, "no_file_url")

    dl_url = f"https://api.anime-pictures.net/pictures/download_image/{file_url}"
    r = session.get(dl_url, timeout=120, headers={
        "Referer": f"https://anime-pictures.net/posts/{post_id}?lang=en",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    })
    if r.status_code == 200 and len(r.content) > 1000:
        ext = file_url.rsplit(".", 1)[-1]
        fpath = os.path.join(outdir, f"{tag_slug}_{post_id}.{ext}")
        with open(fpath, "wb") as f:
            f.write(r.content)
        return (post_id, fpath)

    return (post_id, f"http_{r.status_code}_{len(r.content)}b")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Download full-res images from anime-pictures.net by tag")
    parser.add_argument("tag", help="Tag to search for")
    parser.add_argument("count", type=int, nargs="?", default=10)
    parser.add_argument("--output", "-o", default="downloads")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    tag_slug = args.tag.lower().replace(" ", "_")

    session = make_session({})

    post_ids = []
    page = 0
    while len(post_ids) < args.count:
        posts, total = search_posts(session, args.tag, page)
        if not posts:
            break
        page += 1
        for p in posts:
            if p["id"] not in post_ids:
                post_ids.append(p["id"])
        if page * PER_PAGE >= total:
            break

    post_ids = post_ids[:args.count]
    print(f"Found {len(post_ids)} posts, downloading...", file=sys.stderr)

    saved = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download_one, session, pid, tag_slug, args.output): pid for pid in post_ids}
        for fut in as_completed(futs):
            pid, result = fut.result()
            saved += 1 if not result.startswith("no_") and not result.startswith("http_") else 0
            print(f"[{saved}/{args.count}] {pid}: {result}", file=sys.stderr)

    print(f"\nDone: {saved}/{args.count} images in {args.output}/", file=sys.stderr)


if __name__ == "__main__":
    main()
