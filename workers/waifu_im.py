import os, re
import asyncio
from shared import BaseDownloader, WAIFU_TAG_MAP

def waifu_name_to_slug(name):
    name_lower = name.lower().strip()
    if name_lower in WAIFU_TAG_MAP:
        return WAIFU_TAG_MAP[name_lower]
    return name_lower.replace(" ", "-")

class WaifuImWorker(BaseDownloader):
    def __init__(self, tag, amount, is_nsfw, net_config):
        super().__init__("waifu", "Waifu.im", amount, net_config)
        self.original_tag = tag.lower()
        self.slug = waifu_name_to_slug(self.original_tag)
        self.is_nsfw = is_nsfw

        self.api_timeout = int(net_config.get("api_timeout", 10))
        self.retry_wait = int(net_config.get("retry_wait", 5))

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?:"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        self.subdir = "NSFW" if is_nsfw else "Safe"
        os.makedirs(os.path.join(self.tag_dir, self.subdir), exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}' -> slug: '{self.slug}' (NSFW: {self.is_nsfw})")

        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            params = {"IncludedTags": self.slug, "page": page}
            if self.is_nsfw:
                params["IsNsfw"] = "true"

            try:
                self.log(f"Scanning API... (Page {page})")
                resp = await asyncio.to_thread(self.session.get, "https://api.waifu.im/images", params=params, timeout=self.api_timeout)
                if resp.status_code == 404:
                    self.log("ERROR 404: Tag not found!")
                    break
                elif resp.status_code == 403:
                    self.log("ERROR 403: Adult tag detected. Check NSFW box.")
                    break
                resp.raise_for_status()

                data = resp.json()
                items = data.get("items", [])
                total = data.get("totalCount", 0)

                if not items or total == 0:
                    if self.is_nsfw:
                        self.log(f"No NSFW images found for '{self.original_tag}'.")
                    else:
                        self.log(f"No images found for '{self.original_tag}'.")
                    break
            except Exception as e:
                self.log(f"API Error: {e}. Retrying in {self.retry_wait}s...")
                await asyncio.sleep(self.retry_wait)
                continue

            for img in items:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                    break
                url = img.get("url")
                if not url:
                    continue

                filename = url.split('/')[-1]
                filepath = os.path.join(self.tag_dir, self.subdir, filename)

                self.enqueue_download(url, filepath, filename, [self.original_tag], [])
                collected_count += 1

            page += 1
            has_next = data.get("hasNextPage", False)
            if not has_next or self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                break
            await asyncio.sleep(self.anti_ban_pause)

        if collected_count == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {collected_count} items. Completing downloads in background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_waifu(tag, amount, is_nsfw, net_config):
    worker = WaifuImWorker(tag, amount, is_nsfw, net_config)
    worker.run()
