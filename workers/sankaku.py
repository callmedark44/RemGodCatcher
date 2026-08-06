"""Sankaku worker — async BaseDownloader subclass."""
import os, re, random
import asyncio
from shared import BaseDownloader

API_BASE = "https://sankakuapi.com"

class SankakuWorker(BaseDownloader):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("sankaku", "Sankaku", amount, net_config)
        self.original_tag = tag.strip().lower()
        self.tag_with_rating = f"{self.original_tag} {rating}".strip() if rating else self.original_tag
        self.exclusions = exclusions
        self.rating = rating

        self._login()

        clean_tag = " ".join(t for t in self.original_tag.split() if not t.startswith('-'))
        self.safe_tag = re.sub(r'[\\/*?"<>|]', "", clean_tag)
        self.tag_dir = os.path.join(self.site_root, self.safe_tag)
        os.makedirs(self.tag_dir, exist_ok=True)

        self.rating_map = {"s": "Safe", "q": "Questionable", "e": "NSFW"}

    def _login(self):
        access_token = self.net_config.get("access_token") or os.getenv("SANKA_ACCESS_TOKEN")
        sanka_login = self.net_config.get("login") or os.getenv("SANKA_LOGIN")
        sanka_password = self.net_config.get("password") or os.getenv("SANKA_PASSWORD")

        if not access_token and sanka_login and sanka_password:
            for login_url in (f"{API_BASE}/auth/token", "https://login.sankakucomplex.com/auth/token"):
                try:
                    r = self.session.post(login_url,
                        json={"login": sanka_login, "password": sanka_password}, timeout=15)
                    if r.ok:
                        data = r.json()
                        access_token = data.get("token") or data.get("access_token") or ""
                        if access_token:
                            self.log("Logged in via credentials")
                            break
                        self.log("Login response missing token")
                    else:
                        self.log(f"Login at {login_url.split('/')[2]}: {r.status_code}")
                except Exception as e:
                    self.log(f"Login error at {login_url.split('/')[2]}: {e}")

        if access_token:
            self.session.headers["Authorization"] = f"Bearer {access_token}"
            self.log("Auth token loaded")

    def _setup_session(self):
        s = super()._setup_session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        return s

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.original_tag}'")
        collected_count = 0
        page = 1

        while not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
            try:
                limit_val = min(40, self.amount - collected_count if self.amount > 0 else 40)
                tag_list = [t.strip() for t in self.original_tag.split() if t.strip() and not t.startswith('-')]

                params = {"limit": limit_val, "page": page}
                if self.net_config.get("hide_pools", False):
                    params["hide_posts_in_books"] = "always"
                if self.rating:
                    rc = self.rating.split(":")[-1]
                    tag_list.append(f"rating:{rc}")

                if "-video" in self.exclusions and "-image" not in self.exclusions:
                    tag_list.append("file_type:image")
                elif "-image" in self.exclusions and "-video" not in self.exclusions:
                    tag_list.append("file_type:video")

                if tag_list:
                    params["tags"] = " ".join(tag_list)

                self.log(f"Scanning API... (Page {page})")
                resp = await asyncio.to_thread(self.session.get, f"{API_BASE}/posts", params=params, timeout=15)
                if resp.status_code in (403, 429):
                    self.log(f"API error: {resp.status_code}. Check proxy/credentials.")
                    break
                resp.raise_for_status()

                data = resp.json()
                posts = []
                if isinstance(data, dict):
                    if page == 1:
                        self.log(f"Response keys: {list(data.keys())}")
                    posts = data.get("data") or data.get("posts") or []
                elif isinstance(data, list):
                    posts = data

                if not posts:
                    if page == 1:
                        self.log(f"ZERO images for '{self.original_tag}'.")
                    break

            except Exception as e:
                self.log(f"API Error: {e}")
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(0.25)

            for post in posts:
                if self.stop_event.is_set() or (self.amount > 0 and collected_count >= self.amount):
                    break
                if not isinstance(post, dict):
                    continue

                post_rating = post.get("rating", "")
                if self.rating:
                    filter_rating = self.rating.split(":")[-1]
                    if post_rating != filter_rating:
                        continue

                url = post.get("file_url")
                if not url:
                    continue

                ext = (post.get("file_ext") or "").lower()
                if ext not in ("jpg", "jpeg", "png", "gif", "webp", "mp4", "webm"):
                    continue
                if ext in ("mp4", "webm") and "-video" in self.exclusions: continue
                if ext in ("jpg", "jpeg", "png", "webp") and "-image" in self.exclusions: continue
                if ext == "gif" and "-gif" in self.exclusions: continue

                filename = f"{post.get('id')}.{ext}"
                rating_label = self.rating_map.get(post_rating, "Unknown")
                subfolder = "books" if post.get("in_visible_pool") else "images"
                filepath = os.path.join(self.tag_dir, rating_label, subfolder, filename)

                raw_tags = post.get("tags", [])
                if raw_tags and isinstance(raw_tags[0], dict):
                    tags_list = [t.get("name", "") for t in raw_tags if t.get("name")]
                    artists = [t.get("name") for t in raw_tags if isinstance(t, dict) and t.get("type") == 1]
                else:
                    tags_list = post.get("tag_names", [])
                    artists = []

                if await self.enqueue_download(url, filepath, filename, tags_list, artists):
                    collected_count += 1

            page += 1
            if not self.stop_event.is_set() and (self.amount == 0 or collected_count < self.amount):
                await asyncio.sleep(0.5)

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")

def worker_sankaku(tag, amount, rating, exclusions, net_config):
    SankakuWorker(tag, amount, rating, exclusions, net_config).run()