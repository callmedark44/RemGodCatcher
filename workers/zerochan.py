import os, re, urllib.parse, subprocess
import asyncio
from html.parser import HTMLParser
from requests.adapters import HTTPAdapter
from shared import BaseDownloader

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class _ZerochanTagParser(HTMLParser):
    """Parse categorized tags from Zerochan post HTML."""

    def __init__(self):
        super().__init__()
        self.tags = []
        self._in_tag_list = False
        self._current_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "ul" and attrs_dict.get("id") == "tags":
            self._in_tag_list = True
            return

        if self._in_tag_list and tag == "li":
            classes = attrs_dict.get("class", "").split()
            data_tag = attrs_dict.get("data-tag", "")

            if data_tag and classes:
                category = classes[0]
                primary = "primary" in classes
                favorite = "fav" in classes
                self._current_tag = {
                    "tag": data_tag,
                    "category": category,
                    "primary": primary,
                    "favorite": favorite,
                }

    def handle_endtag(self, tag):
        if tag == "ul" and self._in_tag_list:
            self._in_tag_list = False
        if tag == "li" and self._current_tag is not None:
            self.tags.append(self._current_tag)
            self._current_tag = None


def parse_zerochan_tags(html):
    """Extract categorized tags from raw Zerochan post HTML.

    Returns a list of dicts:
        [{"tag": "Mavuika", "category": "character", "primary": True, "favorite": False}, ...]

    The category comes from the actual CSS class on the <li>, so new
    categories added by Zerochan are handled automatically.
    """
    parser = _ZerochanTagParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.tags


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

    def _gallery_dl_enumerate(self, tag, page=1):
        """Fetch one page of posts via gallery-dl."""
        import json as _json
        import threading
        import shutil

        username = self._zerochan_user
        password = self._zerochan_pass

        gallery_dl_path = shutil.which("gallery-dl")
        if not gallery_dl_path:
            for p in ["/home/hanekawa/.local/bin/gallery-dl", "/usr/local/bin/gallery-dl", "/usr/bin/gallery-dl"]:
                import os
                if os.path.isfile(p):
                    gallery_dl_path = p
                    break
        if not gallery_dl_path:
            self.log("ERROR: gallery-dl not found. Install it: pip install gallery-dl")
            return []

        base_cmd = [gallery_dl_path, "--cookies-from-browser", "chrome"]

        if username and password:
            base_cmd.extend(["-u", username, "-p", password])
        else:
            self.log("For more access, please set your Zerochan Login in the Settings tab.")

        if self.net_config.get("use_proxy"):
            base_cmd.extend(["--proxy", self.net_config["proxy_url"]])

        base_cmd.extend([
            "-j",
            "-o", "extractor.zerochan.metadata=true",
            "-o", "extractor.zerochan.page-html=true",
        ])

        PAGE_SIZE = 2
        start = (page - 1) * PAGE_SIZE + 1
        end = page * PAGE_SIZE

        cmd = base_cmd + [
            "--range", f"{start}-{end}",
            f"https://www.zerochan.net/{tag}",
        ]

        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            watchdog = threading.Timer(600, proc.kill)
            watchdog.start()
            stdout, _ = proc.communicate(timeout=580)
            watchdog.cancel()

            data = _json.loads(stdout)

            posts = []
            seen = set()
            for msg in data:
                if not isinstance(msg, list) or len(msg) < 2:
                    continue
                msg_type = msg[0]
                if msg_type == 3 and len(msg) >= 3:
                    kwdict = msg[2] if isinstance(msg[2], dict) else {}
                elif msg_type == 2 and isinstance(msg[1], dict):
                    kwdict = msg[1]
                else:
                    continue
                pid = kwdict.get("id")
                if pid is None or pid in seen:
                    continue
                seen.add(pid)
                posts.append(kwdict)

            self.log(f"Page {page}: {len(posts)} posts")
            return posts

        except Exception as e:
            if proc and proc.poll() is None:
                proc.kill()
            self.log(f"gallery-dl page {page} failed: {e}")
            return []

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")
        collected_count = 0
        page = 1
        MAX_PAGES = 50

        while page <= MAX_PAGES:
            if self.stop_event.is_set():
                break
            if self.amount > 0 and collected_count >= self.amount:
                break

            posts = await asyncio.to_thread(self._gallery_dl_enumerate, self.encoded_tag, page)
            if not posts:
                self.log("No more posts available from gallery-dl.")
                break

            enqueued_this_page = 0
            for post in posts:
                if self.stop_event.is_set():
                    break
                if self.amount > 0 and collected_count >= self.amount:
                    break

                try:
                    pid = post.get("id")
                    img_url = post.get("file_url")

                    if not img_url:
                        img_url = _derive_img_url(post)
                    if not img_url:
                        self.log(f"No image URL found for post {pid}, skipping.")
                        continue

                    page_html = post.get("page_html", "")
                    if page_html:
                        categorized = parse_zerochan_tags(page_html)
                        artists = [t["tag"] for t in categorized if t["category"] in ("mangaka",)]
                        characters = [t["tag"] for t in categorized if t["category"] in ("character",)]
                        copyrights = [t["tag"] for t in categorized if t["category"] in ("game",)]
                        metadata_tags = [t["tag"] for t in categorized if t["category"] in ("meta",)]
                        tags_list = [t["tag"] for t in categorized if t["category"] in ("theme", "source", "vtuber", "outfit", "series", "group", "studio")]
                    else:
                        tags_raw = post.get("tags", [])
                        artists = []
                        characters = []
                        copyrights = []
                        metadata_tags = []
                        if isinstance(tags_raw, str):
                            tags_list = [t.strip() for t in tags_raw.replace(",", " ").split() if t.strip()]
                        else:
                            tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]

                    filename = urllib.parse.unquote(img_url.split('/')[-1])
                    filepath = os.path.join(self.tag_dir, filename)

                    if await self.enqueue_download(img_url, filepath, filename, tags_list, artists=artists, characters=characters, copyrights=copyrights, metadata_tags=metadata_tags):
                        collected_count += 1
                        enqueued_this_page += 1
                        self.log(f"Enqueued {filename} ({collected_count}/{self.amount})")
                    await asyncio.sleep(self.anti_ban_pause)

                except Exception as e:
                    self.log(f"Error processing post {post.get('id', '?')}: {e}")
                    continue

            self.log(f"Page {page}: enqueued {enqueued_this_page} new images (total: {collected_count})")
            page += 1

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
