import os, re
import asyncio
from shared import BaseDownloader

class SafebooruWorker(BaseDownloader):
    def __init__(self, tag, amount, exclusions, net_config):
        super().__init__("safe", "Safebooru", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.exclusions = exclusions

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?:"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")

        collected_count = 0
        pid = 0

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {pid})")
                limit_val = min(100, self.amount - collected_count if self.amount > 0 else 100)

                resp = await asyncio.to_thread(self.session.get, "https://safebooru.org/index.php", params={
                    "page": "dapi", "s": "post", "q": "index",
                    "tags": self.original_tag, "pid": pid, "limit": limit_val, "json": 1
                }, timeout=15)
                if resp.status_code in [403, 429]:
                    self.log(f"ERROR {resp.status_code}. Change proxy.")
                    break
                resp.raise_for_status()

                data = resp.json()
                if isinstance(data, dict):
                    posts = data.get("post", [])
                elif isinstance(data, list):
                    posts = data
                else:
                    posts = []
                if not posts:
                    if pid == 0:
                        self.log(f"ZERO images found for '{self.original_tag}'.")
                    else:
                        self.log("End of database reached.")
                    break

            except Exception as e:
                err_str = str(e)
                if "403" in err_str:
                    self.log("ERROR 403: Cloudflare/ISP block. You need a VPN.")
                else:
                    self.log(f"API Error: {e}")
                await asyncio.sleep(5)
                continue

            had_valid = False
            for post in posts:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                    break
                if not isinstance(post, dict):
                    continue

                file_url = post.get("file_url") or post.get("large_file_url")
                if not file_url:
                    continue

                ext = file_url.split('.')[-1].lower().split('?')[0]
                if ext in ["mp4", "webm", "zip"] and "-video" in self.exclusions:
                    continue
                if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in self.exclusions:
                    continue
                if ext == "gif" and "-gif" in self.exclusions:
                    continue

                filename = f"{post.get('id')}.{ext}"
                filepath = os.path.join(self.tag_dir, filename)

                tags_raw = post.get("tag_string", post.get("tags", ""))
                tags_list = [t.strip() for t in tags_raw.split() if t.strip()]
                artists = [t.strip() for t in post.get("tag_string_artist", "").split() if t.strip()]

                self.enqueue_download(file_url, filepath, filename, tags_list, artists)
                collected_count += 1
                had_valid = True

            pid += 1
            if had_valid and not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        if collected_count == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {collected_count} items. Completing downloads in background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_safebooru(tag, amount, exclusions, net_config):
    worker = SafebooruWorker(tag, amount, exclusions, net_config)
    worker.run()
