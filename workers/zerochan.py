import os, re, urllib.parse, subprocess
import asyncio
from requests.adapters import HTTPAdapter
from shared import BaseDownloader

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

        username = net_config.get("zerochan_login", "")
        password = net_config.get("zerochan_password", "")
        self.ua = "gallery-dl/1.32.3"
        self._zerochan_user = username
        self._zerochan_pass = password

        import requests
        self.req_session = requests.Session()
        adapter = HTTPAdapter(max_retries=3)
        self.req_session.mount("https://", adapter)
        self.req_session.verify = False
        self.req_session.headers.update({
            "User-Agent": self.ua,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.zerochan.net/"
        })
        if self.net_config.get("use_proxy"):
            p = self.net_config.get("proxy_url")
            self.req_session.proxies = {"http": p, "https": p}

        try:
            import browser_cookie3
            self.req_session.cookies.update(browser_cookie3.chrome(domain_name="zerochan.net"))
            self.log("Loaded Zerochan cookies from Chrome.")
        except Exception as e:
            self.log(f"⚠️ No Chrome cookies ({e}) — falling back to credentials only.")

        self.log(f"Configured: tag='{self.original_tag}' encoded='{self.encoded_tag}' "
                 f"amount={amount} UA='{self.ua}'")

    def _gallery_dl_enumerate(self, tag):
        """Enumerate all post IDs for a tag via gallery-dl (primary source)."""
        username = self._zerochan_user
        password = self._zerochan_pass
        cmd = ["gallery-dl", "--cookies-from-browser", "chrome"]

        if username and password:
            cmd.extend(["-u", username, "-p", password])
            self.log("Using Zerochan credentials for gallery-dl.")
        else:
            self.log("For more access, please set your Zerochan Login in the Settings tab.")

        if self.net_config.get("use_proxy"):
            cmd.extend(["--proxy", self.net_config["proxy_url"]])
            
        # ponytail: no --range, no early stop — enumerate ALL posts so the
        # worker loop can skip past duplicates until amount is reached
        cmd.extend(["-g", f"https://www.zerochan.net/{tag}"])
        self.log(f"Running gallery-dl enumeration for '{tag}'...")
        import threading
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            watchdog = threading.Timer(600, proc.kill)
            watchdog.start()
            post_ids, seen = [], set()
            for line in proc.stdout:
                line = line.strip()
                if line.startswith('https://static.zerochan.net/.full.'):
                    parts = line.split('.full.')
                    if len(parts) > 1:
                        pid_str = parts[-1].split('.')[0]
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid not in seen:
                                seen.add(pid)
                                post_ids.append(pid)
            watchdog.cancel()
            proc.communicate()
            self.log(f"gallery-dl found {len(post_ids)} posts for '{tag}'")
            return post_ids
        except FileNotFoundError:
            self.log("gallery-dl not installed")
            return []
        except Exception as e:
            err = ""
            try: err = (proc.stderr.read() or "").strip()
            except Exception: pass
            self.log(f"gallery-dl failed for '{tag}': {e} {err[:200]}")
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
                    self.req_session.get,
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

        actual = collected_count + (self.download_queue.qsize() if self.download_queue else 0)
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
