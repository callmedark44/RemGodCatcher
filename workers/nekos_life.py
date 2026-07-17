import os
import asyncio
from shared import BaseDownloader

GIF_ONLY = {"ngif", "hug", "pat", "cuddle", "tickle", "feed", "slap", "kiss", "smug"}
STATIC_ONLY = {"gecg", "meow", "neko", "lewd", "gasm", "8ball", "avatar", "woof", "fox_girl", "waifu"}
MIXED = {"goose", "wallpaper", "lizard", "span"}

class NekosLifeWorker(BaseDownloader):
    def __init__(self, category, amount, net_config, fmt="both"):
        super().__init__("nekos_life", "Nekos.life", amount, net_config)
        self.category = category
        self.fmt = fmt

        self.gifs_root = os.path.join(self.site_root, "Gifs")
        self.images_root = os.path.join(self.site_root, "Images")
        self.api_base = "https://nekos.life/api/v2"
        self.fetch_url = f"{self.api_base}/img/{category}"

    async def scraper_task(self):
        if self.category in GIF_ONLY:
            self.log(f"Initializing worker for category: '{self.category}' [GIF ONLY]")
        elif self.category in STATIC_ONLY:
            self.log(f"Initializing worker for category: '{self.category}' [STATIC ONLY]")
        elif self.category in MIXED:
            self.log(f"Initializing worker for category: '{self.category}' [MIXED] [Format: {self.fmt}]")
        else:
            self.log(f"Initializing worker for category: '{self.category}' [UNKNOWN TYPE]")

        collected_count = 0
        consecutive_failures = 0
        max_retries = 3

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                self.log("Scanning API...")
                resp = await asyncio.to_thread(self.session.get, self.fetch_url, timeout=15)
                if resp.status_code in [403, 429]:
                    self.log(f"API BAN ({resp.status_code}). Change VPN node.")
                    break
                resp.raise_for_status()
                data = resp.json()
                url = data.get("url")
                if not url:
                    self.log("No URL in response.")
                    break
                consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                self.log(f"Network delay, retrying... ({consecutive_failures}/{max_retries}) ({e})")
                if consecutive_failures >= max_retries:
                    self.log(f"API unreachable after {max_retries} attempts. Skipping.")
                    break
                await asyncio.sleep(5)
                continue

            if self.stop_event.is_set():
                break

            filename = url.split('/')[-1]
            is_gif = filename.lower().endswith(".gif")

            if self.category in MIXED:
                if self.fmt == "gif" and not is_gif:
                    continue
                elif self.fmt == "image" and is_gif:
                    continue

            type_dir = os.path.join(self.gifs_root if is_gif else self.images_root, self.category)
            os.makedirs(type_dir, exist_ok=True)
            filepath = os.path.join(type_dir, filename)

            if await self.enqueue_download(url, filepath, filename, [self.category], []):
                collected_count += 1

            if not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        actual = self.download_queue.qsize() if self.download_queue else collected_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {actual} item{'s' if actual != 1 else ''}. Completing downloads in the background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_nekos_life(category, amount, net_config, fmt="both"):
    worker = NekosLifeWorker(category, amount, net_config, fmt)
    worker.run()
