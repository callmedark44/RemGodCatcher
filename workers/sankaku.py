import os, re, time, threading, random
import shared
from shared import log_msg, STOP_EVENTS, load_history, save_history, get_session

API_BASE = "https://sankakuapi.com"

def worker_sankaku(tag, amount, rating, exclusions, net_config):
    name = "sankaku"
    my_stop_event = threading.Event()
    if name not in STOP_EVENTS or not isinstance(STOP_EVENTS[name], list):
        STOP_EVENTS[name] = []
    STOP_EVENTS[name].append(my_stop_event)
    stop_event = my_stop_event

    dl_retries = int(net_config.get("download_retries", 3))
    tag = tag.strip().lower()
    original_tag = tag

    if rating:
        tag = (tag + " " + rating).strip()
    log_msg(name, f"Initializing worker for tag: '{tag}'")

    site_root = os.path.join(shared.MASTER_FOLDER, "Sankaku")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)

    session = get_session("sankaku", net_config)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })

    access_token = os.getenv("SANKA_ACCESS_TOKEN")
    sanka_login = os.getenv("SANKA_LOGIN")
    sanka_password = os.getenv("SANKA_PASSWORD")

    if not access_token and sanka_login and sanka_password:
        for login_url in (f"{API_BASE}/auth/token", "https://login.sankakucomplex.com/auth/token"):
            try:
                r = session.post(login_url,
                    json={"login": sanka_login, "password": sanka_password}, timeout=15)
                if r.ok:
                    data = r.json()
                    access_token = data.get("token") or data.get("access_token") or ""
                    if access_token:
                        log_msg(name, "Logged in via credentials")
                        break
                    log_msg(name, "Login response missing token")
                else:
                    try:
                        err_body = r.json()
                        err_msg = err_body.get('error', str(r.status_code))
                    except Exception:
                        err_msg = str(r.status_code)
                    log_msg(name, f"Login at {login_url.split('/')[2]}: {err_msg}")
            except Exception as e:
                log_msg(name, f"Login error at {login_url.split('/')[2]}: {e}")

    if access_token:
        session.headers["Authorization"] = f"Bearer {access_token}"
    elif not access_token:
        log_msg(name, "No auth token - API may reject requests")

    clean_tag = " ".join(t for t in original_tag.split() if not t.startswith('-'))
    safe_tag = re.sub(r'[\\/*?"<>|]', "", clean_tag)
    tag_dir = os.path.join(site_root, safe_tag)
    os.makedirs(tag_dir, exist_ok=True)

    rating_map = {"s": "Safe", "q": "Questionable", "e": "NSFW"}

    collected = []
    video_count = 0
    page = 1

    while not stop_event.is_set() and (amount == 0 or len(collected) < amount):
        try:
            # silent
            limit_val = min(40, amount - len(collected) if amount > 0 else 40)

            tag_list = [t.strip() for t in original_tag.split() if t.strip() and not t.startswith('-')]
            params = {"limit": limit_val, "page": page}
            if net_config.get("hide_pools", False):
                params["hide_posts_in_books"] = "always"
            if rating:
                rc = rating.split(":")[-1]
                tag_list.append(f"rating:{rc}")

            if "-video" in exclusions and "-image" not in exclusions:
                tag_list.append("file_type:image")
            elif "-image" in exclusions and "-video" not in exclusions:
                tag_list.append("file_type:video")

            if tag_list:
                params["tags"] = " ".join(tag_list)

            resp = session.get(f"{API_BASE}/posts", params=params, timeout=15)
            if resp.status_code in [403, 429]:
                try:
                    err = resp.json()
                    log_msg(name, f"API error: {err.get('error') or err.get('errors', [str(resp.status_code)])[0]}")
                except Exception:
                    log_msg(name, f"ERROR {resp.status_code}. Check proxy/credentials.")
                break
            resp.raise_for_status()

            data = resp.json()
            # silent
            if isinstance(data, dict):
                log_msg(name, f"Keys: {list(data.keys())}")
                posts = data.get("data") or data.get("posts") or []
            elif isinstance(data, list):
                posts = data
            else:
                log_msg(name, f"Unexpected response: {str(data)[:200]}")
                break

            if not posts:
                if page == 1:
                    req_url = resp.url
                    resp_text = resp.text[:500] if hasattr(resp, 'text') else str(data)[:500]
                    log_msg(name, f"ZERO images for '{tag}'. URL: {req_url} | status: {resp.status_code} | auth: {'yes' if access_token else 'none'} | resp: {resp_text}")
                break

        except Exception as e:
            err_str = str(e)
            if "403" in err_str:
                log_msg(name, "ERROR 403: Access denied.")
            else:
                log_msg(name, f"API Error: {e}")
            time.sleep(5)
            continue

        time.sleep(0.25)

        for post in posts:
            if stop_event.is_set() or (amount > 0 and len(collected) >= amount):
                break
            if not isinstance(post, dict):
                continue

            post_rating = post.get("rating", "")
            if rating:
                filter_rating = rating.split(":")[-1]
                if post_rating != filter_rating:
                    continue

            url = post.get("file_url")
            if not url:
                continue

            ext = (post.get("file_ext") or "").lower()
            if ext not in ["jpg", "jpeg", "png", "gif", "webp", "mp4", "webm"]:
                continue
            if ext in ["mp4", "webm"] and "-video" in exclusions:
                continue
            if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in exclusions:
                continue
            if ext == "gif" and "-gif" in exclusions:
                continue

            is_video = ext in ["mp4", "webm"]
            filename = f"{post.get('id')}.{ext}"
            if filename in dl_history:
                continue

            rating_label = rating_map.get(post_rating, "Unknown")
            subfolder = "books" if post.get("in_visible_pool") else "images"
            rating_dir = os.path.join(tag_dir, rating_label, subfolder)
            filepath = os.path.join(rating_dir, filename)
            if os.path.exists(filepath):
                continue

            raw_tags = post.get("tags", [])
            if raw_tags and isinstance(raw_tags[0], dict):
                tags_list = [t.get("name", "") for t in raw_tags if t.get("name")]
                artists = [t.get("name") for t in raw_tags if isinstance(t, dict) and t.get("type") == 1]
            else:
                tags_list = post.get("tag_names", [])
                artists = []

            if is_video:
                video_count += 1
            collected.append((url, filename, rating_label, tags_list, artists, is_video))

        page += 1
        if not stop_event.is_set() and (amount == 0 or len(collected) < amount):
            time.sleep(0.5)

    if not collected:
        log_msg(name, "No new items to download.")
        log_msg(name, "--- Worker Terminated ---")
        return

    def _plural(n, s): return s if n == 1 else s + "s"
    if video_count == len(collected):
        log_msg(name, f"Collected {len(collected)} new {_plural(len(collected), 'video')}. Starting download...")
    elif video_count == 0:
        log_msg(name, f"Collected {len(collected)} new {_plural(len(collected), 'image')}. Starting download...")
    else:
        log_msg(name, f"Collected {len(collected)} new {_plural(len(collected), 'item')} ({len(collected)-video_count} {_plural(len(collected)-video_count, 'image')}, {video_count} {_plural(video_count, 'video')}). Starting download...")

    downloaded = 0
    for url, filename, rating_label, tags_list, artists, is_video in collected:
        if stop_event.is_set():
            break

        rating_dir = os.path.join(tag_dir, rating_label, "images")
        os.makedirs(rating_dir, exist_ok=True)
        filepath = os.path.join(rating_dir, filename)

        for dl_attempt in range(dl_retries):
            try:
                r = session.get(url, stream=True, timeout=60)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set():
                            break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break

                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                rel = os.path.relpath(filepath, shared.MASTER_FOLDER)
                shared.add_to_gallery(name, filename, rel, tags_list, artists)
                shared.send_tags(name, filename, tags_list, artists)
                time.sleep(random.uniform(0.5, 2.0))
                break
            except Exception as e:
                if stop_event.is_set():
                    break
                if dl_attempt < dl_retries - 1:
                    log_msg(name, f"[RETRY {dl_attempt+1}/{dl_retries}] {filename}: {e}")
                    for _ in range(20):
                        if stop_event.is_set():
                            break
                        time.sleep(0.1)
                else:
                    log_msg(name, f"[FAILED] {filename}: {e}")

        if stop_event.is_set():
            break

    log_msg(name, "--- Worker Terminated ---")
