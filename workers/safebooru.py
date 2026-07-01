import os
import time
import threading
import random
import re

from shared import log_msg, STOP_EVENTS, MASTER_FOLDER, load_history, save_history, get_session

def worker_safebooru(tag, amount, exclusions, net_config):
    name = "safe"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]

    anti_ban_pause = float(net_config.get("anti_ban_pause", 3.0))
    tag = tag.strip().lower()
    log_msg(name, f"Initializing worker for tag: '{tag}'")

    site_root = os.path.join(MASTER_FOLDER, "Safebooru")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)
    session = get_session("safe", net_config)

    safe_tag = re.sub(r'[\\/*?:"<>|]', "", tag).replace(' ', '_')
    tag_dir = os.path.join(site_root, safe_tag)
    os.makedirs(tag_dir, exist_ok=True)

    downloaded = 0
    page = 1
    empty_pages = 0
    max_empty = 3
    
    while not stop_event.is_set() and (amount == 0 or downloaded < amount):
        try:
            log_msg(name, f"Scanning API... (Page {page})")
            limit_val = min(100, amount - downloaded if amount > 0 else 100)

            resp = session.get("https://safebooru.donmai.us/posts.json", params={"tags": tag, "page": page, "limit": limit_val}, timeout=15)
            if resp.status_code in [403, 429]:
                log_msg(name, f"ERROR {resp.status_code}. Change proxy.")
                break
            resp.raise_for_status()

            text_resp = resp.text.strip()
            if not text_resp or text_resp == "[]":
                if page == 1: log_msg(name, f"ZERO images found for '{tag}'.")
                break

            raw_data = resp.json()
            if isinstance(raw_data, dict):
                if "success" in raw_data and not raw_data["success"]:
                    log_msg(name, f"API Alert: {raw_data.get('message', 'Unknown Error')}")
                    break
                posts = [raw_data]
            elif isinstance(raw_data, list): posts = raw_data
            else: break

            if not posts: break

        except Exception as e:
            err_str = str(e)
            if "403" in err_str: log_msg(name, "ERROR 403: Cloudflare/ISP block. You need a VPN.")
            else: log_msg(name, f"API Error: {e}")
            time.sleep(5)
            continue

        page_downloaded = 0
        for post in posts:
            if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
            if not isinstance(post, dict): continue

            url = post.get("file_url") or post.get("large_file_url")
            if not url: continue
            if url.startswith("https://"): url = url.replace("https://", "http://")

            # --- استخراج تگهای عکس ---
            tags_raw = post.get("tags", "")
            tags_str = (tags_raw[:120] + "...") if len(tags_raw) > 120 else tags_raw

            ext = (post.get("file_ext") or "").lower()
            
            # --- VIDEO/IMAGE FILTERING LOGIC ---
            if ext in ["mp4", "webm", "zip"] and "-video" in exclusions: continue
            if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in exclusions: continue
            if ext == "gif" and "-gif" in exclusions: continue

            filename = f"{post.get('id')}.{ext}"
            filepath = os.path.join(tag_dir, filename)

            if filename in dl_history or os.path.exists(filepath): continue

            try:
                r = session.get(url, stream=True, timeout=20)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break

                downloaded += 1
                page_downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)

                log_msg(name, f"[SUCCESS] {filename} ({downloaded}/{amount}) | Tags: {tags_str}")
                time.sleep(random.uniform(0.5, 2.0))
            except Exception as e:
                log_msg(name, f"[FAILED] {filename}: {e}")

        if page_downloaded == 0:
            empty_pages += 1
            if empty_pages >= max_empty:
                log_msg(name, f"No downloadable content found after {empty_pages} pages. Stopping.")
                break
        else:
            empty_pages = 0

        page += 1
        if not stop_event.is_set() and (amount == 0 or downloaded < amount):
            delay = random.uniform(anti_ban_pause, anti_ban_pause + 2.0)
            log_msg(name, f"Anti-ban pause... ({delay:.1f}s)")
            time.sleep(delay)

    log_msg(name, "--- Worker Terminated ---")