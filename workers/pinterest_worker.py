"""Pinterest worker — async BaseDownloader subclass."""
import os, re, json, threading, random
import asyncio
from pathlib import Path
from shared import BaseDownloader


class PinterestWorker(BaseDownloader):
    def __init__(self, url_or_query, amount, is_search, net_config, min_w=0, min_h=0):
        super().__init__("pinterest", "Pinterest", amount, net_config)
        self.query = url_or_query
        self.is_search = is_search
        self.min_w = min_w
        self.min_h = min_h

        safe_name = re.sub(r'[\\/*?:"<>|]', "_",
            (url_or_query.strip().lower().replace("https://", "").replace("http://", "").replace("/", "_")[:60]))
        self.tag_dir = os.path.join(self.site_root, safe_name)
        os.makedirs(self.tag_dir, exist_ok=True)

        self.cookies_path = net_config.get("pinterest_cookies", "") or os.path.join(self.tag_dir, "pinterest_cookies.json")
        self.email = net_config.get("pinterest_email", "")
        self.password = net_config.get("pinterest_password", "")
        self.proxy_url = net_config.get("proxy_url", "")

        # override session for async compat
        self.session = None
        self._client = None

    def _apply_proxy(self, session):
        if self.net_config.get("use_proxy"):
            session.proxies = {"http": self.proxy_url, "https": self.proxy_url}
        else:
            session.proxies = {"http": "", "https": "", "no_proxy": "*"}

    def _make_api_client(self):
        from pinterest_dl import PinterestDL
        client = PinterestDL.with_api(timeout=5, verbose=False, ensure_alt=True)
        # ponytail: _apply_proxy covers client._session only; pinterest_dl's
        # internal _get_default_cookies/_resolve_short_url use bare requests.get
        # and bypass it. Upgrade: patch pinterest_dl to pass proxies/session in.
        self._apply_proxy(client._session)
        return client

    def _browser_login(self):
        from playwright.sync_api import BrowserType
        from pinterest_dl import PinterestDL as PDL

        orig = BrowserType.launch
        def patched_launch(self, **kw):
            if self.net_config.get("use_proxy") and self.proxy_url:
                kw["proxy"] = {"server": self.proxy_url}
            return orig(self, **kw)
        BrowserType.launch = patched_launch

        scraper = PDL.with_browser(browser_type="chromium", headless=True, verbose=False)
        driver = scraper.login(self.email, self.password)
        cookies = driver.get_cookies(after_sec=7)
        scraper.close()
        self._client.with_cookies(cookies)
        if self.cookies_path and cookies:
            os.makedirs(os.path.dirname(self.cookies_path) or ".", exist_ok=True)
            with open(self.cookies_path, "w") as f:
                json.dump(cookies, f, indent=2)
        self.log("Logged in via browser with fresh cookies")
        return True

    def _run_search(self, collected, seen_ids, lock):
        existing = len([f for f in os.listdir(self.tag_dir) if re.match(r'^\d+\.[a-z]+$', f)])
        fetch_num = self.amount + existing

        def on_progress(media):
            with lock:
                if len(collected) >= self.amount:
                    return
                if media.id in seen_ids:
                    return
                ext = Path(media.src).suffix.lower() if media.src else ".jpg"
                if os.path.exists(os.path.join(self.tag_dir, f"{media.id}{ext}")):
                    return
                seen_ids.add(media.id)
                collected.append(media)

        try:
            if self.is_search:
                self._client.search(query=self.query, num=fetch_num,
                    min_resolution=(self.min_w, self.min_h), on_progress=on_progress)
            else:
                self._client.scrape(url=self.query, num=fetch_num,
                    min_resolution=(self.min_w, self.min_h), on_progress=on_progress)
        except Exception as e:
            self.log(f"Scrape error: {e}")

    async def scraper_task(self):
        self.log(f"Initializing Pinterest worker: '{self.query[:80]}'")

        from pinterest_dl.download import MediaDownloader

        self._client = self._make_api_client()
        have_auth = False

        if os.path.exists(self.cookies_path):
            try:
                self._client.with_cookies_path(self.cookies_path)
                self.log("Loaded Pinterest cookies")
                have_auth = True
            except Exception as e:
                self.log(f"Cookie load error: {e}")

        collected = []
        seen_ids = set()
        lock = threading.Lock()

        await asyncio.to_thread(self._run_search, collected, seen_ids, lock)

        if not collected and have_auth and self.email and self.password:
            self.log("Cookies expired, refreshing via browser login...")
            try: os.remove(self.cookies_path)
            except Exception: pass
            self._client = self._make_api_client()
            try:
                await asyncio.to_thread(self._browser_login)
                collected.clear(); seen_ids.clear()
                await asyncio.to_thread(self._run_search, collected, seen_ids, lock)
            except ImportError:
                self.log("Browser auth unavailable (install pinterest-dl[browser] and playwright)")
            except Exception as e:
                self.log(f"Browser login failed: {e}")
        elif not have_auth and self.email and self.password:
            self.log("No cookies, logging in via browser...")
            try:
                await asyncio.to_thread(self._browser_login)
                collected.clear(); seen_ids.clear()
                await asyncio.to_thread(self._run_search, collected, seen_ids, lock)
            except ImportError:
                self.log("Browser auth unavailable")
            except Exception as e:
                self.log(f"Browser login failed: {e}")

        if not collected:
            self.log("No new media found.")
            return

        medias = collected[:self.amount]
        self.log(f"Collected {len(medias)} items, downloading...")

        from shared import socketio_emit, add_to_gallery, send_tags

        dl_retries = int(self.net_config.get("download_retries", 3))
        downloader = MediaDownloader(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            timeout=int(self.net_config.get("api_timeout", 10)),
            max_retries=dl_retries)
        self._apply_proxy(downloader.http_client.session)

        downloaded = 0
        for i, media in enumerate(medias):
            if self.stop_event.is_set():
                break
            try:
                path = downloader.download(media, Path(self.tag_dir), download_streams=True)
                filename = os.path.basename(path)
                rel = os.path.relpath(str(path), shared.MASTER_FOLDER)
                tags = [media.alt] if media.alt else []
                add_to_gallery(self.name, filename, rel, tags, [])
                send_tags(self.name, filename, tags)
                downloaded += 1
                socketio_emit("pinterest_progress", {"index": downloaded, "total": self.amount})
                self.log(f"[SUCCESS] Downloaded {filename} ({downloaded}/{self.amount})")
            except Exception as e:
                self.log(f"[FAILED] {media.id}: {e}")
            await asyncio.sleep(random.uniform(0.5, 1.5))

        self.log(f"Downloaded {downloaded} items.")

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")


def worker_pinterest(url_or_query, amount, is_search, net_config, min_w=0, min_h=0):
    PinterestWorker(url_or_query, amount, is_search, net_config, min_w, min_h).run()