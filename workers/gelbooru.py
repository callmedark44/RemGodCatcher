import os, time, threading, random, re
import shared
from shared import log_msg, STOP_EVENTS, load_history, save_history, get_session

def worker_gelbooru(tag, amount, rating, exclusions, net_config):
    name = "gelbooru"
    if name in STOP_EVENTS and STOP_EVENTS[name] is not None:
        STOP_EVENTS[name].set()

    my_stop_event = threading.Event()
    STOP_EVENTS[name] = my_stop_event
    stop_event = my_stop_event

    anti_ban_pause = float(net_config.get("anti_ban_pause", 3.0))
    dl_retries = int(net_config.get("download_retries", 3))
    tag = tag.strip().lower()
    original_tag = tag

    dan_to_gel_rating = {"rating:g": "rating:general", "rating:s": "rating:sensitive", "rating:q": "rating:questionable", "rating:e": "rating:explicit"}
    api_tag = tag
    if rating:
        api_rating = dan_to_gel_rating.get(rating, rating)
        api_tag = (tag + " " + api_rating).strip()
    log_msg(name, f"Initializing worker for tag: '{api_tag}'")

    site_root = os.path.join(shared.MASTER_FOLDER, "Gelbooru")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)
    session = get_session("gelbooru", net_config)

    clean_tag = " ".join(t for t in original_tag.split() if not t.startswith('-'))
    safe_tag = re.sub(r'[\\/*?"<>|]', "", clean_tag)
    tag_dir = os.path.join(site_root, safe_tag)
    os.makedirs(tag_dir, exist_ok=True)

    rating_code_map = {"g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"}
    rating_label_map = {"general": "Safe", "sensitive": "Sensitive", "questionable": "Questionable", "explicit": "NSFW"}

    api_key = os.getenv("GELBOORU_API_KEY", "")
    user_id = os.getenv("GELBOORU_USER_ID", "")

    collected = []
    pid = 0

    while not stop_event.is_set() and (amount == 0 or len(collected) < amount):
        try:
            log_msg(name, f"Scanning API... (Page {pid})")
            limit_val = min(100, amount - len(collected) if amount > 0 else 100)

            params = {
                "page": "dapi", "s": "post", "q": "index",
                "tags": api_tag, "pid": pid, "limit": limit_val, "json": 1
            }
            if api_key and user_id:
                params["api_key"] = api_key
                params["user_id"] = user_id

            resp = session.get("https://gelbooru.com/index.php", params=params, timeout=15)
            if resp.status_code == 401:
                log_msg(name, "ERROR 401: Unauthorized! Gelbooru blocked this request.")
                log_msg(name, "FIX: Enter a valid Gelbooru API Key & User ID in the Options Tab!")
                break
            elif resp.status_code in [403, 429]:
                log_msg(name, f"ERROR {resp.status_code}. Change proxy or slow down.")
                break

            resp.raise_for_status()
            data = resp.json()

            posts = data.get("post", [])
            if not posts:
                if pid == 0: log_msg(name, f"0 images found for '{tag}'.")
                else: log_msg(name, "End of database reached.")
                break

        except Exception as e:
            err_str = str(e)
            if "403" in err_str: log_msg(name, "ERROR 403: Cloudflare/ISP block. You need a VPN.")
            else: log_msg(name, f"API Error: {e}")
            time.sleep(5)
            continue

        had_valid = False
        for post in posts:
            if stop_event.is_set() or (amount > 0 and len(collected) >= amount): break
            if not isinstance(post, dict): continue

            post_rating = post.get("rating", "")
            if rating:
                filter_code = rating.split(":")[-1]
                filter_rating = rating_code_map.get(filter_code, filter_code)
                if post_rating != filter_rating:
                    continue

            file_url = post.get("file_url", "")
            if not file_url: continue

            ext = file_url.split('.')[-1].lower()

            if ext in ["mp4", "webm", "zip"] and "-video" in exclusions: continue
            if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in exclusions: continue
            if ext == "gif" and "-gif" in exclusions: continue

            filename = file_url.split('/')[-1].split('?')[0]
            if filename in dl_history:
                continue

            rating_label = rating_label_map.get(post_rating, "Unknown")
            rating_dir = os.path.join(tag_dir, rating_label, "images")
            filepath = os.path.join(rating_dir, filename)
            if os.path.exists(filepath):
                continue

            tags_raw = post.get("tags", "")
            tags_list = [t.strip() for t in tags_raw.split() if t.strip()]
            artists = []
            for t in tags_list:
                if t.startswith("artist:"):
                    artists.append(t.replace("artist:", "", 1))
            tags_list = [t for t in tags_list if not t.startswith("artist:")]

            collected.append((file_url, filename, rating_label, tags_list, artists))
            had_valid = True

        pid += 1
        if had_valid and not stop_event.is_set() and (amount == 0 or len(collected) < amount):
            log_msg(name, f"Anti-ban pause... ({anti_ban_pause:.1f}s)")
            time.sleep(anti_ban_pause)

    if not collected:
        log_msg(name, "No new images to download.")
        log_msg(name, "--- Worker Terminated ---")
        return

    log_msg(name, f"Collected {len(collected)} new images. Starting download...")

    downloaded = 0
    for file_url, filename, rating_label, tags_list, artists in collected:
        if stop_event.is_set(): break

        rating_dir = os.path.join(tag_dir, rating_label, "images")
        os.makedirs(rating_dir, exist_ok=True)
        filepath = os.path.join(rating_dir, filename)

        success = False
        for dl_attempt in range(dl_retries):
            try:
                r = session.get(file_url, stream=True, timeout=20, headers={"Referer": "https://gelbooru.com/"})
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break

                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                shared.send_tags(name, filename, tags_list, artists)
                time.sleep(random.uniform(0.5, 1.5))
                success = True
                break
            except Exception as e:
                if dl_attempt < dl_retries - 1:
                    log_msg(name, f"[RETRY {dl_attempt+1}/{dl_retries}] {filename}: {e}")
                    time.sleep(2)
                else:
                    log_msg(name, f"[FAILED] {filename}: {e}")
        if not success:
            continue

    log_msg(name, "--- Worker Terminated ---")
