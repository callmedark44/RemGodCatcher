import os, re, time, threading, json, random
from pathlib import Path
import shared
from shared import log_msg, STOP_EVENTS

name = "pinterest"

def worker_pinterest(url_or_query, amount, is_search, net_config):
    if name in STOP_EVENTS and STOP_EVENTS[name] is not None:
        STOP_EVENTS[name].set()
    my_stop_event = threading.Event()
    STOP_EVENTS[name] = my_stop_event
    stop_event = my_stop_event

    if net_config.get("use_proxy"):
        os.environ.setdefault("HTTP_PROXY", net_config["proxy_url"])
        os.environ.setdefault("HTTPS_PROXY", net_config["proxy_url"])

    from pinterest_dl import PinterestDL
    from pinterest_dl.download import MediaDownloader

    log_msg(name, f"Initializing Pinterest worker for: '{url_or_query[:80]}' ({'search' if is_search else 'url scrape'})")

    client = PinterestDL.with_api(timeout=5, verbose=False, ensure_alt=True)

    cookies_path = net_config.get("pinterest_cookies", "")
    email = net_config.get("pinterest_email", "")
    password = net_config.get("pinterest_password", "")
    have_auth = False

    if cookies_path and os.path.exists(cookies_path):
        try:
            client.with_cookies_path(cookies_path)
            log_msg(name, "Loaded Pinterest cookies")
            have_auth = True
        except Exception as e:
            log_msg(name, f"Cookie load error: {e}")

    if not have_auth and email and password:
        try:
            from pinterest_dl import PinterestDL as PDL
            driver = PDL.with_browser(browser_type="chromium", headless=True, verbose=False).login(email, password)
            cookies = driver.get_cookies(after_sec=7)
            driver.close()
            client.with_cookies(cookies)
            if cookies_path:
                try:
                    os.makedirs(os.path.dirname(cookies_path) or ".", exist_ok=True)
                    with open(cookies_path, "w") as f:
                        json.dump(cookies, f, indent=2)
                    log_msg(name, f"Saved fresh cookies to {cookies_path}")
                except Exception as e:
                    log_msg(name, f"Could not save cookies: {e}")
            log_msg(name, "Logged in via browser and using fresh cookies")
            have_auth = True
        except ImportError:
            log_msg(name, "Browser auth unavailable (install pinterest-dl[browser] and playwright)")
        except Exception as e:
            log_msg(name, f"Browser login failed: {e}")

    if not have_auth:
        log_msg(name, "No auth — public content only")

    collected = []
    progress_lock = threading.Lock()

    def on_progress(media):
        with progress_lock:
            collected.append(media)
            shared.socketio_emit("pinterest_progress", {
                "index": len(collected),
                "total": amount,
                "alt": media.alt or "",
                "id": media.id
            })

    try:
        if is_search:
            medias = client.search(query=url_or_query, num=amount, on_progress=on_progress)
        else:
            medias = client.scrape(url=url_or_query, num=amount, on_progress=on_progress)
    except Exception as e:
        log_msg(name, f"Scrape error: {e}")
        log_msg(name, "--- Worker Terminated ---")
        return

    if not medias:
        log_msg(name, "No media found.")
        log_msg(name, "--- Worker Terminated ---")
        return

    log_msg(name, f"Collected {len(medias)} media items. Starting download...")

    safe_name = re.sub(r'[\\/*?:"<>|]', "_", (url_or_query.strip().lower().replace("https://", "").replace("http://", "").replace("/", "_")[:60]))
    site_root = os.path.join(shared.MASTER_FOLDER, "Pinterest", safe_name)
    os.makedirs(site_root, exist_ok=True)

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

            if media.alt:
                sidecar = path.with_suffix(path.suffix + ".txt")
                sidecar.write_text(media.alt, encoding="utf-8")

            downloaded += 1
            log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
        except Exception as e:
            log_msg(name, f"[FAILED] {media.id}: {e}")

        time.sleep(random.uniform(0.5, 1.5))

    log_msg(name, f"Downloaded {downloaded} items.")
    log_msg(name, "--- Worker Terminated ---")
