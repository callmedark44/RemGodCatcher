import os, re, time, threading, json, random
from pathlib import Path
import shared
from shared import log_msg, STOP_EVENTS

name = "pinterest"

def browser_login(client, email, password, proxy_url, cookies_path):
    from playwright.sync_api import BrowserType
    from pinterest_dl import PinterestDL as PDL
    orig_browser_launch = BrowserType.launch
    def patched_browser_launch(self, **kw):
        if proxy_url:
            kw["proxy"] = {"server": proxy_url}
        return orig_browser_launch(self, **kw)
    BrowserType.launch = patched_browser_launch
    scraper = PDL.with_browser(browser_type="chromium", headless=True, verbose=False)
    driver = scraper.login(email, password)
    cookies = driver.get_cookies(after_sec=7)
    scraper.close()
    client.with_cookies(cookies)
    if cookies_path and cookies:
        try:
            os.makedirs(os.path.dirname(cookies_path) or ".", exist_ok=True)
            with open(cookies_path, "w") as f:
                json.dump(cookies, f, indent=2)
            log_msg(name, f"Saved fresh cookies to {cookies_path}")
        except Exception as e:
            log_msg(name, f"Could not save cookies: {e}")
    log_msg(name, "Logged in via browser and using fresh cookies")
    return True

def worker_pinterest(url_or_query, amount, is_search, net_config, min_w=0, min_h=0):
    my_stop_event = threading.Event()
    if name not in STOP_EVENTS or not isinstance(STOP_EVENTS[name], list):
        STOP_EVENTS[name] = []
    STOP_EVENTS[name].append(my_stop_event)
    stop_event = my_stop_event

    if net_config.get("use_proxy"):
        os.environ.setdefault("HTTP_PROXY", net_config["proxy_url"])
        os.environ.setdefault("HTTPS_PROXY", net_config["proxy_url"])

    from pinterest_dl import PinterestDL
    from pinterest_dl.download import MediaDownloader

    log_msg(name, f"Initializing Pinterest worker for: '{url_or_query[:80]}' ({'search' if is_search else 'url scrape'})")

    cookies_path = net_config.get("pinterest_cookies", "")
    email = net_config.get("pinterest_email", "")
    password = net_config.get("pinterest_password", "")
    proxy_url = net_config.get("proxy_url", "")

    safe_name = re.sub(r'[\\/*?:"<>|]', "_", (url_or_query.strip().lower().replace("https://", "").replace("http://", "").replace("/", "_")[:60]))
    site_root = os.path.join(shared.MASTER_FOLDER, "Pinterest", safe_name)
    os.makedirs(site_root, exist_ok=True)

    if not cookies_path:
        cookies_path = os.path.join(site_root, "pinterest_cookies.json")

    def run_search(client):
        collected = []
        seen_ids = set()
        progress_lock = threading.Lock()

        def on_progress(media):
            with progress_lock:
                if len(collected) >= amount:
                    return
                if media.id in seen_ids:
                    return
                ext = Path(media.src).suffix.lower() if media.src else ".jpg"
                if os.path.exists(os.path.join(site_root, f"{media.id}{ext}")):
                    return
                seen_ids.add(media.id)
                collected.append(media)

        try:
            existing = len([f for f in os.listdir(site_root) if re.match(r'^\d+\.[a-z]+$', f)])
            fetch_num = amount + existing
            if is_search:
                client.search(query=url_or_query, num=fetch_num, min_resolution=(min_w, min_h), on_progress=on_progress)
            else:
                client.scrape(url=url_or_query, num=fetch_num, min_resolution=(min_w, min_h), on_progress=on_progress)
        except Exception as e:
            log_msg(name, f"Scrape error: {e}")
            return None
        return collected

    client = PinterestDL.with_api(timeout=5, verbose=False, ensure_alt=True)
    have_auth = False

    if os.path.exists(cookies_path):
        try:
            client.with_cookies_path(cookies_path)
            log_msg(name, "Loaded Pinterest cookies")
            have_auth = True
        except Exception as e:
            log_msg(name, f"Cookie load error: {e}")

    collected = run_search(client)

    if not collected and have_auth and email and password:
        log_msg(name, "Cookies expired, refreshing via browser login...")
        try:
            os.remove(cookies_path)
        except Exception:
            pass
        client = PinterestDL.with_api(timeout=5, verbose=False, ensure_alt=True)
        try:
            browser_login(client, email, password, proxy_url, cookies_path)
            collected = run_search(client)
        except Exception as e:
            log_msg(name, f"Browser login failed: {e}")
    elif not have_auth and email and password:
        log_msg(name, "No cookies, logging in via browser...")
        try:
            browser_login(client, email, password, proxy_url, cookies_path)
            collected = run_search(client)
        except ImportError:
            log_msg(name, "Browser auth unavailable (install pinterest-dl[browser] and playwright)")
        except Exception as e:
            log_msg(name, f"Browser login failed: {e}")

    if not collected:
        log_msg(name, "No new media found.")
        log_msg(name, "--- Worker Terminated ---")
        return

    medias = collected[:amount]
    log_msg(name, f"Collected {len(collected)} new items, downloading {len(medias)}.")

    shared.socketio_emit("pinterest_progress", {"index": 0, "total": amount})

    dl_retries = int(net_config.get("download_retries", 3))
    downloader = MediaDownloader(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        timeout=int(net_config.get("api_timeout", 10)),
        max_retries=dl_retries
    )

    downloaded = 0
    for i, media in enumerate(medias):
        if stop_event.is_set():
            break

        try:
            path = downloader.download(media, Path(site_root), download_streams=True)
            filename = os.path.basename(path)

            rel = os.path.relpath(str(path), shared.MASTER_FOLDER)
            tags = []
            if media.alt:
                tags = [media.alt]
            artists = []
            shared.add_to_gallery(name, filename, rel, tags, artists)
            shared.send_tags(name, filename, tags, artists)

            downloaded += 1
            shared.socketio_emit("pinterest_progress", {"index": downloaded, "total": amount})
            log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
        except Exception as e:
            log_msg(name, f"[FAILED] {media.id}: {e}")

        time.sleep(random.uniform(0.5, 1.5))

    log_msg(name, f"Downloaded {downloaded} items.")
    log_msg(name, "--- Worker Terminated ---")
