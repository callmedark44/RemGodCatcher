import os, re, urllib.parse
import asyncio
from shared import BaseDownloader

def _derive_img_url(item):
    keys = ["full", "large", "file_url", "source", "src", "url", "image"]
    for k in keys:
        v = item.get(k)
        if v:
            return v
    thumb = item.get("thumb", "")
    if thumb:
        no_thumb = thumb.replace(".thumb.", ".")
        if no_thumb != thumb:
            return no_thumb
    return None

class ZerochanWorker(BaseDownloader):
    def __init__(self, tag, amount, net_config):
        super().__init__("zero", "Zerochan", amount, net_config)
        self.original_tag = tag.strip().lower()

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?:"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)
        self.encoded_tag = urllib.parse.quote_plus(self.original_tag)

        self.session.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.zerochan.net/{self.encoded_tag}",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        })

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")

        collected_count = 0
        page = 1
        collected_ids = []
        api_exhausted = False
        first_page = True

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount) and not api_exhausted:
            if not collected_ids:
                try:
                    self.log(f"Scanning API... (Page {page})")
                    resp = await asyncio.to_thread(
                        self.session.get,
                        f"https://www.zerochan.net/{self.encoded_tag}",
                        params={"json": "1", "p": page, "l": 48},
                        timeout=30
                    )
                    resp.raise_for_status()
                    items = resp.json().get("items", [])
                    if not items:
                        self.log("End of database reached.")
                        api_exhausted = True
                        break
                    for item in items:
                        post_id = item.get("id")
                        if post_id:
                            collected_ids.append(post_id)
                    page += 1
                    if not first_page:
                        await asyncio.sleep(self.anti_ban_pause)
                    first_page = False
                except Exception as e:
                    self.log(f"Network/Limit: {e}")
                    break

            if not collected_ids:
                continue

            post_id = collected_ids.pop(0)

            try:
                det_resp = await asyncio.to_thread(self.session.get, f"https://www.zerochan.net/{post_id}?json", timeout=30)
                json_data = det_resp.json()
            except Exception as e:
                self.log(f"Failed to get details for post {post_id}: {e}")
                continue

            img_url = _derive_img_url(json_data)
            if not img_url:
                self.log(f"No image URL found for post {post_id}, skipping.")
                continue

            tags_raw = json_data.get("tags", [])
            if isinstance(tags_raw, str):
                tags_list = [t.strip() for t in tags_raw.replace(",", " ").split() if t.strip()]
            else:
                tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]

            filename = urllib.parse.unquote(img_url.split('/')[-1])
            filepath = os.path.join(self.tag_dir, filename)

            if await self.enqueue_download(img_url, filepath, filename, tags_list, []):
                collected_count += 1

        actual = self.download_queue.qsize() if self.download_queue else collected_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {actual} item{'s' if actual != 1 else ''}. Completing downloads in the background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_zerochan(tag, amount, net_config):
    worker = ZerochanWorker(tag, amount, net_config)
    worker.run()
