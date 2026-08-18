import os
import asyncio
from shared import BaseDownloader

class NekosiaWorker(BaseDownloader):
    def __init__(self, tag, amount, net_config):
        super().__init__("nekosia", "Nekosia", amount, net_config)
        self.tag = tag.strip().lower() if tag else "catgirl"
        self.api_base = "https://api.nekosia.cat/api/v1/images"
        self.tag_dir = os.path.join(self.site_root, self.tag)
        os.makedirs(self.tag_dir, exist_ok=True)

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: {self.tag}")

        need = self.amount or 200
        collected = 0
        batch_size = 50

        while collected < need and not self.stop_event.is_set():
            params = {"count": min(batch_size, need - collected)}

            try:
                # The endpoint is /api/v1/images/{category/tag}
                async with self.session.get(f"{self.api_base}/{self.tag}", params=params) as resp:
                    if resp.status in (403, 429):
                        self.log(f"API BAN ({resp.status}).")
                        break
                    if resp.status == 400:
                        self.log(f"Tag '{self.tag}' not found or invalid criteria.")
                        break
                    resp.raise_for_status()
                    data = await resp.json()

                images = data.get("images", [])
                if not images:
                    self.log("No more images found.")
                    break
            except Exception as e:
                self.log(f"API error: {e}")
                break

            for img in images:
                if self.stop_event.is_set() or collected >= need: break
                
                # Try getting the original image URL, fallback to compressed
                img_data = img.get("image", {})
                url_data = img_data.get("original") or img_data.get("compressed")
                if not url_data: continue
                url = url_data.get("url")
                if not url: continue
                
                img_id = img.get("id", "unknown")
                ext = url_data.get("extension", "jpg")
                filename = f"{img_id}.{ext}"
                filepath = os.path.join(self.tag_dir, filename)
                
                tags = img.get("tags", [])
                attr = img.get("attribution", {})
                artist_name = attr.get("artist", {}).get("username")
                artists = [artist_name] if artist_name else []
                
                if await self.enqueue_download(url, filepath, filename, tags, artists):
                    collected += 1

            if collected >= need or not images: break
            if not self.stop_event.is_set():
                await asyncio.sleep(self.anti_ban_pause)

        if collected:
            self.log(f"Enqueued {collected} item{'s' if collected != 1 else ''}.")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_nekosia(tag, amount, net_config):
    NekosiaWorker(tag, amount, net_config).run()
