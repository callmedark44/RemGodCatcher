import os, re, hashlib
import asyncio
from workers import BaseWorker


class KonachanWorker(BaseWorker):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("kona", "Konachan", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.rating = rating
        self.exclusions = exclusions

        self.api_tag = self.original_tag
        if self.rating:
            self.api_tag = f"{self.original_tag} {self.rating}".strip()

        self.rating_map = {"s": "Safe", "q": "Questionable", "e": "NSFW"}

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?:"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)

    def get_tags(self):
        return [self.original_tag]

    async def download_image(self, url, filepath, filename, tags_list, artists=None):
        return await self.enqueue_download(url, filepath, filename, tags_list, artists or [])

    async def fetch_posts(self):
        await self.scraper_task()

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.api_tag}'")

        auth = {}
        kona_user = os.getenv("KONACHAN_USERNAME", "")
        kona_pass = os.getenv("KONACHAN_PASSWORD", "")
        if kona_user and kona_pass:
            # moebooru salt per their API docs
            pw_hash = hashlib.sha1(f"So-I-Heard-You-Like-Mupkids-?--{kona_pass}--".encode()).hexdigest()
            auth = {"login": kona_user, "password_hash": pw_hash}
            self.log(f"Authenticating as '{kona_user}' (needed for questionable/explicit).")
        else:
            self.log("No Konachan credentials loaded - running as anonymous (safe content only).")

        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {page})")
                limit_val = min(100, self.amount - collected_count if self.amount > 0 else 100)

                resp = await self.session.get("https://konachan.com/post.json", params={"tags": self.api_tag, "page": page, "limit": limit_val, **auth})
                if resp.status in [403, 429]:
                    self.log(f"ERROR {resp.status}. Change proxy.")
                    break
                resp.raise_for_status()

                text_resp = (await resp.text()).strip()
                if not text_resp or text_resp == "[]" or text_resp == "null":
                    if page == 1:
                        self.log(f"ZERO images found for '{self.api_tag}'.")
                        if self.rating and self.rating.split(":")[-1] in ("q", "e"):
                            if auth:
                                self.log("Authenticated, got 0 non-safe posts. Check 'Show explicit content' is enabled in your konachan.com profile settings.")
                            else:
                                self.log("No Konachan credentials configured (Options tab) - non-safe content needs a logged-in account.")
                    break

                raw_data = await resp.json()
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
                if ext in ["mp4", "webm", "zip"] and "-video" in self.exclusions:
                    continue
                if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in self.exclusions:
                    continue
                if ext == "gif" and "-gif" in self.exclusions:
                    continue
                if ext not in ["jpg", "jpeg", "png", "gif", "webp", "mp4", "webm"]:
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

                if await self.enqueue_download(url, filepath, filename, tags_list, artists):
                    collected_count += 1
                    had_valid = True

            page += 1
            if had_valid and not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        actual = self.enqueued_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.check_amount_warning(actual)

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_konachan(tag, amount, rating, exclusions, net_config):
    worker = KonachanWorker(tag, amount, rating, exclusions, net_config)
    worker.run()
