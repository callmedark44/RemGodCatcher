import os
import threading
import json
import time
import asyncio
import hashlib
import aiohttp
from PIL import Image, PngImagePlugin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_FOLDER = os.path.join(BASE_DIR, "Rem God")
HISTORY_LOCK = threading.Lock()
STOP_EVENTS = {}

SAFE_TAGS_DB = []
WAIFU_TAGS_DB = []
WAIFU_TAG_MAP = {}

def get_session(site, net_config):
    """Legacy sync helper – kept for Flask tag-suggestion endpoints."""
    import requests as _requests
    session = _requests.Session()
    if net_config.get("use_proxy"):
        p = net_config.get("proxy_url")
        session.proxies = {"http": p, "https": p}
    else:
        session.proxies = {"http": "", "https": "", "no_proxy": "*"}
    session.verify = net_config.get("verify_tls", False)
    return session

# --- LOGGING & TAG SYSTEM ---
def default_logger(worker_name, msg): print(f"[{worker_name.upper()}] {msg}")
log_callback = default_logger
def log_msg(worker_name, msg): log_callback(worker_name, msg)

def default_tag_handler(worker_name, filename, tags_list, artist_list, filepath=None): pass
tag_callback = default_tag_handler
def send_tags(worker_name, filename, tags_list, artist_list=None, filepath=None):
    if artist_list is None: artist_list = []
    tag_callback(worker_name, filename, tags_list, artist_list, filepath)

def default_emit(event, data): pass
emit_callback = default_emit
def socketio_emit(event, data): emit_callback(event, data)

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

        self.session = None  # created lazily in _create_session
        self.downloaded_count = 0
        self.failed_count = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.total_to_download = 0
        self.download_queue = None
        self.is_scanning = False
        self.enqueued_count = 0
        self.queued_items = set()

    def check_amount_warning(self, total_found):
        """Helper to warn the user if they requested more images than are available."""
        if total_found > 0:
            self.log(f"Total valid items found: {total_found}")
            if self.amount > 0 and total_found < self.amount:
                self.log(f"⚠️ Notice: You requested {self.amount} images, but only {total_found} exist.")

    # --- aiohttp session factory (override in subclasses for curl_cffi etc.) ---
    async def _create_session(self):
        """Create and return an aiohttp.ClientSession with proxy and headers."""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        headers = {
            "User-Agent": "RemGodCatcher/4.0 (by RemLover on GitHub)",
            "Accept": "application/json",
        }
        proxy = None
        if self.net_config.get("use_proxy"):
            proxy = self.net_config.get("proxy_url")
        if not proxy:
            proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

        connector = aiohttp.TCPConnector(
            ssl=False if not self.net_config.get("verify_tls", False) else None,
            limit=10,
        )
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers,
            proxy=proxy,
        )
        return session

    def log(self, msg): log_msg(self.name, msg)

    async def enqueue_download(self, url, filepath, filename, tags_list, artists=None):
        if artists is None: artists = []
        
        if filename in self.dl_history or filename in self.queued_items or os.path.exists(filepath):
            return False
            
        file_size = 0
        try:
            async with self.session.head(url) as resp:
                file_size = int(resp.headers.get('Content-Length', 0))
        except Exception:
            pass
            
        self.total_bytes += file_size
        self.queued_items.add(filename)
        self.download_queue.put_nowait((url, filepath, filename, tags_list, artists, file_size))
        self.enqueued_count += 1
        return True

    async def _async_download_file(self, url, filepath, filename, tags_list, artists, file_size=0):
        if self.stop_event.is_set():
            self.enqueued_count -= 1
            return False

        for attempt in range(self.dl_retries):
            try:
                referer = self.session.headers.get("Referer") or url
                async with self.session.get(url, headers={"Referer": referer}) as resp:
                    resp.raise_for_status()
                    content_length = int(resp.headers.get('Content-Length', 0)) or file_size
                    if content_length and (content_length != file_size):
                        self.total_bytes += (content_length - file_size)

                    downloaded = 0
                    with open(filepath, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            if self.stop_event.is_set(): break
                            f.write(chunk)
                            downloaded += len(chunk)

                if self.stop_event.is_set():
                    if os.path.exists(filepath): os.remove(filepath)
                    self.enqueued_count -= 1
                    return False

                self.downloaded_count += 1
                self.downloaded_bytes += downloaded
                self.dl_history.add(filename)
                save_history(self.site_root, self.dl_history)

                # درصدگیری بی‌نقص بر اساس Limit
                if self.is_scanning and self.amount > 0:
                    target_total = max(self.amount, self.enqueued_count)
                else:
                    target_total = max(self.enqueued_count, self.downloaded_count)
                    
                pct = int((self.downloaded_count / target_total) * 100) if target_total > 0 else 0
                
                rel_path = os.path.relpath(filepath, MASTER_FOLDER)
                top_tags = ", ".join(tags_list[:5]) if tags_list else "No tags"
                self.log(f"[SUCCESS] Downloaded {filename} ({self.downloaded_count}/{target_total}) [{pct}%] |PATH| {rel_path} |TAGS| {top_tags}")
                
                add_to_gallery(self.name, filename, rel_path, tags_list, artists)
                write_image_metadata(filepath, tags_list, artists, self.name)
                send_tags(self.name, filename, tags_list, artists, rel_path)
                return True

            except Exception as e:
                if self.stop_event.is_set():
                    self.enqueued_count -= 1
                    break
                if attempt < self.dl_retries - 1: 
                    await asyncio.sleep(2)
                else: 
                    self.enqueued_count -= 1
                    err_msg = str(e).strip()
                    if not err_msg: err_msg = "HTTP 404 / File Deleted from Server"
                    self.log(f"[FAILED] {filename}: {err_msg}")
                    self.failed_count += 1
        return False

    async def _download_worker(self):
        while not self.stop_event.is_set():
            if self.download_queue.empty():
                if not self.is_scanning: break
                await asyncio.sleep(0.5)
                continue
            item = await self.download_queue.get()
            try: await self._async_download_file(*item)
            finally: self.download_queue.task_done()

    async def run_async_loop(self, scraper_coroutine):
        try:
            self.session = await self._create_session()
            self.download_queue = asyncio.Queue()
            self.is_scanning = True

            num_workers = 4
            download_tasks = [asyncio.create_task(self._download_worker()) for _ in range(num_workers)]

            self.log("Phase 1: Gathering links from API... Please wait.")
            try: await scraper_coroutine()
            except Exception as e: self.log(f"Scraper Error: {e}")

            self.is_scanning = False
            self.total_to_download = self.download_queue.qsize() + self.downloaded_count

            if self.total_to_download > 0 and not self.stop_event.is_set():
                await self.download_queue.join()
                for t in download_tasks: t.cancel()
                if self.failed_count > 0:
                    self.log(f"--- Task finished: {self.downloaded_count} downloaded successfully, {self.failed_count} failed to download! ---")
                else:
                    self.log(f"--- All {self.downloaded_count} downloads completed successfully! ---")
            else:
                for t in download_tasks: t.cancel()
                if not self.stop_event.is_set(): self.log("Task finished. No new images to download.")
        except Exception as critical_e:
            self.log(f"CRITICAL ERROR: {critical_e}")
        finally:
            if self.session and hasattr(self.session, 'closed') and not self.session.closed:
                await self.session.close()

        if self.name in STOP_EVENTS and self.stop_event in STOP_EVENTS[self.name]:
            STOP_EVENTS[self.name].remove(self.stop_event)
