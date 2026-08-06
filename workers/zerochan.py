import os, re, urllib.parse, json, subprocess
import asyncio
from requests.adapters import HTTPAdapter
from shared import BaseDownloader, BASE_DIR

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
    post_id = item.get("id")
    if post_id:
        return f"https://static.zerochan.net/.full.{post_id}.jpg"
    return None


class ZerochanWorker(BaseDownloader):
    def __init__(self, tag, amount, net_config):
        super().__init__("zero", "Zerochan", amount, net_config)
        self.original_tag = tag.strip().lower()

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)
        tag_parts = [urllib.parse.quote_plus(p.strip()) for p in self.original_tag.split(',')]
        self.encoded_tag = ','.join(tag_parts)

        username = os.getenv("ZEROCHAN_USERNAME", "")
        password = os.getenv("ZEROCHAN_PASSWORD", "")
        self.ua = "gallery-dl/1.32.3"
        self._zerochan_user = username
        self._zerochan_pass = password

        adapter = HTTPAdapter(max_retries=3)
        self.session.mount("https://", adapter)
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": self.ua,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.zerochan.net/{self.encoded_tag}",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })
        self.log(f"Configured: tag='{self.original_tag}' encoded='{self.encoded_tag}' "
                 f"amount={amount} UA='{self.ua}'")

    def _gallery_dl_enumerate(self, tag):
        """Enumerate all post IDs for a tag via gallery-dl (primary source)."""
        username = self._zerochan_user
        password = self._zerochan_pass
        if not username or not password:
            self.log("gallery-dl skipped: no ZEROCHAN_USERNAME/PASSWORD set")
            return []
        cmd = ["gallery-dl", "-u", username, "-p", password]
        if self.net_config.get("use_proxy"):
            cmd.extend(["--proxy", self.net_config["proxy_url"]])
        # ponytail: no --range — gallery-dl enumerates ALL posts so the worker
        # loop can keep past duplicates until collected_count hits amount
        cmd.extend(["-g", f"https://www.zerochan.net/{tag}"])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120, check=True
            )
            post_ids = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('https://static.zerochan.net/.full.'):
                    parts = line.split('.full.')
                    if len(parts) > 1:
                        pid_str = parts[-1].split('.')[0]
                        if pid_str.isdigit():
                            post_ids.append(int(pid_str))
            self.log(f"gallery-dl found {len(post_ids)} posts for '{tag}'")
            return post_ids
        except subprocess.TimeoutExpired:
            self.log(f"gallery-dl timed out for '{tag}'")
            return []
        except FileNotFoundError:
            self.log("gallery-dl not installed")
            return []
        except subprocess.CalledProcessError as e:
            self.log(f"gallery-dl failed for '{tag}': {e.stderr[:200]}")
            return []
        except Exception as e:
            self.log(f"gallery-dl error for '{tag}': {e}")
            return []

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")
        collected_count = 0

        ids = await asyncio.to_thread(self._gallery_dl_enumerate, self.encoded_tag)
        if not ids:
            self.log("No posts found via gallery-dl.")
        else:
            self.log(f"gallery-dl found {len(ids)} posts. Fetching details...")

        for pid in ids:
            if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                break

            try:
                det_resp = await asyncio.to_thread(
                    self.session.get,
                    f"https://www.zerochan.net/{pid}?json",
                    timeout=30
                )
                det_resp.raise_for_status()
                json_data = det_resp.json()
            except Exception as e:
                self.log(f"Failed to get details for post {pid}: {e}")
                continue

            img_url = _derive_img_url(json_data)
            if not img_url:
                self.log(f"No image URL found for post {pid}, skipping.")
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
                self.log(f"Enqueued download for {filename} "
                         f"(total enqueued: {collected_count})")
            await asyncio.sleep(self.anti_ban_pause)

        actual = self.download_queue.qsize() if self.download_queue else collected_count
        if actual == 0:
            self.log("No new images to download.")
        else:
            self.log(f"Finished scanning. Enqueued {actual} item"
                     f"{'s' if actual != 1 else ''}. "
                     "Completing downloads in the background...")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")


def worker_zerochan(tag, amount, net_config):
    worker = ZerochanWorker(tag, amount, net_config)
    worker.run()
