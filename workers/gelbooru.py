import os, re
import asyncio
from shared import BaseDownloader

class GelbooruWorker(BaseDownloader):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("gelbooru", "Gelbooru", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.rating = rating
        self.exclusions = exclusions
        
        dan_to_gel_rating = {"rating:g": "rating:general", "rating:s": "rating:sensitive", "rating:q": "rating:questionable", "rating:e": "rating:explicit"}
        self.api_tag = self.original_tag
        if self.rating:
            api_rating = dan_to_gel_rating.get(self.rating, self.rating)
            self.api_tag = f"{self.original_tag} {api_rating}".strip()
            
        self.rating_code_map = {"g": "general", "s": "sensitive", "q": "questionable", "e": "explicit"}
        self.rating_label_map = {"general": "Safe", "sensitive": "Sensitive", "questionable": "Questionable", "explicit": "NSFW"}
        
        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag_name = re.sub(r'[\\/*?"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag_name)
        os.makedirs(self.tag_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.api_tag}'")
        api_key = os.getenv("GELBOORU_API_KEY", "")
        user_id = os.getenv("GELBOORU_USER_ID", "")

        collected_count = 0
        pid = 0

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log(f"Scanning API... (Page {pid})")
                limit_val = min(100, self.amount - collected_count if self.amount > 0 else 100)
                params = {"page": "dapi", "s": "post", "q": "index", "tags": self.api_tag, "pid": pid, "limit": limit_val, "json": 1}
                if api_key and user_id:
                    params["api_key"] = api_key
                    params["user_id"] = user_id

                resp = await asyncio.to_thread(self.session.get, "https://gelbooru.com/index.php", params=params, timeout=15)
                if resp.status_code == 401:
                    self.log("ERROR 401: Unauthorized! Enter API Key in Options.")
                    break
                elif resp.status_code in [403, 429]:
                    self.log(f"ERROR {resp.status_code}. Change proxy or slow down.")
                    break
                
                resp.raise_for_status()
                posts = resp.json().get("post", [])
                
                if not posts:
                    if pid == 0: self.log(f"0 images found for '{self.original_tag}'.")
                    else: self.log("End of database reached.")
                    break

            except Exception as e:
                self.log(f"API Error: {e}")
                await asyncio.sleep(5)
                continue

            had_valid = False
            for post in posts:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount): break
                if not isinstance(post, dict): continue

                post_rating = post.get("rating", "")
                if self.rating:
                    filter_code = self.rating.split(":")[-1]
                    if post_rating != self.rating_code_map.get(filter_code, filter_code): continue

                file_url = post.get("file_url", "")
                if not file_url: continue

                ext = file_url.split('.')[-1].lower()
                if ext in ["mp4", "webm", "zip"] and "-video" in self.exclusions: continue
                if ext in ["jpg", "jpeg", "png", "webp"] and "-image" in self.exclusions: continue
                if ext == "gif" and "-gif" in self.exclusions: continue

                filename = file_url.split('/')[-1].split('?')[0]
                rating_label = self.rating_label_map.get(post_rating, "Unknown")
                
                tags_list = [t.strip() for t in post.get("tags", "").split() if t.strip()]
                artists = [t.replace("artist:", "", 1) for t in tags_list if t.startswith("artist:")]
                tags_list = [t for t in tags_list if not t.startswith("artist:")]

                rating_dir = os.path.join(self.tag_dir, rating_label, "images")
                os.makedirs(rating_dir, exist_ok=True)
                filepath = os.path.join(rating_dir, filename)

                if await self.enqueue_download(file_url, filepath, filename, tags_list, artists):
                    collected_count += 1
                    had_valid = True

            pid += 1
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

def worker_gelbooru(tag, amount, rating, exclusions, net_config):
    worker = GelbooruWorker(tag, amount, rating, exclusions, net_config)
    worker.run()
