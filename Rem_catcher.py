"""RemGodCatcher — async OOP web UI backend.

Every worker inherits BaseDownloader (shared.py). The App class owns
the Flask + SocketIO server and dispatches workers as asyncio tasks.
"""

import os, sys, threading, time, json, hashlib, re, urllib.parse, webbrowser, random
from datetime import datetime
from functools import lru_cache

import requests, urllib3, subprocess
from PIL import Image
from flask import Flask, send_from_directory, send_file, jsonify, request
from flask_socketio import SocketIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
    _STATIC = os.path.join(sys._MEIPASS, "web")
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _STATIC = "web"

load_dotenv(os.path.join(_BASE_DIR, ".env"))

import shared
from shared import MASTER_FOLDER

# ── Worker imports ──────────────────────────────────────────────
from workers.rule34 import worker_rule34
from workers.safebooru import worker_safebooru
from workers.zerochan import worker_zerochan
from workers.waifu_im import worker_waifu
from workers.nekos_best import worker_nekos_best
from workers.nekos_life import worker_nekos_life
from workers.gelbooru import worker_gelbooru
from workers.yande import worker_yande
from workers.konachan import worker_konachan
from workers.danbooru import worker_danbooru
from workers.sankaku import worker_sankaku
from workers.anime_dl import worker_anime_dl
from workers.pinterest_worker import worker_pinterest
from workers.pixiv import worker_pixiv, get_refresh_token, submit_pixiv_code
from workers.nekosia import worker_nekosia
from workers.eshuushuu import worker_eshuushuu

# ── Tag DB globals ──────────────────────────────────────────────
SAFE_TAGS_DB = []
YANDE_TAGS_DB = []
KONA_TAGS_DB = []
DAN_TAGS_DB = []
SANKAKU_TAGS_DB = []
ANIME_TAGS_DB = []
NEKOSIA_TAGS_DB = []
WAIFU_TAGS_DB = []
GELBOORU_TAGS_DB = []
WAIFU_TAG_MAP = {}

DATABASE_DIR = os.path.join(_BASE_DIR, "database")

STARTUP_CONFIG = {
    "use_proxy": os.getenv("USE_PROXY", "false").lower() == "true",
    "proxy_url": os.getenv("PROXY_URL", "http://127.0.0.1:10808"),
    "worker_proxy": json.loads(os.getenv("WORKER_PROXY", "{}") or "{}"),
    "verify_tls": os.getenv("VERIFY_TLS", "false").lower() == "true",
    "api_timeout": int(os.getenv("API_TIMEOUT", "10")),
    "retry_wait": int(os.getenv("RETRY_WAIT", "5")),
    "anti_ban_pause": float(os.getenv("ANTI_BAN_PAUSE", "3.0")),
    "download_retries": int(os.getenv("DOWNLOAD_RETRIES", "3")),
}
if STARTUP_CONFIG["use_proxy"]:
    os.environ.setdefault("HTTP_PROXY", STARTUP_CONFIG["proxy_url"])
    os.environ.setdefault("HTTPS_PROXY", STARTUP_CONFIG["proxy_url"])


# ── App class ───────────────────────────────────────────────────
class RemGodCatcherApp:
    """Wraps Flask, SocketIO, workers, and shutdown in one async-oriented class."""

    def __init__(self):
        self.app = Flask(__name__, static_folder=_STATIC)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode="threading", ping_interval=2, ping_timeout=5)
        self.shutdown_timer = None
        self._tag_tasks = {}
        self._tag_tasks_lock = threading.Lock()
        self._tag_semaphore = threading.Semaphore(MAX_CONCURRENT_TAGS := int(os.getenv("MAX_CONCURRENT_TAGS", "10")))

        # wire shared callbacks
        shared.log_callback = self._log
        shared.tag_callback = self._socketio_tag_handler
        shared.emit_callback = lambda e, d: self._socketio_emit(e, d)
        shared.MASTER_FOLDER = MASTER_FOLDER

        self._register_routes()
        self._register_socketio_events()

    # ── Logging & Events ────────────────────────────────────────
    def _log(self, worker_name, msg):
        try: self.socketio.emit("python_log", {"worker": worker_name, "msg": msg})
        except Exception: print(f"[{worker_name.upper()}] {msg}")

    def _socketio_emit(self, event, data):
        try: self.socketio.emit(event, data)
        except Exception: print(f"[SOCKETIO] {event}: {data}")

    def _socketio_tag_handler(self, worker_name, filename, tags_list, artist_list, filepath=None):
        try:
            hist = self._load_json_db(IMAGE_HISTORY_FILE)
            entry = {"site": worker_name, "filename": filename,
                     "tags": [t.strip() for t in tags_list if t.strip()],
                     "artists": [a.strip() for a in artist_list if a.strip()]}
            hist.insert(0, entry)
            self._save_json_db(IMAGE_HISTORY_FILE, hist[:100])
            self.socketio.emit("update_history")
        except Exception as e:
            print("Image Tag Save Error:", e)

    # ── JSON helpers ────────────────────────────────────────────
    @staticmethod
    def _load_json_db(filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                try: return json.load(f)
                except Exception: return []
        return []

    @staticmethod
    def _save_json_db(filepath, data):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    # ── Routes ──────────────────────────────────────────────────
    def _register_routes(self):
        # --- Static ---
        @self.app.route("/")
        def _index():
            return send_from_directory(_STATIC, "index.html")

        @self.app.route("/<path:path>")
        def _static_files(path):
            return send_from_directory(_STATIC, path)

        @self.app.route("/user_wallpapers/<path:filename>")
        def _custom_wallpaper(filename):
            custom_dir = os.path.join(_BASE_DIR, "user_wallpapers")
            if os.path.exists(os.path.join(custom_dir, filename)):
                return send_from_directory(custom_dir, filename)
            return send_from_directory(os.path.join(_STATIC, "wallpaper"), filename)

        # --- Config ---
        @self.app.route("/api/config", methods=["GET", "POST"])
        def _config_manager():
            if request.method == "POST":
                data = request.json
                for k in data:
                    if k in STARTUP_CONFIG:
                        STARTUP_CONFIG[k] = data[k]
                self._write_env()
                return jsonify({"success": True})
            return jsonify(STARTUP_CONFIG)

        @self.app.route("/api/folder", methods=["GET", "POST"])
        def _folder_manager():
            global MASTER_FOLDER
            if request.method == "POST":
                folder = request.json.get("folder", "")
                if folder:
                    shared.MASTER_FOLDER = os.path.join(folder, "Rem God")
                    MASTER_FOLDER = shared.MASTER_FOLDER
                    self._build_filepath_cache.cache_clear()
                    return jsonify({"folder": shared.MASTER_FOLDER})
            return jsonify({"folder": shared.MASTER_FOLDER})

        @self.app.route("/api/api-settings", methods=["GET", "POST"])
        def _api_settings_manager():
            env_path = os.path.join(_BASE_DIR, ".env")
            if request.method == "POST":
                data = request.json
                keys = {
                    "RULE34_API_KEY": "rule34_api_key", "RULE34_USER_ID": "rule34_user_id",
                    "GELBOORU_API_KEY": "gelbooru_api_key", "GELBOORU_USER_ID": "gelbooru_user_id",
                    "SANKA_LOGIN": "sanka_login", "SANKA_PASSWORD": "sanka_password",
                    "PINTEREST_COOKIES": "pinterest_cookies", "PINTEREST_EMAIL": "pinterest_email",
                    "PINTEREST_PASSWORD": "pinterest_password",
                    "PIXIV_LOGIN_EMAIL": "pixiv_login_email", "PIXIV_LOGIN_PASSWORD": "pixiv_login_password",
                    "PIXIV_REFRESH_TOKEN": "pixiv_refresh_token",
                    "ZEROCHAN_USERNAME": "zerochan_username",
                    "ZEROCHAN_PASSWORD": "zerochan_password",
                }
                for env_k, json_k in keys.items():
                    os.environ[env_k] = data.get(json_k, "")
                self._write_env()
                return jsonify({"success": True, "message": "All API keys saved!"})
            config = {}
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1); config[k.strip()] = v.strip()
            return jsonify({
                "rule34_api_key": config.get("RULE34_API_KEY", ""),
                "rule34_user_id": config.get("RULE34_USER_ID", ""),
                "gelbooru_api_key": config.get("GELBOORU_API_KEY", ""),
                "gelbooru_user_id": config.get("GELBOORU_USER_ID", ""),
                "sanka_login": config.get("SANKA_LOGIN", ""),
                "sanka_password": config.get("SANKA_PASSWORD", ""),
                "pinterest_cookies": config.get("PINTEREST_COOKIES", ""),
                "pinterest_email": config.get("PINTEREST_EMAIL", ""),
                "pinterest_password": config.get("PINTEREST_PASSWORD", ""),
                "pixiv_login_email": config.get("PIXIV_LOGIN_EMAIL", ""),
                "pixiv_login_password": config.get("PIXIV_LOGIN_PASSWORD", ""),
                "pixiv_refresh_token": config.get("PIXIV_REFRESH_TOKEN", ""),
                "zerochan_username": config.get("ZEROCHAN_USERNAME", ""),
                "zerochan_password": config.get("ZEROCHAN_PASSWORD", ""),
            })

        # --- Upload wallpaper ---
        @self.app.route("/api/upload_wallpaper", methods=["POST"])
        def _upload_wallpaper():
            if "file" not in request.files:
                return jsonify({"success": False, "error": "No file"}), 400
            f = request.files["file"]
            if f.filename == "":
                return jsonify({"success": False, "error": "No file"}), 400
            custom_dir = os.path.join(_BASE_DIR, "user_wallpapers")
            os.makedirs(custom_dir, exist_ok=True)
            fn = "".join(c for c in f.filename if c.isalnum() or c in " ._-").rstrip()
            if not fn:
                fn = f"wallpaper_{random.randint(1000,9999)}.png"
            f.save(os.path.join(custom_dir, fn))
            return jsonify({"success": True, "filename": fn})

        # --- Pixiv OAuth ---
        @self.app.route("/api/pixiv/get_token", methods=["POST"])
        def _pixiv_get_token():
            data = request.json
            u = (data.get("username") or "").strip()
            p = (data.get("password") or "").strip()
            if not u or not p:
                return jsonify({"success": False, "error": "Email and password required"}), 400
            try:
                proxy = STARTUP_CONFIG["proxy_url"] if STARTUP_CONFIG.get("use_proxy") else None
                token, name, account = get_refresh_token(u, p, proxy)
                os.environ["PIXIV_REFRESH_TOKEN"] = token
                self._write_env()
                return jsonify({"success": True, "token": token, "name": name,
                                "account": account, "message": f"Logged in as {name}."})
            except ImportError as e:
                return jsonify({"success": False, "error": str(e), "needs_playwright": True}), 400
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 400

        @self.app.route("/api/pixiv/submit_code", methods=["POST"])
        def _pixiv_submit_code():
            code = (request.json.get("code") or "").strip()
            if not code:
                return jsonify({"success": False, "error": "Code required"}), 400
            submit_pixiv_code(code)
            return jsonify({"success": True})

        # --- Tags ---
        @self.app.route("/api/tags/waifu", methods=["POST"])
        def _get_waifu_tags():
            if WAIFU_TAGS_DB:
                return jsonify([t["name"] for t in WAIFU_TAGS_DB])
            try:
                s = self._get_session("waifu", request.json)
                r = s.get("https://api.waifu.im/tags", timeout=10)
                return jsonify(sorted(set(t.get("name", t.get("slug"))
                    for t in r.json().get("items", []) if t)))
            except Exception:
                return jsonify(['maid', 'waifu', 'oppai', 'ero', 'ass', 'hentai', 'milf', 'paizuri', 'ecchi'])

        @self.app.route("/api/tags/zerochan", methods=["POST"])
        def _zerochan_suggest():
            query = request.json.get("query", "")
            try:
                s = self._get_session("zero", request.json.get("net_config", {}))
                s.headers.update({"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.zerochan.net/"})
                r = s.get(f"https://www.zerochan.net/suggest?q={urllib.parse.quote_plus(query)}", timeout=5)
                if r.status_code == 200:
                    items = r.json() if "{" in r.text else [x.strip() for x in r.text.split('\n') if x.strip()]
                    return jsonify(list(dict.fromkeys(i.split('|')[0].strip() for i in items)))
            except Exception:
                pass
            return jsonify([])

        def _tag_suggest(db, query):
            q = query.lower()
            return jsonify([t for t in db if t.startswith(q)][:50] if db else [])

        def _make(name, db_):
            def _handler():
                return _tag_suggest(db_, request.json.get("query", ""))
            _handler.__name__ = f"suggest_{name}"
            return _handler

        for route, name, db in [
            ("/api/tags/safe", "safe", SAFE_TAGS_DB), ("/api/tags/yande", "yande", YANDE_TAGS_DB),
            ("/api/tags/kona", "kona", KONA_TAGS_DB), ("/api/tags/dan", "dan", DAN_TAGS_DB),
            ("/api/tags/sankaku", "sankaku", SANKAKU_TAGS_DB),
            ("/api/tags/anime_dl", "anime_dl", ANIME_TAGS_DB),
            ("/api/tags/nekosia", "nekosia", NEKOSIA_TAGS_DB),
            ("/api/tags/gelbooru", "gelbooru", GELBOORU_TAGS_DB),
        ]:
            self.app.route(route, methods=["POST"])(_make(name, db))

        @self.app.route("/api/tags/eshuushuu", methods=["POST"])
        def _eshuushuu_suggest():
            q = request.json.get("query", "").lower()
            if not q:
                return jsonify([])
            results = []
            for t in ESHUSHU_TAGS_DB:
                if t["title"].lower().startswith(q):
                    results.append({
                        "title": t["title"],
                        "tag_id": t["tag_id"],
                        "type_name": t.get("type_name", ""),
                    })
                    if len(results) >= 50:
                        break
            return jsonify(results)

        @self.app.route("/api/tags/rule34", methods=["POST"])
        def _rule34_suggest():
            query = request.json.get("query", "")
            if len(query) < 2:
                return jsonify([])
            for url in [
                f"https://api.rule34.xxx/autocomplete.php?q={urllib.parse.quote(query)}",
                f"https://gelbooru.com/index.php?page=autocomplete2&term={urllib.parse.quote(query)}&type=tag_query&limit=20",
            ]:
                try:
                    s = self._get_session("rule34", request.json.get("net_config", {}))
                    r = s.get(url, timeout=3)
                    if r.status_code == 200:
                        return jsonify([i.get("value") for i in r.json() if isinstance(i, dict) and "value" in i])
                except Exception:
                    pass
            return jsonify([])

        # --- History & Favourites ---
        @self.app.route("/api/history", methods=["GET"])
        def _get_tag_history():
            return jsonify(self._load_json_db(TAG_HISTORY_FILE))

        for route, fname in [
            ("/api/history/clear", None), ("/api/image_history/clear", None),
        ]:
            def _clear_make(route_, _):
                def _clear():
                    self._save_json_db(TAG_HISTORY_FILE if "history" in route_ else IMAGE_HISTORY_FILE, [])
                    return jsonify({"success": True})
                _clear.__name__ = f"clear_{route_.lstrip('/').replace('/','_')}"
                return _clear
            self.app.route(route, methods=["POST"])(_clear_make(route, fname))

        @self.app.route("/api/history/remove", methods=["POST"])
        def _remove_tag_history():
            d = request.json
            hist = [x for x in self._load_json_db(TAG_HISTORY_FILE)
                    if not (x["site"] == d["site"] and x["tag"] == d["tag"])]
            self._save_json_db(TAG_HISTORY_FILE, hist)
            return jsonify({"success": True})

        @self.app.route("/api/image_history", methods=["GET"])
        def _get_image_history():
            return jsonify(self._load_json_db(IMAGE_HISTORY_FILE))

        @self.app.route("/api/image_history/remove", methods=["POST"])
        def _remove_image_history():
            fn = request.json.get("filename")
            hist = [x for x in self._load_json_db(IMAGE_HISTORY_FILE) if x.get("filename") != fn]
            self._save_json_db(IMAGE_HISTORY_FILE, hist)
            return jsonify({"success": True})

        @self.app.route("/api/favorites", methods=["GET", "POST"])
        def _manage_favorites():
            favs = self._load_json_db(FAV_TAGS_FILE)
            if request.method == "POST":
                d = request.json
                entry = {"site": d["site"], "tag": d["tag"]}
                if d["action"] == "add" and entry not in favs:
                    favs.append(entry)
                elif d["action"] == "remove" and entry in favs:
                    favs.remove(entry)
                self._save_json_db(FAV_TAGS_FILE, favs)
                return jsonify({"success": True, "favorites": favs})
            return jsonify(favs)

        # --- Gallery ---
        @self.app.route("/api/gallery", methods=["GET"])
        def _get_gallery():
            return jsonify(self._build_gallery_response(request.args))

        @self.app.route("/api/gallery/favourite", methods=["POST"])
        def _toggle_gallery_fav():
            img_id = request.json.get("id")
            gallery = shared.load_gallery()
            for img in gallery["images"]:
                if img["id"] == img_id:
                    img["favourite"] = not img.get("favourite", False)
                    shared.save_gallery(gallery)
                    return jsonify({"success": True, "favourite": img["favourite"]})
            return jsonify({"success": False, "error": "not found"}), 404

        @self.app.route("/api/gallery/tags", methods=["GET"])
        def _get_gallery_tags():
            gallery = shared.load_gallery()
            tags = set()
            for img in gallery.get("images", []):
                tags.update(img.get("tags", []))
            return jsonify(sorted(tags))

        @self.app.route("/api/gallery/sources", methods=["GET"])
        def _get_gallery_sources():
            gallery = shared.load_gallery()
            counts = {}
            for img in gallery.get("images", []):
                if img.get("filepath"):
                    s = img.get("site", "unknown"); counts[s] = counts.get(s, 0) + 1
            return jsonify(counts)

        @self.app.route("/api/gallery/file/<path:filepath>")
        def _gallery_file(filepath):
            root = os.path.realpath(MASTER_FOLDER)
            full = os.path.realpath(os.path.join(MASTER_FOLDER, filepath))
            if full != root and not full.startswith(root + os.sep):
                return "Forbidden", 403
            if os.path.isfile(full):
                return send_file(full)
            return "Not found", 404

        @self.app.route("/api/gallery/thumb/<path:filepath>")
        def _gallery_thumb(filepath):
            root = os.path.realpath(MASTER_FOLDER)
            full = os.path.realpath(os.path.join(MASTER_FOLDER, filepath))
            if full != root and not full.startswith(root + os.sep):
                return "Forbidden", 403
            if not os.path.isfile(full):
                return "Not found", 404
            ext = os.path.splitext(full)[1].lower()
            EXT_VIDEO = {'.mp4','.webm','.mov','.avi','.mkv'}
            key = hashlib.sha256(filepath.encode()).hexdigest()[:16]
            if ext in EXT_VIDEO:
                thumb = os.path.join(THUMB_CACHE, key + ".jpg")
                if not os.path.exists(thumb):
                    try:
                        subprocess.run(["ffmpeg", "-y", "-i", full, "-vframes", "1",
                                        "-q:v", "2", thumb],
                                       capture_output=True, timeout=10)
                    except Exception:
                        pass
                if os.path.exists(thumb):
                    return send_file(thumb, mimetype='image/jpeg')
                return send_file(full)
            key = hashlib.sha256(filepath.encode()).hexdigest()[:16]
            for fname, mime in [(key+".jpg", 'image/jpeg'), (key+".png", 'image/png')]:
                p = os.path.join(THUMB_CACHE, fname)
                if os.path.exists(p):
                    return send_file(p, mimetype=mime)
            try:
                img = Image.open(full)
                img.thumbnail((300, 300))
                if ext in ('.png', '.gif') or img.mode in ('RGBA', 'P', 'L', 'LA', '1'):
                    cache = os.path.join(THUMB_CACHE, key+".png")
                    img.save(cache, format='PNG')
                    return send_file(cache, mimetype='image/png')
                else:
                    if img.mode in ('RGBA', 'P', 'LA'):
                        img = img.convert('RGB')
                    cache = os.path.join(THUMB_CACHE, key+".jpg")
                    img.save(cache, format='JPEG', quality=85)
                    return send_file(cache, mimetype='image/jpeg')
            except Exception:
                return send_file(full)

        @self.app.route("/api/gallery/rescan", methods=["POST"])
        def _rescan_gallery():
            result = self._do_rescan()
            return jsonify(result)

        @self.app.route("/api/gallery/import", methods=["POST"])
        def _import_gallery():
            hist = self._load_json_db(IMAGE_HISTORY_FILE)
            gallery = shared.load_gallery()
            existing = {(i.get("site",""), i["filename"]) for i in gallery["images"]}
            fp_cache = self._build_filepath_cache()
            count = 0
            for entry in hist:
                fn = entry.get("filename", "")
                if fn and (entry.get("site",""), fn) not in existing:
                    gallery["images"].append({
                        "id": hashlib.sha256(f"{entry.get('site','')}:{fn}".encode()).hexdigest()[:12],
                        "filename": fn, "filepath": (fp_cache.get(fn) or [""])[0],
                        "site": entry.get("site", ""), "tags": entry.get("tags", []),
                        "artists": entry.get("artists", []), "favourite": False, "downloaded_at": ""})
                    existing.add((entry.get("site",""), fn)); count += 1
            shared.save_gallery(gallery)
            return jsonify({"success": True, "imported": count})

        @self.app.route("/api/ui_config", methods=["GET", "POST"])
        def _ui_config():
            default = {
                "theme_mode": "dark",
                "wallpapers": {
                    "Main": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
                    "Neko": {"dark": "Rem_neko_d.png", "light": "Rem_neko_l.png"},
                    "NekosLife": {"dark": "Rem_nekolife_d.png", "light": "Rem_nekolife_l.png"},
                    "Zero": {"dark": "Rem_zero_d.png", "light": "Rem_zero_l.png"},
                    "Waifu": {"dark": "Rem_waifu_d.png", "light": "Rem_waifu_l.png"},
                    "Safe": {"dark": "Rem_safe_d.png", "light": "Rem_safe_l.png"},
                    "Gelbooru": {"dark": "Rem_gelbooru_d.png", "light": "Rem_gelbooru_l.png"},
                    "Rule34": {"dark": "Rem_rule34_d.png", "light": "Rem_rule34_l.png"},
                    "Yande": {"dark": "Rem_yande_d.png", "light": "Rem_yande_l.png"},
                    "Kona": {"dark": "Rem_kona_d.png", "light": "Rem_kona_l.png"},
                    "Danbooru": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
                    "Pinterest": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
                    "Pixiv": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
                    "History": {"dark": "Rem_history_d.png", "light": "Rem_history_l.png"},
                    "Options": {"dark": "Rem_option_d.png", "light": "Rem_option_l.png"},
                    "Customize": {"dark": "Rem_custom_d.png", "light": "Rem_custom_l.png"},
                },
                "colors": {
                    "dark": {"title": "#00d2d3", "text": "#ffffff", "accent": "#ff9ff3",
                             "tab_text": "#ffffff", "btn_start_bg": "#00d2d3", "btn_start_text": "#0a0a0a",
                             "btn_stop_bg": "#ff9ff3", "btn_stop_text": "#1a0a1a"},
                    "light": {"title": "#0097e6", "text": "#2f3640", "accent": "#8c7ae6",
                              "tab_text": "#1a1a2e", "btn_start_bg": "#0097e6", "btn_start_text": "#ffffff",
                              "btn_stop_bg": "#8c7ae6", "btn_stop_text": "#ffffff"},
                },
            }
            if request.method == "POST":
                self._save_json_db(UI_CONFIG_FILE, request.json)
                return jsonify({"success": True})
            cfg = self._load_json_db(UI_CONFIG_FILE) or default
            if not os.path.exists(UI_CONFIG_FILE):
                self._save_json_db(UI_CONFIG_FILE, default)
            return jsonify(cfg)

    # ── SocketIO events ─────────────────────────────────────────
    def _register_socketio_events(self):
        @self.socketio.on("connect")
        def _on_connect():
            if self.shutdown_timer:
                self.shutdown_timer.cancel()
                self.shutdown_timer = None
            print("Browser tab connected!")

        @self.socketio.on("disconnect")
        def _on_disconnect():
            print("Browser tab closed. 3s shutdown timer...")
            def _die():
                print(">>> No active tabs. Shutting down. <<<")
                os._exit(0)
            self.shutdown_timer = threading.Timer(3.0, _die)
            self.shutdown_timer.start()

        @self.socketio.on("start_worker")
        def _start_worker(data):
            self._handle_start_worker(data)

        @self.socketio.on("stop_worker")
        def _stop_worker(data):
            name = data.get("worker")
            if name in shared.STOP_EVENTS:
                for evt in shared.STOP_EVENTS[name]:
                    evt.set()

    def _handle_start_worker(self, data):
        worker = data.get("worker")

        # save history
        tag = data.get("tag", data.get("category", "")).strip()
        if tag:
            try:
                hist = self._load_json_db(TAG_HISTORY_FILE)
                entry = {"site": worker, "tag": tag}
                if entry not in hist:
                    hist.insert(0, entry)
                    self._save_json_db(TAG_HISTORY_FILE, hist[:100])
            except Exception as e:
                print("History Save Error:", e)

        # Pinterest is special (no BaseWorker pattern in pinterest_dl)
        if worker == "pinterest":
            nc = data.get("net_config", {})
            for k in ("pinterest_cookies", "pinterest_email", "pinterest_password"):
                nc[k] = os.getenv(k.upper(), "")
            t = threading.Thread(
                target=worker_pinterest,
                args=(data.get("tag", ""), int(data.get("limit", 50)),
                      data.get("is_search", False), nc,
                      int(data.get("min_w", 0)), int(data.get("min_h", 0))),
                daemon=True)
            t.start()
            return

        # Map worker name → function + arg extractor
        _DISPATCH = {
            "zero":     (worker_zerochan,     lambda d: (d["tag"], int(d.get("limit", 50)), d["net_config"])),
            "waifu":    (worker_waifu,        lambda d: (d["tag"], int(d.get("limit", 30)), d.get("nsfw", False), d["net_config"])),
            "neko":     (worker_nekos_best,   lambda d: (d["category"], int(d.get("limit", 20)), d.get("format", "image"), d["net_config"])),
            "safe":     (worker_safebooru,    lambda d: (d["tag"], int(d.get("limit", 50)), d.get("exclusions", []), d["net_config"])),
            "rule34":   (worker_rule34,       lambda d: (d["tag"], int(d.get("limit", 50)), d.get("method", "and"), d.get("sort_type", "id"), d.get("sort_order", "desc"), d.get("exclusions", []), d["net_config"])),
            "gelbooru": (worker_gelbooru,    lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d["net_config"])),
            "nekos_life": (worker_nekos_life, lambda d: (d["category"], int(d.get("limit", 20)), d["net_config"], d.get("format", "both"))),
            "yande":    (worker_yande,        lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d["net_config"])),
            "kona":     (worker_konachan,     lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d["net_config"])),
            "dan":      (worker_danbooru,     lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d["net_config"])),
            "sankaku":  (worker_sankaku,      lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d["net_config"])),
            "anime_dl": (worker_anime_dl,     lambda d: (d["tag"], int(d.get("limit", 50)), d["net_config"])),
            "pixiv":    (worker_pixiv,        lambda d: (d["tag"], int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d["net_config"])),
            "nekosia":  (worker_nekosia,      lambda d: (d.get("tag", "waifu"), int(d.get("limit", 50)), d["net_config"])),
            "eshuushuu": (worker_eshuushuu, lambda d: (d["tag"], int(d.get("limit", 50)), d.get("exclusions", []), d.get("user_id", ""), d["net_config"])),
        }

        entry = _DISPATCH.get(worker)
        if not entry:
            return
        fn, arg_fn = entry
        args = arg_fn(data)
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()

    # ── .env writer ─────────────────────────────────────────────
    def _write_env(self):
        env_path = os.path.join(_BASE_DIR, ".env")
        keys = {
            "USE_PROXY": "true" if STARTUP_CONFIG.get("use_proxy") else "false",
            "PROXY_URL": STARTUP_CONFIG.get("proxy_url", ""),
            "WORKER_PROXY": json.dumps(STARTUP_CONFIG.get("worker_proxy", {})),
            "VERIFY_TLS": "true" if STARTUP_CONFIG.get("verify_tls") else "false",
            "API_TIMEOUT": str(STARTUP_CONFIG.get("api_timeout", 10)),
            "RETRY_WAIT": str(STARTUP_CONFIG.get("retry_wait", 5)),
            "ANTI_BAN_PAUSE": str(STARTUP_CONFIG.get("anti_ban_pause", 3.0)),
            "DOWNLOAD_RETRIES": str(STARTUP_CONFIG.get("download_retries", 3)),
        }
        for k in ("RULE34_API_KEY", "RULE34_USER_ID", "GELBOORU_API_KEY", "GELBOORU_USER_ID",
                  "SANKA_LOGIN", "SANKA_PASSWORD",
                  "PINTEREST_COOKIES", "PINTEREST_EMAIL", "PINTEREST_PASSWORD",
                  "PIXIV_LOGIN_EMAIL", "PIXIV_LOGIN_PASSWORD", "PIXIV_REFRESH_TOKEN",
                  "ZEROCHAN_USERNAME", "ZEROCHAN_PASSWORD"):
            keys[k] = os.environ.get(k, "")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        new_lines = []
        found = {k: False for k in keys}
        for line in lines:
            s = line.strip()
            matched = False
            for k in keys:
                if s.startswith(f"{k}="):
                    new_lines.append(f"{k}={keys[k]}\n")
                    found[k] = True
                    matched = True
                    break
            if not matched:
                new_lines.append(line)
        for k, v in keys.items():
            if not found[k]:
                new_lines.append(f"{k}={v}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    # ── Helpers: session, gallery, cache ────────────────────────
    @staticmethod
    def _get_session(site, net_config):
        s = requests.Session()
        if net_config and net_config.get("use_proxy"):
            p = net_config.get("proxy_url")
            s.proxies = {"http": p, "https": p}
        else:
            s.proxies = {"http": "", "https": "", "no_proxy": "*"}
        s.verify = net_config.get("verify_tls", False) if net_config else False
        if site == "safe":
            s.headers.update({"User-Agent": "RemGodCatcher/2.0", "Accept": "application/json"})
        elif site == "zero":
            s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*"})
            a = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2.0, status_forcelist=[429,500,502,503,504], allowed_methods=["GET"]))
            s.mount("https://", a); s.mount("http://", a)
            _zc_user = os.getenv("ZEROCHAN_USERNAME", "")
            if _zc_user:
                s.headers["User-Agent"] = f"RemGodCatcher - {_zc_user}"
        elif site in ("waifu", "neko"):
            s.headers.update({"Accept": "application/json"})
        elif site == "yande":
            s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        return s

    EXT_IMAGE = {'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tiff','.tif'}
    EXT_VIDEO = {'.mp4','.webm','.mov','.avi','.mkv'}

    @staticmethod
    @lru_cache(maxsize=1)
    def _build_filepath_cache():
        cache = {}
        for root, _, files in os.walk(MASTER_FOLDER):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in RemGodCatcherApp.EXT_IMAGE | RemGodCatcherApp.EXT_VIDEO:
                    cache.setdefault(fn, []).append(os.path.relpath(os.path.join(root, fn), MASTER_FOLDER))
        return cache

    def _build_gallery_response(self, args):
        search = args.get("search", "").lower().strip()
        site_filters = [s.strip() for s in args.get("site", "").split(",") if s.strip()] if args.get("site") else []
        fav_only = args.get("favourites", "").lower() == "true"
        sort_by = args.get("sort", "newest")
        type_filter = args.get("type", "all").lower().strip()
        type_filters = [t.strip() for t in type_filter.split(",") if t.strip()] if type_filter and type_filter != "all" else []
        rating_filter = [s.strip() for s in args.get("rating", "").split(",") if s.strip()] if args.get("rating") else []
        page = max(1, int(args.get("page", 1)))
        per_page = min(120, max(1, int(args.get("per_page", 24))))

        gallery = shared.load_gallery()
        images = gallery.get("images", [])
        fp_cache = self._build_filepath_cache()
        dirty = False
        for img in list(images):
            paths = fp_cache.get(img.get("filename", ""))
            fp = img.get("filepath", "")
            if not paths:
                if fp:
                    del img["filepath"]; dirty = True
                else:
                    images.remove(img); dirty = True
            elif fp in paths:
                continue
            elif len(paths) == 1:
                img["filepath"] = paths[0]; dirty = True
            else:
                del img["filepath"]; dirty = True
        if dirty:
            shared.save_gallery(gallery)
            images = gallery.get("images", [])
        images = [i for i in images if i.get("filepath")]

        if search:
            images = [i for i in images if any(search in t.lower() for t in i.get("tags", []))]
        if site_filters:
            images = [i for i in images if i.get("site", "").lower() in site_filters]
        if fav_only:
            images = [i for i in images if i.get("favourite")]
        if type_filters:
            def _match_type(img):
                ext = os.path.splitext(img.get("filename", ""))[1].lower()
                for tf in type_filters:
                    if tf == "image" and ext in self.EXT_IMAGE - {'.gif'}: return True
                    if tf == "gif" and ext == '.gif': return True
                    if tf == "video" and ext in self.EXT_VIDEO: return True
                return False
            images = [i for i in images if _match_type(i)]

        if rating_filter:
            images = [i for i in images if _img_rating(i) in rating_filter]

        def _sort_key(img):
            ts = img.get("downloaded_at", "")
            if ts:
                try: ts = datetime.fromisoformat(ts).timestamp()
                except: ts = 0
            else:
                fp = img.get("filepath", "")
                if fp:
                    ts = os.path.getmtime(os.path.join(MASTER_FOLDER, fp)) if os.path.exists(os.path.join(MASTER_FOLDER, fp)) else 0
                else: ts = 0
            return ts

        if sort_by == "newest": images.sort(key=_sort_key, reverse=True)
        elif sort_by == "oldest": images.sort(key=_sort_key)
        else: images.sort(key=lambda x: (not x.get("favourite"), _sort_key(x)), reverse=False)

        total = len(images)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start = (page - 1) * per_page
        return {"images": images[start:start+per_page], "total": total,
                "page": page, "total_pages": total_pages, "per_page": per_page}

    def _do_rescan(self):
        gallery = shared.load_gallery()
        by_fn = {(i.get("site",""), i["filename"]): i for i in gallery["images"]}
        added = fixed = 0
        for root, _, files in os.walk(MASTER_FOLDER):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in self.EXT_IMAGE and ext not in self.EXT_VIDEO:
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, MASTER_FOLDER)
                parts = rel.replace('\\', '/').split('/')
                site = parts[0] if len(parts) > 1 else "unknown"
                tag = parts[1] if len(parts) > 2 else ""
                tags = [tag] if tag else []
                if (site, fn) in by_fn:
                    e = by_fn[(site, fn)]
                    if not e.get("filepath"): e["filepath"] = rel; fixed += 1
                    if not e.get("tags"): e["tags"] = tags; fixed += 1
                else:
                    gallery["images"].append({
                        "id": hashlib.sha256(fn.encode()).hexdigest()[:12],
                        "filename": fn, "filepath": rel, "site": site,
                        "tags": tags, "artists": [], "favourite": False,
                        "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
                    })
                    by_fn[(site, fn)] = gallery["images"][-1]
                    added += 1
        before = len(gallery["images"])
        kept = []
        for img in gallery["images"]:
            fp = img.get("filepath", "")
            if os.path.exists(os.path.join(MASTER_FOLDER, fp)):
                kept.append(img)
            else:
                k = hashlib.sha256(fp.encode()).hexdigest()[:16]
                for ext in ('.jpg', '.png'):
                    p = os.path.join(THUMB_CACHE, k + ext)
                    if os.path.exists(p): os.remove(p)
        gallery["images"] = kept
        removed = before - len(gallery["images"])
        shared.save_gallery(gallery)
        self._build_filepath_cache.cache_clear()
        return {"success": True, "added": added, "fixed": fixed, "removed": removed}


# ── Constants ───────────────────────────────────────────────────
TAG_HISTORY_FILE = os.path.join(DATABASE_DIR, "tag_history.json")
FAV_TAGS_FILE = os.path.join(DATABASE_DIR, "fav_tags.json")
IMAGE_HISTORY_FILE = os.path.join(DATABASE_DIR, "image_history.json")
UI_CONFIG_FILE = os.path.join(DATABASE_DIR, "ui_config.json")
THUMB_CACHE = os.path.join(DATABASE_DIR, "thumb_cache")
os.makedirs(THUMB_CACHE, exist_ok=True)

# map gallery folder labels to canonical rating tokens for the gallery rating filter
RATING_FOLDERS = {
    "safe": {"safe", "general"},
    "sensitive": {"sensitive"},
    "questionable": {"questionable", "moderate"},
    "explicit": {"nsfw", "explicit", "r18", "r18g"},
}

def _img_rating(img):
    segs = set((img.get("filepath") or "").lower().replace("\\", "/").split("/"))
    for canon, labels in RATING_FOLDERS.items():
        if segs & labels:
            return canon
    return ""


# ── Tag DB loaders ──────────────────────────────────────────────
def load_safe_db():
    global SAFE_TAGS_DB
    p = os.path.join(DATABASE_DIR, "safe_tag_names.json")
    if not os.path.exists(p):
        p = os.path.join(DATABASE_DIR, "tag_names.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: SAFE_TAGS_DB = json.load(f)
        except Exception: pass

def load_waifu_tags():
    global WAIFU_TAGS_DB, WAIFU_TAG_MAP
    p = os.path.join(_BASE_DIR, "tags.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f: WAIFU_TAGS_DB = json.load(f)
            WAIFU_TAG_MAP = {t["name"].lower(): t["slug"] for t in WAIFU_TAGS_DB}
            shared.WAIFU_TAG_MAP = WAIFU_TAG_MAP
        except Exception: pass

def _load_tag_db(global_name, filename):
    p = os.path.join(DATABASE_DIR, filename)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                globals()[global_name] = json.load(f)
        except Exception: pass

def load_yande_db(): _load_tag_db("YANDE_TAGS_DB", "yande_tag_names.json")
def load_kona_db(): _load_tag_db("KONA_TAGS_DB", "kona_tag_names.json")
def load_dan_db(): _load_tag_db("DAN_TAGS_DB", "dan_tag_names.json")
def load_sankaku_db(): _load_tag_db("SANKAKU_TAGS_DB", "sankaku_tag_names.json")
load_nekosia_db = lambda: _load_tag_db("NEKOSIA_TAGS_DB", "nekosia_tag_names.json")
load_gelbooru_db = lambda: _load_tag_db("GELBOORU_TAGS_DB", "gelbooru_tag_names.json")

ESHUSHU_TAGS_DB = []

def load_eshuushuu_db():
    global ESHUSHU_TAGS_DB
    p = os.path.join(DATABASE_DIR, "eshuushuu_tags.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                ESHUSHU_TAGS_DB = json.load(f)
        except Exception: pass

def load_anime_dl_db():
    global ANIME_TAGS_DB
    p = os.path.join(DATABASE_DIR, "anime_tags.json")
    if os.path.exists(p):
        try:
            tags = []
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        tags.append(json.loads(line)["tag"])
            ANIME_TAGS_DB = tags
        except Exception: pass


# ── Entry point ─────────────────────────────────────────────────
def startup_rescan():
    """Build initial gallery from disk on boot."""
    with shared.GALLERY_LOCK:
        gallery = shared.load_gallery()
        by_fn = {(i.get("site",""), i["filename"]): i for i in gallery["images"]}
        count = 0
        for root, _, files in os.walk(MASTER_FOLDER):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in RemGodCatcherApp.EXT_IMAGE and ext not in RemGodCatcherApp.EXT_VIDEO:
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, MASTER_FOLDER)
                parts = rel.replace('\\', '/').split('/')
                site = parts[0] if len(parts) > 1 else "unknown"
                tag = parts[1] if len(parts) > 2 else ""
                tags = [tag] if tag else []
                if (site, fn) in by_fn:
                    if not by_fn[(site, fn)].get("tags"):
                        by_fn[(site, fn)]["tags"] = tags; count += 1
                    continue
                gallery["images"].append({
                    "id": hashlib.md5(f"{site}:{fn}".encode()).hexdigest()[:12],
                    "filename": fn, "filepath": rel, "site": site,
                    "tags": tags, "artists": [], "favourite": False,
                    "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
                })
                by_fn[(site, fn)] = gallery["images"][-1]; count += 1
        if count:
            shared.save_gallery(gallery)
            print(f"Rescanned {count} new images into gallery")


if __name__ == "__main__":
    load_safe_db()
    load_waifu_tags()
    load_yande_db()
    load_kona_db()
    load_dan_db()
    load_sankaku_db()
    load_nekosia_db()
    load_eshuushuu_db()
    load_anime_dl_db()
    load_gelbooru_db()
    startup_rescan()

    app = RemGodCatcherApp()
    port = 5000
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Rem God Catcher Web UI on {url} ...")
    webbrowser.open(url)
    app.socketio.run(app.app, host="127.0.0.1", port=port, debug=False, allow_unsafe_werkzeug=True)