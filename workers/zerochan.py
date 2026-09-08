import os, re, time, urllib.parse, subprocess
import asyncio
from html.parser import HTMLParser
from requests.adapters import HTTPAdapter
from core.shared import BaseDownloader

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class _ZerochanTagParser(HTMLParser):
    """Parse categorized tags from Zerochan post HTML."""

    def __init__(self):
        super().__init__()
        self.tags = []
        self._in_tag_list = False
        self._current_tag = None
        self._icon_class = ""

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
                self._icon_class = ""

        # ponytail: the <s> icon class holds the TRUE sub-category
        # (li="theme" + s="outfit" for garments, s="hair"/"eyes"/"group"...)
        if self._in_tag_list and tag == "s" and self._current_tag is not None:
            specific = [c for c in attrs_dict.get("class", "").split()
                        if c != "medium"]
            if specific:
                self._icon_class = specific[0]

    def handle_endtag(self, tag):
        if tag == "ul" and self._in_tag_list:
            self._in_tag_list = False
        if tag == "li" and self._current_tag is not None:
            if self._icon_class:
                self._current_tag["category"] = self._icon_class
            self.tags.append(self._current_tag)
            self._current_tag = None
            self._icon_class = ""


class _ZerochanSubtagParser(HTMLParser):
    """Parse sub-tag browser boxes from a Zerochan tag page.

    Targets ``<section class="carousel thumbs"><ul><li>`` entries:
        <li><a href="/Reze+%28Default+Outfit%29" title="235 entries">
        <div class="thumb" data-src="..."></div>
        <p class="outfit">Default Outfit</p></a><i>235</i></li>
    """

    def __init__(self):
        super().__init__()
        self.subtags = []
        self._in_carousel = False
        self._current = None
        self._in_name = False
        self._in_count = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "section" and "carousel" in attrs_dict.get("class", "").split():
            self._in_carousel = True
            return
        if not self._in_carousel:
            return
        if tag == "li":
            self._current = {"name": "", "short": "", "url": "",
                             "count": 0, "thumb": "", "kind": ""}
        elif tag == "a" and self._current is not None and not self._current["url"]:
            href = attrs_dict.get("href", "")
            if href.startswith("/"):
                self._current["url"] = "https://www.zerochan.net" + href
                self._current["name"] = urllib.parse.unquote_plus(
                    href.rsplit("/", 1)[-1])
            title = attrs_dict.get("title", "")
            m = re.search(r"(\d+)", title)
            if m:
                self._current["count"] = int(m.group(1))
        elif tag == "div" and self._current is not None:
            if "thumb" in attrs_dict.get("class", "").split():
                self._current["thumb"] = attrs_dict.get("data-src", "")
        elif tag == "p" and self._current is not None:
            self._current["kind"] = attrs_dict.get("class", "")
            self._in_name = True
        elif tag == "i" and self._current is not None:
            self._in_count = True

    def handle_data(self, data):
        if self._current is None:
            return
        if self._in_name:
            self._current["short"] += data.strip()
        elif self._in_count:
            m = re.search(r"(\d+)", data)
            if m:
                self._current["count"] = int(m.group(1))

    def handle_endtag(self, tag):
        if tag == "section" and self._in_carousel:
            self._in_carousel = False
        if not self._in_carousel and tag != "li":
            self._in_name = self._in_count = False
            return
        if tag == "p":
            self._in_name = False
        elif tag == "i":
            self._in_count = False
        elif tag == "li" and self._current is not None:
            if self._current["url"]:
                self.subtags.append(self._current)
            self._current = None
            self._in_name = self._in_count = False


def parse_zerochan_subtags(html):
    """Extract sub-tag boxes from raw Zerochan tag-page HTML.

    Returns a list of dicts:
        [{"name": "Reze (Default Outfit)", "short": "Default Outfit",
          "url": "https://www.zerochan.net/Reze+%28Default+Outfit%29",
          "count": 235, "thumb": "https://...", "kind": "outfit"}, ...]
    """
    parser = _ZerochanSubtagParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.subtags


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


# Windows forbids these chars (plus control chars) in file/dir names.
# NOTE: ':' must be included — Zerochan tags/filenames contain it
# (e.g. "Rem (Re:Zero)") and it crashes makedirs/replace with WinError 267/87.
_UNSAFE_PATH_CHARS_RE = re.compile('[<>:"/\\\\|?*\\x00-\\x1f]')


def _sanitize_path_part(name, fallback="misc"):
    """Make a tag/filename safe for Windows + POSIX filesystems."""
    try:
        cleaned = _UNSAFE_PATH_CHARS_RE.sub("", str(name or ""))
        # Windows also dislikes trailing dots/spaces
        cleaned = cleaned.strip().rstrip(". ")
        return cleaned or fallback
    except Exception:
        return fallback


def _split_category_tags(raw_tags):
    """Split ['Category:Name', ...] into (general, artists, chars, copyrights, meta)."""
    general, artists, characters, copyrights, metadata_tags = [], [], [], [], []
    for entry in raw_tags or []:
        try:
            text = str(entry).strip()
            if not text:
                continue
            if ":" not in text:
                general.append(text)
                continue
            cat, _, name = text.partition(":")
            name = name.strip()
            if not name:
                continue
            c = cat.strip().lower()
            if c in ("mangaka", "artist"):
                artists.append(name)
            elif c in ("character",):
                characters.append(name)
            elif c in ("game", "series", "copyright"):
                copyrights.append(name)
            elif c in ("meta", "metadata"):
                metadata_tags.append(name)
            else:
                general.append(name)
        except Exception:
            continue
    return general, artists, characters, copyrights, metadata_tags


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
        self.safe_tag = _sanitize_path_part(re.sub(r'[\\/*?"<>|]', "", clean_tag), fallback="")
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

        self._cookies_loaded = False

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
            for p in [os.path.expanduser("~/.local/bin/gallery-dl"), "/usr/local/bin/gallery-dl", "/usr/bin/gallery-dl"]:
                if os.path.isfile(p):
                    gallery_dl_path = p
                    break
        if not gallery_dl_path:
            self.log("ERROR: gallery-dl not found. Install it: pip install gallery-dl")
            return []

        base_cmd = [gallery_dl_path]
        # ponytail: reading the browser cookie store costs seconds per
        # spawn, and the export stays valid for hours — reuse a fresh file.
        cookie_file = os.path.join(self.tag_dir, ".zerochan_cookies.txt")
        cookie_fresh = (
            os.path.exists(cookie_file)
            and (time.time() - os.path.getmtime(cookie_file) < 12 * 3600)
        )
        browser = next((b for b in ("chrome", "chromium", "edge", "firefox") if shutil.which(b)), None)
        if cookie_fresh:
            base_cmd.extend(["--cookies", cookie_file])
        elif browser:
            base_cmd.extend(["--cookies-from-browser", browser, "--cookies-export", cookie_file])
        else:
            self.log("No supported browser found for cookies — continuing anonymously (safe content only).")

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

        PAGE_SIZE = 20
        FIRST_PAGE_SIZE = 6
        if page == 1:
            # ponytail: small first page — first image in ~10s, not ~1min
            start, end = 1, FIRST_PAGE_SIZE
        else:
            start = FIRST_PAGE_SIZE + (page - 2) * PAGE_SIZE + 1
            end = start + PAGE_SIZE - 1

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

    def _fetch_subtags(self):
        """Download the tag page and return its sub-tag boxes."""
        if not self._cookies_loaded:
            self._cookies_loaded = True
            try:
                import browser_cookie3
                self.req_session.cookies.update(browser_cookie3.chrome(domain_name="zerochan.net"))
                self.log("Loaded Zerochan cookies from Chrome.")
            except Exception as e:
                self.log(f"⚠️ No Chrome cookies ({e}) — falling back to credentials only.")
        resp = self.req_session.get(f"https://www.zerochan.net/{self.encoded_tag}",
                                    timeout=30)
        resp.raise_for_status()
        self.subtags = parse_zerochan_subtags(resp.text)
        return self.subtags

    async def _log_subtags(self):
        # ponytail: runs beside page 1, never ahead of it — first image first
        try:
            subtags = await asyncio.to_thread(self._fetch_subtags)
            for s in subtags:
                self.log(f"🔖 Sub-tag: '{s['name']}' — {s['count']} entries "
                         f"(search '{s['name']}' to download)")
        except Exception as e:
            self.log(f"Sub-tag listing skipped: {e}")

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")
        collected_count = 0
        page = 1
        MAX_PAGES = 50

        asyncio.create_task(self._log_subtags())

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
                        outfits = [t["tag"] for t in categorized if t["category"] in ("outfit",)]
                        groups = [t["tag"] for t in categorized if t["category"] in ("group",)]
                        hair = [t["tag"] for t in categorized if t["category"] in ("hair",)]
                        eyes = [t["tag"] for t in categorized if t["category"] in ("eyes",)]
                        tags_list = [t["tag"] for t in categorized if t["category"] in ("theme", "source", "vtuber", "series", "studio")]
                    else:
                        tags_raw = post.get("tags", [])
                        artists = []
                        characters = []
                        copyrights = []
                        metadata_tags = []
                        outfits = []
                        groups = []
                        hair = []
                        eyes = []
                        if isinstance(tags_raw, str):
                            tags_list = [t.strip() for t in tags_raw.replace(",", " ").split() if t.strip()]
                        elif isinstance(tags_raw, list) and any(":" in str(t) for t in tags_raw):
                            tags_list, artists, characters, copyrights, metadata_tags = \
                                _split_category_tags(tags_raw)
                        else:
                            tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]

                    filename = _sanitize_path_part(urllib.parse.unquote(img_url.split('/')[-1]),
                                                   fallback=f"zerochan_{pid}.jpg")
                    filepath = os.path.join(self.tag_dir, filename)

                    if await self.enqueue_download(img_url, filepath, filename, tags_list, artists=artists, characters=characters, copyrights=copyrights, metadata_tags=metadata_tags, outfits=outfits, groups=groups, hair=hair, eyes=eyes):
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
        if self.stop_event.is_set():
            self.log("--- Worker Terminated ---")


def worker_zerochan(tag, amount, net_config):
    worker = ZerochanWorker(tag, amount, net_config)
    worker.run()
