import os
import asyncio
from shared import BaseDownloader

class NekosBestWorker(BaseDownloader):
    def __init__(self, category, amount, net_config):
        super().__init__("neko", "Nekos.best", amount, net_config)
        self.category = category
        self.cat_dir = os.path.join(self.site_root, category)
        os.makedirs(self.cat_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for category: '{self.category}'")

        collected_count = 0
        max_retries = 3
        consecutive_failures = 0

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            batch_size = min(20, self.amount - collected_count if self.amount > 0 else 20)
            fetch_url = f"https://nekos.best/api/v2/{self.category}?amount={batch_size}"

            try:
                self.log("Scanning API...")
                resp = await asyncio.to_thread(self.session.get, fetch_url, timeout=15)
                if resp.status_code in [403, 429]:
                    self.log(f"API BAN ({resp.status_code}). Change VPN node.")
                    break
                resp.raise_for_status()
                results = resp.json().get("results", [])
                consecutive_failures = 0
                if not results:
                    self.log("End of database reached.")
                    break
            except Exception as e:
                consecutive_failures += 1
                self.log(f"Network delay, retrying... ({consecutive_failures}/{max_retries}) ({e})")
                if consecutive_failures >= max_retries:
                    self.log(f"API unreachable after {max_retries} attempts. Skipping.")
                    break
                await asyncio.sleep(5)
                continue

            for item in results:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                    break
                url = item.get("url")
                if not url:
                    continue
                filename = url.split('/')[-1]
                filepath = os.path.join(self.cat_dir, filename)
                self.enqueue_download(url, filepath, filename, [self.category], [])
                collected_count += 1

            if not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

        if collected_count == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {collected_count} items. Completing downloads in background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_nekos_best(category, amount, net_config):
    worker = NekosBestWorker(category, amount, net_config)
    worker.run()
