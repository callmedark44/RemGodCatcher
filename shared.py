import os
import threading
import json
import time
import requests
import asyncio
import hashlib
from requests.adapters import HTTPAdapter
from PIL import Image, PngImagePlugin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_FOLDER = os.path.join(BASE_DIR, "Rem God")
HISTORY_LOCK = threading.Lock()
STOP_EVENTS = {}

SAFE_TAGS_DB = []
WAIFU_TAGS_DB = []
WAIFU_TAG_MAP = {}

# --- LOGGING & TAG SYSTEM ---
def default_logger(worker_name, msg): print(f"[{worker_name.upper()}] {msg}")
log_callback = default_logger
def log_msg(worker_name, msg): log_callback(worker_name, msg)

def default_tag_handler(worker_name, filename, tags_list, artist_list, filepath=None): pass
tag_callback = default_tag_handler
def send_tags(worker_name, filename, tags_list, artist_list=None, filepath=None):
    if artist_list is None: artist_list = []
    tag_callback(worker_name, filename, tags_list, artist_list, filepath)

GALLERY_FILE = os.path.join(BASE_DIR, "database", "gallery.json")

def load_gallery():
    if os.path.exists(GALLERY_FILE):
        try:
            with open(GALLERY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"images": []}
    return {"images": []}

def save_gallery(data):
    with open(GALLERY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def add_to_gallery(site, filename, filepath, tags_list, artists):
    gallery = load_gallery()
    for img in gallery["images"]:
        if img["filename"] == filename:
            return
    gallery["images"].insert(0, {
        "id": hashlib.md5(f"{site}:{filename}".encode()).hexdigest()[:12],
        "filename": filename,
        "filepath": filepath,
        "site": site,
        "tags": [t.strip() for t in tags_list if t.strip()],
        "artists": [a.strip() for a in artists if a.strip()],
        "favourite": False,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    })
    save_gallery(gallery)

def write_image_metadata(filepath, tags_list, artists, site):
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
    try:
        img = Image.open(filepath)
        meta_lines = [f"site:{site}"]
        meta_lines += [f"tag:{t}" for t in tags_list]
        meta_lines += [f"artist:{a}" for a in artists]
        meta_text = "\n".join(meta_lines)

        if ext in ('jpg', 'jpeg'):
            from PIL.ExifTags import Base
            exif = img.getexif()
            exif[0x9286] = meta_text
            img.save(filepath, exif=exif, quality=95, subsampling=0)
        elif ext == 'png':
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("RemGodCatcher", meta_text)
            img.save(filepath, pnginfo=pnginfo)
        elif ext == 'webp':
            img.save(filepath, exif=meta_text.encode())
        elif ext == 'gif':
            img.info['comment'] = meta_text
            img.save(filepath, save_all=True)
    except Exception as e:
        print(f"Metadata write error on {filepath}: {e}")

# --- HISTORY SYSTEM ---
def load_history(site_root):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        if os.path.exists(hist_path):
            try:
                with open(hist_path, "r", encoding="utf-8") as f: return set(json.load(f))
            except Exception: return set()
        return set()

def save_history(site_root, history_set):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        try:
            with open(hist_path, "w", encoding="utf-8") as f: json.dump(list(history_set), f, indent=4)
        except Exception as e: print(f"Error saving history: {e}")

# ==========================================
# === OOP ASYNCIO ENGINE ===
# ==========================================
class BaseDownloader:
    def __init__(self, name, site_folder, amount, net_config):
        self.name = name
        self.site_folder = site_folder
        self.amount = max(0, int(amount))
        self.net_config = net_config

        self.stop_event = threading.Event()
        if name not in STOP_EVENTS:
            STOP_EVENTS[name] = []
        STOP_EVENTS[name].append(self.stop_event)

        self.anti_ban_pause = float(net_config.get("anti_ban_pause", 3.0))
        self.dl_retries = int(net_config.get("download_retries", 3))

        self.site_root = os.path.join(MASTER_FOLDER, site_folder)
        os.makedirs(self.site_root, exist_ok=True)
        self.dl_history = load_history(self.site_root)

        self.session = self._setup_session()
        self.downloaded_count = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.total_to_download = 0
        self.download_queue = None

    def _setup_session(self):
        session = requests.Session()
        if self.net_config.get("use_proxy"):
            p = self.net_config.get("proxy_url")
            session.proxies = {"http": p, "https": p}
        session.verify = self.net_config.get("verify_tls", False)

        session.headers.update({
            "User-Agent": "RemGodCatcher/4.0 (by RemLover on GitHub)",
            "Accept": "application/json"
        })
        return session

    def log(self, msg): log_msg(self.name, msg)

    async def enqueue_download(self, url, filepath, filename, tags_list, artists=None):
        if artists is None: artists = []
        if filename in self.dl_history or os.path.exists(filepath):
            return False
        file_size = 0
        try:
            resp = await asyncio.to_thread(self.session.head, url, timeout=5)
            file_size = int(resp.headers.get('Content-Length', 0))
        except Exception:
            pass
        self.total_bytes += file_size
        self.download_queue.put_nowait((url, filepath, filename, tags_list, artists, file_size))
        return True

    async def _async_download_file(self, url, filepath, filename, tags_list, artists, file_size=0):
        if self.stop_event.is_set(): return False
        if filename in self.dl_history or os.path.exists(filepath): return False

        for attempt in range(self.dl_retries):
            try:
                r = await asyncio.to_thread(self.session.get, url, stream=True, timeout=30, headers={"Referer": url})
                r.raise_for_status()
                content_length = int(r.headers.get('Content-Length', 0)) or file_size
                if content_length and (content_length != file_size):
                    diff = content_length - file_size
                    self.total_bytes += diff

                downloaded = 0
                def write_file():
                    nonlocal downloaded
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(65536):
                            if self.stop_event.is_set(): break
                            f.write(chunk)
                            downloaded += len(chunk)
                await asyncio.to_thread(write_file)

                if self.stop_event.is_set():
                    if os.path.exists(filepath): os.remove(filepath)
                    return False

                self.downloaded_count += 1
                self.downloaded_bytes += downloaded
                self.dl_history.add(filename)
                save_history(self.site_root, self.dl_history)

                pct = max(0, min(100, int(self.downloaded_bytes * 100 / self.total_bytes))) if self.total_bytes > 0 else 0
                self.log(f"[SUCCESS] Downloaded {filename} ({self.downloaded_count}/{self.total_to_download}) [{pct}%]")
                rel_path = os.path.relpath(filepath, MASTER_FOLDER)
                add_to_gallery(self.name, filename, rel_path, tags_list, artists)
                write_image_metadata(filepath, tags_list, artists, self.name)
                send_tags(self.name, filename, tags_list, artists, rel_path)
                return True

            except Exception as e:
                if self.stop_event.is_set(): break
                if attempt < self.dl_retries - 1: await asyncio.sleep(2)
                else: self.log(f"[FAILED] {filename}: {e}")
        return False

    async def _download_worker(self):
        while not self.stop_event.is_set():
            if self.download_queue.empty(): break
            item = await self.download_queue.get()
            try: await self._async_download_file(*item)
            finally: self.download_queue.task_done()

    async def run_async_loop(self, scraper_coroutine):
        self.download_queue = asyncio.Queue()

        self.log("Phase 1: Gathering links from API... Please wait.")
        try: await scraper_coroutine()
        except Exception as e: self.log(f"Scraper Error: {e}")

        self.total_to_download = self.download_queue.qsize()

        if self.total_to_download > 0 and not self.stop_event.is_set():
            img_word = "image" if self.total_to_download == 1 else "images"
            label = "parallel download" if self.total_to_download > 1 else "download"
            self.log(f"Phase 2: Starting {label} of {self.total_to_download} {img_word}...")

            num_workers = 8
            download_tasks = [asyncio.create_task(self._download_worker()) for _ in range(num_workers)]

            await self.download_queue.join()
            for t in download_tasks: t.cancel()

            dw = "download" if self.downloaded_count == 1 else "downloads"
            self.log(f"--- All {self.downloaded_count} {dw} completed successfully! ---")
        else:
            if not self.stop_event.is_set():
                self.log("Task finished. No new images to download.")

        if self.name in STOP_EVENTS and self.stop_event in STOP_EVENTS[self.name]:
            STOP_EVENTS[self.name].remove(self.stop_event)
