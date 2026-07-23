import os, re
import asyncio
from shared import BaseDownloader

class DanbooruWorker(BaseDownloader):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("dan", "Danbooru", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.rating = rating
        self.exclusions = exclusions

        self.api_tag = self.original_tag
        if self.rating:
            self.api_tag = f"{self.original_tag} {self.rating}".strip()

        self.rating_map = {"g": "Safe", "s": "Sensitive", "q": "Questionable", "e": "NSFW"}
        self.video_exts = {"mp4", "webm"}

        FORMAT_WORDS = {"video", "image"}
        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-') and t not in FORMAT_WORDS)
        self.safe_tag = re.sub(r'[\\/*?"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.api_tag}'")

        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {page})")
                limit_val = min(200, self.amount - collected_count if self.amount > 0 else 200)

                resp = await asyncio.to_thread(self.session.get, "https://danbooru.donmai.us/posts.json", params={"tags": self.api_tag, "page": page, "limit": limit_val}, timeout=15)
                if resp.status_code in [403, 429]:
                    self.log(f"ERROR {resp.status_code}. Change proxy.")
                    break
                resp.raise_for_status()

                posts = resp.json()
                if not isinstance(posts, list):
                    break

                if not posts:
                    if page == 1:
                        self.log(f"ZERO images found for '{self.api_tag}'.")
                    else:
                        self.log("End of database reached.")
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
                if ext in ["mp4", "webm", "zip"] and "-video" in self.exclusions:
                    continue
                if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in self.exclusions:
                    continue
                if ext == "gif" and "-gif" in self.exclusions:
                    continue
                if ext not in ["jpg", "jpeg", "png", "gif", "webp", "mp4", "webm"]:
                    continue

                filename = f"{post.get('id')}.{ext}"
                is_video = ext in self.video_exts
                rating_label = self.rating_map.get(post_rating, "Unknown")
                rating_dir = os.path.join(self.tag_dir, rating_label, "video" if is_video else "images")
                os.makedirs(rating_dir, exist_ok=True)
                filepath = os.path.join(rating_dir, filename)

                tags_raw = post.get("tag_string", "")
                tags_list = [t.strip() for t in tags_raw.split() if t.strip()]
                artists = [t.replace("artist:", "", 1) for t in tags_list if t.startswith("artist:")]
                tags_list = [t for t in tags_list if not t.startswith("artist:")]

                if await self.enqueue_download(url, filepath, filename, tags_list, artists):
                    collected_count += 1
                    had_valid = True

            page += 1
            if had_valid and not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        actual = self.download_queue.qsize() if self.download_queue else collected_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {actual} item{'s' if actual != 1 else ''}. Completing downloads in the background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_danbooru(tag, amount, rating, exclusions, net_config):
    worker = DanbooruWorker(tag, amount, rating, exclusions, net_config)
    worker.run()
