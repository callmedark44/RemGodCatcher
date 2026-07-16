import os, re
import asyncio
from shared import BaseDownloader

class YandeWorker(BaseDownloader):
    def __init__(self, tag, amount, rating, net_config):
        super().__init__("yande", "Yande.re", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.rating = rating

        self.api_tag = self.original_tag
        if self.rating:
            self.api_tag = f"{self.original_tag} {self.rating}".strip()

        self.rating_map = {"s": "Safe", "q": "Moderate", "e": "NSFW"}

        FORMAT_WORDS = {"video", "image"}
        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-') and t not in FORMAT_WORDS)
        self.safe_tag = re.sub(r'[\\/*?:"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.api_tag}'")

        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {page})")
                limit_val = min(100, self.amount - collected_count if self.amount > 0 else 100)

                resp = await asyncio.to_thread(self.session.get, "https://yande.re/post.json", params={"tags": self.api_tag, "page": page, "limit": limit_val}, timeout=15)
                if resp.status_code in [403, 429]:
                    self.log(f"ERROR {resp.status_code}. Change proxy.")
                    break
                resp.raise_for_status()

                text_resp = resp.text.strip()
                if not text_resp or text_resp == "[]":
                    if page == 1:
                        self.log(f"ZERO images found for '{self.api_tag}'.")
                    break

                raw_data = resp.json()
                if isinstance(raw_data, dict):
                    if "success" in raw_data and not raw_data["success"]:
                        self.log(f"API Alert: {raw_data.get('message', 'Unknown Error')}")
                        break
                    posts = [raw_data]
                elif isinstance(raw_data, list):
                    posts = raw_data
                else:
                    break

                if not posts:
                    break

            except Exception as e:
                err_str = str(e)
                if "403" in err_str:
                    self.log("ERROR 403: Cloudflare/ISP block. You need a proxy.")
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

                post_rating = post.get("rating", "")
                if self.rating:
                    filter_rating = self.rating.split(":")[-1]
                    if post_rating != filter_rating:
                        continue

                url = post.get("file_url") or post.get("large_file_url")
                if not url:
                    continue

                ext = (post.get("file_ext") or "").lower()
                if ext not in ["jpg", "jpeg", "png"]:
                    continue

                filename = f"{post.get('id')}.{ext}"
                rating_label = self.rating_map.get(post_rating, "Unknown")
                rating_dir = os.path.join(self.tag_dir, rating_label, "images")
                os.makedirs(rating_dir, exist_ok=True)
                filepath = os.path.join(rating_dir, filename)

                tags_raw = post.get("tags", "")
                tags_list = [t.strip() for t in tags_raw.split() if t.strip()]
                artists = [t.replace("artist:", "", 1) for t in tags_list if t.startswith("artist:")]
                tags_list = [t for t in tags_list if not t.startswith("artist:")]

                self.enqueue_download(url, filepath, filename, tags_list, artists)
                collected_count += 1
                had_valid = True

            page += 1
            if had_valid and not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        if collected_count == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {collected_count} items. Completing downloads in background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_yande(tag, amount, rating, net_config):
    worker = YandeWorker(tag, amount, rating, net_config)
    worker.run()
