"""Nekos API v5 image worker."""

import asyncio
import os
import re
from urllib.parse import urlparse

from shared import BaseDownloader


class NekosApiWorker(BaseDownloader):
    API_BASE = "https://api.nekosapi.com/v5"
    VALID_RATINGS = {"safe", "suggestive", "borderline", "explicit"}
    MAX_FILTERS = 5

    def __init__(self, tags, artists, amount, rating, net_config):
        self.tags = self._parse_filters(tags, "tags")
        self.artists = self._parse_filters(artists, "artists")
        self.rating = str(rating or "safe").strip().lower()
        if self.rating not in self.VALID_RATINGS:
            raise ValueError(f"Unsupported Nekos API rating: {self.rating}")

        label = self.tags[0] if self.tags else self.artists[0] if self.artists else "all"
        folder = re.sub(r"[^\w.-]+", "_", label, flags=re.UNICODE).strip("._") or "all"
        super().__init__("nekosapi", os.path.join("NekosAPI", self.rating, folder), amount, net_config)

    @classmethod
    def _parse_filters(cls, values, label):
        if isinstance(values, str):
            values = re.split(r"[,\n]", values)
        values = values or []
        cleaned = []
        seen = set()
        for value in values:
            value = str(value).strip()
            key = value.casefold()
            if value and key not in seen:
                cleaned.append(value)
                seen.add(key)
        if len(cleaned) > cls.MAX_FILTERS:
            raise ValueError(f"Nekos API accepts at most {cls.MAX_FILTERS} {label}.")
        return cleaned

    async def _request_page(self, params):
        retries = max(1, int(self.net_config.get("api_retries", 3)))
        timeout = max(1, int(self.net_config.get("api_timeout", 15)))
        retry_wait = max(0, float(self.net_config.get("retry_wait", 3)))

        for attempt in range(retries):
            try:
                response = await asyncio.to_thread(
                    self.session.get,
                    f"{self.API_BASE}/images",
                    params=params,
                    timeout=timeout,
                )
                if response.status_code == 429:
                    wait = min(60, float(response.headers.get("Retry-After", retry_wait)))
                    if attempt + 1 < retries:
                        self.log(f"Rate limited by Nekos API; retrying in {wait:g}s...")
                        await asyncio.sleep(wait)
                        continue
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "json" not in content_type:
                    raise ValueError(f"Nekos API returned non-JSON content ({content_type or 'unknown'}).")
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise ValueError("Nekos API returned an unexpected response shape.")
                return payload
            except Exception as exc:
                if attempt + 1 >= retries:
                    raise RuntimeError(f"Nekos API request failed after {retries} attempts: {exc}") from exc
                await asyncio.sleep(retry_wait)
        return {"items": []}

    async def scraper(self):
        offset = 0
        collected = 0
        unlimited_page_cap = 200

        while not self.stop_event.is_set() and (self.amount == 0 or collected < self.amount):
            remaining = self.amount - collected if self.amount else 100
            page_limit = min(100, max(1, remaining))
            params = [("limit", page_limit), ("offset", offset), ("rating", self.rating)]
            params.extend(("tag", tag) for tag in self.tags)
            params.extend(("artist", artist) for artist in self.artists)

            payload = await self._request_page(params)
            items = payload["items"]
            if not items:
                break

            for item in items:
                if self.stop_event.is_set() or (self.amount and collected >= self.amount):
                    break
                url = item.get("url")
                image_id = item.get("id")
                if not url or image_id is None:
                    continue
                ext = os.path.splitext(urlparse(url).path)[1].lower().lstrip(".") or "jpg"
                if ext not in self.IMAGE_EXTENSIONS:
                    ext = "jpg"
                filename = f"nekosapi_{image_id}.{ext}"
                filepath = os.path.join(self.site_root, filename)
                tag_names = [
                    tag.get("name", "").strip()
                    for tag in item.get("tags", [])
                    if isinstance(tag, dict) and tag.get("name")
                ]
                item_rating = str(item.get("rating") or self.rating)
                if item_rating:
                    tag_names.append(f"rating:{item_rating}")
                artists = [str(item["artist_name"]).strip()] if item.get("artist_name") else []
                if await self.enqueue_download(url, filepath, filename, tag_names, artists):
                    collected += 1

            offset += len(items)
            total = payload.get("total")
            if len(items) < page_limit or (isinstance(total, int) and offset >= total):
                break
            if self.amount == 0 and offset >= unlimited_page_cap:
                self.log("Unlimited mode page cap reached; start again to continue.")
                break
            if self.anti_ban_pause:
                await asyncio.sleep(self.anti_ban_pause)

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper))


def worker_nekosapi(tags, artists, amount, rating, net_config):
    NekosApiWorker(tags, artists, amount, rating, net_config).run()
