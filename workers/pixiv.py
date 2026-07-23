# -*- coding: utf-8 -*-

# Adapted from gallery-dl (https://github.com/mikf/gallery-dl)
# Original: gallery_dl/extractor/pixiv.py  |  gallery_dl/text.py
#           gallery_dl/extractor/common.py  |  gallery_dl/util.py
# Copyright 2014-2026 Mike Fährmann
#
# gallery-dl is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This file is part of RemGodCatcher, which incorporates GPL-2.0 licensed
# code from gallery-dl. See LICENSE for details.
#
# Modifications: adapted to BaseDownloader pattern, removed gallery-dl
# CLI/config/Job/postprocessor machinery, switched to shared get_session()
# proxy/TLS framework, added ugoira-to-GIF conversion via Pillow.

import os
import re
import io
import time
import hashlib
import zipfile
import json
import asyncio
from datetime import datetime
from urllib.parse import unquote
from PIL import Image
import requests

from shared import BaseDownloader, save_history, add_to_gallery, send_tags, MASTER_FOLDER, log_msg

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"
RATING_CODES = {0: "General", 1: "R18", 2: "R18G"}


class PixivAppAPI:
    """Minimal Pixiv App API (adapted from gallery-dl PixivAppAPI)."""

    def __init__(self, session, log_fn, refresh_token):
        self.session = session
        self.log = log_fn
        self.refresh_token = refresh_token
        self.user = None
        self._token = None
        self._token_expires = 0
        self.session.headers.update({
            "App-OS": "ios",
            "App-OS-Version": "16.7.2",
            "App-Version": "7.19.1",
            "User-Agent": "PixivIOSApp/7.19.1 (iOS 16.7.2; iPhone12,8)",
            "Referer": "https://app-api.pixiv.net/",
        })

    def login(self):
        now = time.time()
        if self._token and now < self._token_expires:
            return
        if not self.refresh_token:
            raise ValueError("PIXIV_REFRESH_TOKEN required in .env")

        self.log("Refreshing access token")
        url = "https://oauth.secure.pixiv.net/auth/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "get_secure_url": "1",
        }
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        headers = {
            "X-Client-Time": ts,
            "X-Client-Hash": hashlib.md5(
                (ts + HASH_SECRET).encode()).hexdigest(),
        }
        resp = self.session.post(url, data=data, headers=headers, timeout=30)
        if resp.status_code >= 400:
            self.log(f"Auth failed: {resp.text[:200]}")
            raise ValueError("Invalid refresh token")

        body = resp.json()["response"]
        self.user = body["user"]
        self._token = body["access_token"]
        self._token_expires = now + 3300
        self.session.headers["Authorization"] = f"Bearer {self._token}"
        self.log(f"Logged in as {self.user.get('name', '?')}")

    def _call(self, endpoint, params=None):
        url = "https://app-api.pixiv.net" + endpoint
        while True:
            self.login()
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code in (403, 429):
                self.log("Rate limited - waiting 300s")
                time.sleep(300)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" not in data:
                return data
            err = data["error"]
            msg = (
                err.get("user_message") or err.get("message") or str(err)
                if isinstance(err, dict) else str(err))
            if "rate limit" in msg.lower():
                self.log("Rate limited - waiting 300s")
                time.sleep(300)
                continue
            raise Exception(f"Pixiv API error: {msg}")

    def _paginate(self, endpoint, params, key="illusts", limit=0):
        items = []
        while True:
            data = self._call(endpoint, params)
            items.extend(data.get(key, []))
            if limit > 0 and len(items) >= limit:
                items = items[:limit]
                break
            if not data.get("next_url"):
                break
            qs = data["next_url"].rpartition("?")[2]
            params = dict(
                (k, unquote(v)) for part in qs.split("&") if "=" in part
                for k, v in [part.split("=", 1)]
            )
        return items

    def user_illusts(self, user_id, limit=0):
        return self._paginate("/v1/user/illusts", {"user_id": str(user_id)}, limit=limit)

    def user_bookmarks(self, user_id, restrict="public", limit=0):
        return self._paginate("/v1/user/bookmarks/illust", {
            "user_id": str(user_id), "restrict": restrict}, limit=limit)

    def search(self, word, sort="date_desc",
               target="partial_match_for_tags",
               date_start=None, date_end=None, limit=0):
        params = {"word": word, "sort": sort,
                  "search_target": target}
        if date_start:
            params["start_date"] = date_start
        if date_end:
            params["end_date"] = date_end
        return self._paginate("/v1/search/illust", params, limit=limit)

    def ranking(self, mode="day", date=None, limit=0):
        params = {"mode": mode}
        if date:
            params["date"] = date
        return self._paginate("/v1/illust/ranking", params, limit=limit)

    def ugoira_meta(self, illust_id):
        data = self._call("/v1/ugoira/metadata",
                          {"illust_id": str(illust_id)})
        return data.get("ugoira_metadata", {})


class PixivWorker(BaseDownloader):
    def __init__(self, tag, amount, rating, exclusions, net_config):
        super().__init__("pixiv", "Pixiv", amount, net_config)
        self.raw_tag = tag.strip()
        self.rating_filter = rating
        self.exclusions = exclusions
        self.refresh_token = os.getenv("PIXIV_REFRESH_TOKEN", "")
        self._api = None

        self.exclude_manga = "-manga" in self.exclusions
        self.only_ugoira = "-image" in self.exclusions and "-ugoira" not in self.exclusions
        self.only_images = "-ugoira" in self.exclusions and "-image" not in self.exclusions

        if ":" in self.raw_tag and not self.raw_tag.startswith("http"):
            self.mode, self.value = self.raw_tag.split(":", 1)
        else:
            self.mode = "artworks"
            self.value = self.raw_tag

        safe_value = re.sub(r'[\\/*?:"<>|]', "", self.value) or "pixiv"
        if self.mode == "ranking":
            self.tag_dir = os.path.join(self.site_root, "ranking", safe_value)
        else:
            self.tag_dir = os.path.join(self.site_root, safe_value)
        os.makedirs(self.tag_dir, exist_ok=True)

    def _api_instance(self):
        if self._api is None:
            self._api = PixivAppAPI(self.session, self.log, self.refresh_token)
        return self._api

    async def scraper_task(self):
        self.log(f"Pixiv mode: {self.mode}, value: {self.value}")
        api = self._api_instance()

        try:
            works = await asyncio.to_thread(self._fetch_works, api)
        except ValueError as e:
            self.log(f"Auth error: {e}")
            return
        except Exception as e:
            self.log(f"API error: {e}")
            return

        self.log(f"Found {len(works)} works")
        collected = 0
        for work in works:
            if self.stop_event.is_set():
                break
            if self.amount > 0 and collected >= self.amount:
                break
            collected += await self._process_work(work)
            if collected < len(works) and (
                    self.amount == 0 or collected < self.amount):
                await asyncio.sleep(self.anti_ban_pause)

    def _fetch_works(self, api):
        if self.mode == "bookmark":
            return api.user_bookmarks(self.value, limit=0)
        if self.mode == "search":
            return api.search(self.value, limit=0)
        if self.mode == "ranking":
            return api.ranking(self.value, limit=0)
        return api.user_illusts(self.value, limit=0)

    async def _process_work(self, work):
        work_id = work.get("id")
        if not work_id:
            return 0

        if self.exclude_manga and work.get("type") == "manga":
            return 0

        tags = [t["name"] for t in work.get("tags", [])]
        if "-ai" in self.exclusions or "ai" in self.exclusions:
            if any(tag in ("ai_generated", "ai") for tag in tags):
                return 0

        x_restrict = work.get("x_restrict", 0)
        if self.rating_filter:
            fc = self.rating_filter.split(":")[-1].lower()
            if fc in ("general", "g") and x_restrict != 0: return 0
            if fc in ("r18", "explicit", "e") and x_restrict != 1: return 0
            if fc == "r18g" and x_restrict != 2: return 0

        user = work.get("user", {})
        artists = [user.get("name", "")] if user.get("id") else []

        files = self._extract_files(work)
        if not files:
            return 0

        is_u = work.get("type") == "ugoira"

        if self.only_ugoira and not is_u:
            return 0
        if self.only_images and is_u:
            return 0

        count = 0
        if is_u and "-ugoira" in self.exclusions:
            return 0

        for file_info in files:
            if self.stop_event.is_set(): break
            if self.amount > 0 and count >= self.amount: break

            url = file_info["url"]
            ext = file_info.get("ext")
            num = file_info.get("num", 0)
            suffix = f"_p{num:02}" if num > 0 else ""
            filename = f"{work_id}{suffix}.{ext}"

            rating_label = RATING_CODES.get(x_restrict, "Unknown")
            rating_dir = os.path.join(self.tag_dir, rating_label, "images")
            os.makedirs(rating_dir, exist_ok=True)
            filepath = os.path.join(rating_dir, filename)

            if is_u and ext == "zip":
                ok = await self._process_ugoira(work_id, tags, artists, rating_dir)
                if ok: count += 1
                continue

            if await self.enqueue_download(url, filepath, filename,
                                           tags, artists):
                count += 1

        return count

    def _extract_files(self, work):
        """Extract file URLs from a work. Adapted from
        PixivExtractor._extract_files."""
        mp = work.get("meta_pages", [])
        ms = work.get("meta_single_page", {})

        if mp:
            result = []
            for img in mp:
                url = img.get("image_urls", {}).get("original", "")
                if not url:
                    continue
                ext = url.rpartition(".")[2].split("?")[0].lower()
                result.append({"url": url, "ext": ext, "num": len(result)})
            return result

        url = ms.get("original_image_url", "")
        if not url:
            image_urls = work.get("image_urls", {})
            url = image_urls.get("original", "")
            if not url:
                return []

        ext = url.rpartition(".")[2].split("?")[0].lower()
        is_ugoira = work.get("type") == "ugoira"

        if is_ugoira:
            return [{"url": url, "ext": "zip", "num": 0, "_ugoira": True}]

        return [{"url": url, "ext": ext, "num": 0}]

    async def _process_ugoira(self, work_id, tags,
                              artists, rating_dir):
        try:
            api = self._api_instance()
            meta = await asyncio.to_thread(api.ugoira_meta, work_id)
            frames = meta.get("frames", [])
            if not frames:
                self.log(f"No frame data for ugoira {work_id}")
                return False

            zip_src = meta.get("originalSrc")
            if not zip_src:
                zip_src = meta.get("zip_urls", {}).get("medium")
            if not zip_src:
                self.log(f"No zip URL for ugoira {work_id}")
                return False

            self.log(f"Converting ugoira {work_id} -> GIF "
                     f"({len(frames)} frames)")

            resp = await asyncio.to_thread(
                self.session.get, zip_src, stream=True, timeout=120,
                headers={"Referer": "https://www.pixiv.net/"})
            resp.raise_for_status()

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = zf.namelist()
                frame_images = []
                delays = []
                for f in frames:
                    fname = f.get("file", "")
                    delay = f.get("delay", 50)
                    if not fname or fname not in names:
                        continue
                    try:
                        img = Image.open(io.BytesIO(zf.read(fname)))
                        frame_images.append(img.convert("RGBA"))
                        delays.append(delay)
                    except Exception:
                        continue

            if not frame_images:
                self.log(f"No frames extracted from ugoira {work_id}")
                return False

            gif_name = f"{work_id}.gif"
            gif_path = os.path.join(rating_dir, gif_name)

            frame_images[0].save(
                gif_path,
                save_all=True,
                append_images=frame_images[1:],
                duration=delays,
                loop=0,
            )

            self.downloaded_count += 1
            self.dl_history.add(gif_name)
            save_history(self.site_root, self.dl_history)
            rel = os.path.relpath(gif_path, MASTER_FOLDER)
            add_to_gallery(self.name, gif_name, rel, tags, artists)
            send_tags(self.name, gif_name, tags, artists, rel)
            self.log(f"[SUCCESS] Ugoira -> GIF: {gif_name}")
            return True

        except Exception as e:
            self.log(f"Ugoira conversion failed for {work_id}: {e}")
            return False

    def run(self):
        asyncio.run(self.run_async_loop(self.scraper_task))
        self.log("--- Worker Terminated ---")


def get_refresh_token(username, password, proxy_url=None):
    """Get a Pixiv refresh token using email/password.
    Opens browser via webbrowser.open, user copies code from DevTools,
    submits it via Options tab -> /api/pixiv/submit_code."""
    return _browser_get_refresh_token(username, password, proxy_url)


def _api_get_refresh_token(username, password, proxy_url=None):
    return _browser_get_refresh_token(username, password, proxy_url)


_PENDING_PIXIV_LOGIN = {"code": None, "waiting": False}


def submit_pixiv_code(code):
    _PENDING_PIXIV_LOGIN["code"] = code.strip()


def _browser_get_refresh_token(username=None, password=None, proxy_url=None):
    import secrets
    import base64
    import webbrowser
    from hashlib import sha256, md5
    from datetime import datetime

    LOGIN_URL = "https://app-api.pixiv.net/web/v1/login"
    CALLBACK_URL = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
    TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"

    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(
        sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    login_params = (
        f"code_challenge={code_challenge}&code_challenge_method=S256"
        "&client=pixiv-android"
    )
    login_url = f"{LOGIN_URL}?{login_params}"

    _PENDING_PIXIV_LOGIN["code"] = None
    _PENDING_PIXIV_LOGIN["waiting"] = True

    log_msg("pixiv", "Opening Pixiv login in your default browser.")
    log_msg("pixiv", "1) Log in and solve the captcha if shown.")
    log_msg("pixiv", "2) After clicking Continue, a new tab opens and tries to redirect to a pixiv:// link.")
    log_msg("pixiv", "3) Open that tab's DevTools (F12) -> Network tab BEFORE clicking Continue.")
    log_msg("pixiv", "4) Find the request named 'callback?state=...' in the list.")
    log_msg("pixiv", "5) Click it, open its Payload/Query String Parameters, and copy the 'code' value.")
    log_msg("pixiv", "6) Go to the Options tab, paste the code, and submit. It expires ~30 seconds after login.")

    try:
        webbrowser.open(login_url)
    except Exception:
        pass
    log_msg("pixiv", f"If the browser didn't open, go to: {login_url}")

    code = None
    for _ in range(300):
        if _PENDING_PIXIV_LOGIN["code"]:
            code = _PENDING_PIXIV_LOGIN["code"]
            break
        time.sleep(1)

    _PENDING_PIXIV_LOGIN["waiting"] = False
    if not code:
        raise Exception("Timed out waiting for the code. Try again and submit it within 5 minutes.")

    log_msg("pixiv", "Exchanging authorization code for token...")

    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "include_policy": "true",
            "redirect_uri": CALLBACK_URL,
        },
        headers={
            "User-Agent": "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)",
            "X-Client-Time": ts,
            "X-Client-Hash": md5((ts + HASH_SECRET).encode()).hexdigest(),
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    refresh_token = data["refresh_token"]
    name = data.get("user", {}).get("name", "")
    account = data.get("user", {}).get("account", "")

    log_msg("pixiv", f"Logged in as {name} ({account}).")
    return refresh_token, name, account


def worker_pixiv(tag, amount, rating, exclusions, net_config):
    worker = PixivWorker(tag, amount, rating, exclusions, net_config)
    worker.run()
