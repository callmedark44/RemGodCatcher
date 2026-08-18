"""Anime-Pictures.net worker — async BaseDownloader subclass.

Cookie bypass detail
────────────────────
The origin server at api.anime-pictures.net/pictures/download_image/
rejects requests (403) unless two cookies are present:
  time_zone=<browser timezone>  e.g. Asia/Tehran, UTC
  sitelang=<site language>      e.g. en
"""
import os, re
import asyncio
from curl_cffi import requests as curl_requests
import shared
from shared import BaseDownloader

API = "https://api.anime-pictures.net/api/v3"
PER_PAGE = 80


class AnimeDlWorker(BaseDownloader):
    def __init__(self, tag, amount, net_config):
        super().__init__("anime_dl", "AnimePictures", amount, net_config)
        self.tag = tag.strip().lower()
        self.tag_slug = self.tag.replace(" ", "_")
        self.tag_dir = os.path.join(self.site_root, self.tag_slug)
        os.makedirs(self.tag_dir, exist_ok=True)

        # override session with curl_cffi for TLS impersonation
        self.session = self._make_session()

    def _make_session(self):
        s = curl_requests.Session()
        s.impersonate = "chrome131"
        if self.net_config.get("use_proxy"):
            p = self.net_config.get("proxy_url", "")
            s.proxies = {"http": p, "https": p}
        else:
            # libcurl reads http_proxy/https_proxy env vars; empty string disables
            s.proxies = {"http": "", "https": ""}
        s.cookies.set("time_zone", "UTC", domain=".anime-pictures.net")
        s.cookies.set("sitelang", "en", domain=".anime-pictures.net")
        return s

    async def _search_posts(self, page=0):
        params = {"page": page, "limit": PER_PAGE, "search_tag": self.tag, "lang": "en"}
        r = await asyncio.to_thread(self.session.get, f"{API}/posts", params=params, timeout=30)
        if r.status_code != 200:
            return None, 0
        data = r.json()
        return data.get("posts", []), data.get("posts_count", 0)

    async def _get_post_detail(self, post_id):
        r = await asyncio.to_thread(self.session.get, f"{API}/posts/{post_id}", params={"lang": "en"}, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()

    async def _download_one(self, post_id):
        detail = await self._get_post_detail(post_id)
        if not detail:
            return
        file_url = detail.get("file_url", "")
        if not file_url:
            return

        dl_url = f"https://api.anime-pictures.net/pictures/download_image/{file_url}"
        r = await asyncio.to_thread(self.session.get, dl_url, timeout=120, headers={
            "Referer": f"https://anime-pictures.net/posts/{post_id}?lang=en",
        })
        if r.status_code != 200 or len(r.content) <= 1000:
            return

        ext = file_url.rsplit(".", 1)[-1]
        filename = f"{self.tag_slug}_{post_id}.{ext}"
        fpath = os.path.join(self.tag_dir, filename)
        with open(fpath, "wb") as f:
            f.write(r.content)

        rel = os.path.relpath(fpath, shared.MASTER_FOLDER)
        from shared import add_to_gallery, send_tags
        add_to_gallery(self.name, filename, rel, [self.tag], [])
        send_tags(self.name, filename, [self.tag])
        self.log(f"[SUCCESS] Downloaded {filename}")

    async def scraper_task(self):
        self.log(f"Initializing worker for tag: '{self.tag}'")

        post_ids = []
        page = 0
        while not self.stop_event.is_set() and (self.amount == 0 or len(post_ids) < self.amount):
            posts, total = await self._search_posts(page)
            if not posts:
                break
            page += 1
            for p in posts:
                if p["id"] not in post_ids:
                    post_ids.append(p["id"])
            if page * PER_PAGE >= total:
                break

        if self.amount > 0:
            post_ids = post_ids[:self.amount]
        if not post_ids:
            self.log("No posts found.")
            return

        self.log(f"Found {len(post_ids)} posts, downloading...")
        for pid in post_ids:
            if self.stop_event.is_set():
                break
            await self._download_one(pid)

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")


def worker_anime_dl(tag, amount, net_config):
    AnimeDlWorker(tag, amount, net_config).run()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Download full-res images from anime-pictures.net by tag")
    parser.add_argument("tag", help="Tag to search for")
    parser.add_argument("count", type=int, nargs="?", default=10)
    parser.add_argument("--output", "-o", default="downloads")
    args = parser.parse_args()
    import sys
    net_config = {}
    worker = AnimeDlWorker(args.tag, args.count, net_config)
    worker.tag_dir = os.path.join(args.output, worker.tag_slug)
    os.makedirs(worker.tag_dir, exist_ok=True)
    from shared import MASTER_FOLDER
    worker.site_root = args.output
    asyncio.run(worker.run_async_loop(worker.scraper_task))

if __name__ == "__main__":
    main()
