import os, re
import asyncio
from workers import BaseWorker

API_BASE = "https://gsbooru.org/api/posts"
RATE_LIMIT_PAUSE = 5.0  # gsbooru.org: strictly 1 query per 5 seconds per API key


class GsbooruWorker(BaseWorker):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("gsbooru", "Gsbooru", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.rating = rating
        self.exclusions = exclusions

        # UI sends danbooru-style codes (rating:g/s/q/e)
        self.filter_code = self.rating.split(":")[-1] if self.rating else ""
        # API returns integer ratings {0: g, 1: s, 2: q, 3: e}
        self.rating_int_map = {"g": 0, "s": 1, "q": 2, "e": 3}
        self.rating_label_map = {"g": "Safe", "s": "Sensitive", "q": "Questionable", "e": "NSFW"}

        self.api_tag = f"{self.original_tag} {self.rating}".strip()

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag_name = re.sub(r'[\\/*?:"<>|]', "", clean_tag) or "all"
        self.tag_dir = os.path.join(self.site_root, self.safe_tag_name)
        os.makedirs(self.tag_dir, exist_ok=True)

    def get_tags(self):
        return [self.original_tag]

    async def download_image(self, url, filepath, filename, tags_list, artists=None):
        return await self.enqueue_download(url, filepath, filename, tags_list, artists or [])

    async def fetch_posts(self):
        await self.scraper_task()

    async def scraper_task(self):
        api_key = os.getenv("GSBOORU_API_KEY", "")
        if not api_key:
            self.log("ERROR: No GSBOORU_API_KEY set! Generate one at gsbooru.org and add it in Options.")
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "RemGodCatcher/1.0 (image downloader; contact via github)",
        }

        self.log(f"Initializing worker for tag: '{self.api_tag}'")

        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {page})")
                limit_val = min(100, self.amount - collected_count if self.amount > 0 else 100)

                resp = await self.session.get(API_BASE, params={"tags": self.api_tag, "page": page, "limit": limit_val}, headers=headers)
                if resp.status == 401:
                    self.log("ERROR 401: Unauthorized! Check your GSBOORU_API_KEY in Options.")
                    break
                elif resp.status == 429:
                    self.log("Rate limited (429). Waiting 10s...")
                    await asyncio.sleep(10)
                    continue
                elif resp.status in [403, 500]:
                    self.log(f"ERROR {resp.status}.")
                    break

                resp.raise_for_status()
                data = await resp.json()
                posts = data.get("posts", [])

                if not posts:
                    if page == 1:
                        self.log(f"0 images found for '{self.original_tag}'.")
                    else:
                        self.log("End of database reached.")
                    break

            except Exception as e:
                self.log(f"API Error: {e}")
                await asyncio.sleep(5)
                continue

            had_valid = False
            for post in posts:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                    break
                if not isinstance(post, dict):
                    continue

                rating_int = post.get("rating", -1)
                code_by_int = {v: k for k, v in self.rating_int_map.items()}
                post_rating = code_by_int.get(rating_int, "")
                if not post_rating:
                    continue
                if self.filter_code and post_rating != self.filter_code:
                    continue

                file_url = post.get("file_url", "")
                if not file_url:
                    continue

                ext = (post.get("file_ext") or "").lstrip(".").lower()
                if ext in ["mp4", "webm", "zip"] and "-video" in self.exclusions:
                    continue
                if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in self.exclusions:
                    continue
                if ext == "gif" and "-gif" in self.exclusions:
                    continue

                tags_list = [t.strip() for t in post.get("tag_string", "").split() if t.strip()]
                artists = [t.replace("artist:", "", 1) for t in tags_list if t.startswith("artist:")]
                tags_list = [t for t in tags_list if not t.startswith("artist:")]

                filename = file_url.split('/')[-1].split('?')[0]
                rating_label = self.rating_label_map[post_rating]
                is_video = ext in ["mp4", "webm"]

                rating_dir = os.path.join(self.tag_dir, rating_label, "video" if is_video else "images")
                os.makedirs(rating_dir, exist_ok=True)
                filepath = os.path.join(rating_dir, filename)

                if await self.enqueue_download(file_url, filepath, filename, tags_list, artists):
                    collected_count += 1
                    had_valid = True

            page += 1
            if not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(RATE_LIMIT_PAUSE)

        actual = self.enqueued_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.check_amount_warning(actual)

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")


def worker_gsbooru(tag, amount, rating, exclusions, net_config):
    worker = GsbooruWorker(tag, amount, rating, exclusions, net_config)
    worker.run()
