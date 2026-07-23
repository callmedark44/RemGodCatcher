import os
import sys
import threading
import requests
import urllib3
import urllib.parse
import random
import json
import hashlib
import webbrowser
from PIL import Image
from datetime import datetime

from flask import Flask, send_from_directory, send_file, jsonify, request
from flask_socketio import SocketIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# تنظیم مسیرها برای زمانی که فایل .exe می‌شود
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    STATIC_FOLDER = os.path.join(sys._MEIPASS, "web")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_FOLDER = "web"

load_dotenv(os.path.join(BASE_DIR, ".env"))

import shared 
from workers.rule34 import worker_rule34
from workers.safebooru import worker_safebooru
from workers.zerochan import worker_zerochan
from workers.waifu_im import worker_waifu
from workers.nekos_best import worker_nekos_best
from workers.gelbooru import worker_gelbooru
from workers.nekos_life import worker_nekos_life
from workers.yande import worker_yande
from workers.konachan import worker_konachan
from workers.danbooru import worker_danbooru
from workers.sankaku import worker_sankaku
from workers.anime_dl import worker_anime_dl
from workers.pinterest_worker import worker_pinterest
from workers.pixiv import worker_pixiv, get_refresh_token, submit_pixiv_code

SAFE_TAGS_DB = []
YANDE_TAGS_DB = []
KONA_TAGS_DB = []
DAN_TAGS_DB = []
SANKAKU_TAGS_DB = []
ANIME_TAGS_DB = []
WAIFU_TAGS_DB = []
WAIFU_TAG_MAP = {}
MASTER_FOLDER = os.path.join(BASE_DIR, "Rem God")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
HISTORY_LOCK = threading.Lock()

STARTUP_CONFIG = {
    "use_proxy": os.getenv("USE_PROXY", "false").lower() == "true",
    "proxy_url": os.getenv("PROXY_URL", "http://127.0.0.1:10808"),
    "verify_tls": os.getenv("VERIFY_TLS", "false").lower() == "true",
    "api_timeout": int(os.getenv("API_TIMEOUT", "10")),
    "retry_wait": int(os.getenv("RETRY_WAIT", "5")),
    "anti_ban_pause": float(os.getenv("ANTI_BAN_PAUSE", "3.0")),
    "download_retries": int(os.getenv("DOWNLOAD_RETRIES", "3"))
}

if STARTUP_CONFIG["use_proxy"]:
    os.environ.setdefault("HTTP_PROXY", STARTUP_CONFIG["proxy_url"])
    os.environ.setdefault("HTTPS_PROXY", STARTUP_CONFIG["proxy_url"])

app = Flask(__name__, static_folder=STATIC_FOLDER)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# متغیر کنترل‌کننده زمان بسته شدن
shutdown_timer = None

def load_history(site_root):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        if os.path.exists(hist_path):
            try:
                with open(hist_path, "r", encoding="utf-8") as f: return set(json.load(f))
            except Exception: return set()
        return set()

def save_history(site_root, history_set):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        try:
            with open(hist_path, "w", encoding="utf-8") as f: json.dump(list(history_set), f, indent=4)
        except Exception: pass

def log_msg(worker_name, msg):
    try: socketio.emit("python_log", {"worker": worker_name, "msg": msg})
    except Exception: print(f"[{worker_name.upper()}] {msg}")

shared.log_callback = log_msg

def socketio_tag_handler(worker_name, filename, tags_list, artist_list, filepath=None):
    try:
        hist = load_json_db(IMAGE_HISTORY_FILE)
        entry = {
            "site": worker_name,
            "filename": filename,
            "tags": [t.strip() for t in tags_list if t.strip()],
            "artists": [a.strip() for a in artist_list if a.strip()]
        }
        hist.insert(0, entry)
        hist = hist[:100]
        save_json_db(IMAGE_HISTORY_FILE, hist)
        socketio.emit("update_history")
    except Exception as e:
        print("Image Tag Save Error:", e)

shared.tag_callback = socketio_tag_handler
# ❌ خط بازنویسی STOP_EVENTS را کاملاً حذف کردیم تا ارتباط قطع نشود!
shared.MASTER_FOLDER = MASTER_FOLDER

def socketio_emit(event, data):
    try: socketio.emit(event, data)
    except Exception: print(f"[SOCKETIO] {event}: {data}")
shared.emit_callback = socketio_emit

def load_waifu_tags():
    global WAIFU_TAGS_DB, WAIFU_TAG_MAP
    tags_path = os.path.join(BASE_DIR, "tags.json")
    if os.path.exists(tags_path):
        try:
            with open(tags_path, "r", encoding="utf-8") as f: WAIFU_TAGS_DB = json.load(f)
            WAIFU_TAG_MAP = {t["name"].lower(): t["slug"] for t in WAIFU_TAGS_DB}
        except Exception: pass

def get_session(site, net_config):
    session = requests.Session()
    if net_config.get("use_proxy"):
        p = net_config.get("proxy_url")
        session.proxies = {"http": p, "https": p}
    else:
        session.proxies = {"http": "", "https": "", "no_proxy": "*"}
    session.verify = net_config.get("verify_tls", False)

    if site == "safe": session.headers.update({"User-Agent": "RemGodCatcher/2.0", "Accept": "application/json"})
    elif site == "zero":
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*"})
        adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2.0, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"]))
        session.mount("https://", adapter); session.mount("http://", adapter)
    elif site in ["waifu", "neko"]: session.headers.update({"Accept": "application/json"})
    elif site == "yande": session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return session

def load_safe_db():
    global SAFE_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "safe_tag_names.json")
    if not os.path.exists(db_path): db_path = os.path.join(DATABASE_DIR, "tag_names.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: SAFE_TAGS_DB = json.load(f)
        except Exception: pass

def load_yande_db():
    global YANDE_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "yande_tag_names.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: YANDE_TAGS_DB = json.load(f)
        except Exception: pass

def load_kona_db():
    global KONA_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "kona_tag_names.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: KONA_TAGS_DB = json.load(f)
        except Exception: pass

def load_dan_db():
    global DAN_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "dan_tag_names.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: DAN_TAGS_DB = json.load(f)
        except Exception: pass

def load_sankaku_db():
    global SANKAKU_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "sankaku_tag_names.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: SANKAKU_TAGS_DB = json.load(f)
        except Exception: pass

def load_anime_dl_db():
    global ANIME_TAGS_DB
    db_path = os.path.join(DATABASE_DIR, "anime_tags.json")
    if os.path.exists(db_path):
        try:
            tags = []
            with open(db_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        obj = json.loads(line)
                        tags.append(obj["tag"])
            ANIME_TAGS_DB = tags
        except Exception: pass

@app.route("/")
def index(): return send_from_directory(STATIC_FOLDER, "index.html")

@app.route("/user_wallpapers/<path:filename>")
def custom_wallpaper(filename):
    custom_dir = os.path.join(BASE_DIR, "user_wallpapers")
    if os.path.exists(os.path.join(custom_dir, filename)):
        return send_from_directory(custom_dir, filename)
    return send_from_directory(os.path.join(STATIC_FOLDER, "wallpaper"), filename)

@app.route("/api/upload_wallpaper", methods=["POST"])
def upload_wallpaper():
    if "file" not in request.files: return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "": return jsonify({"success": False, "error": "No selected file"}), 400
    
    custom_dir = os.path.join(BASE_DIR, "user_wallpapers")
    os.makedirs(custom_dir, exist_ok=True)
    
    filename = "".join([c for c in file.filename if c.isalpha() or c.isdigit() or c in " ._-"]).rstrip()
    if not filename: filename = f"wallpaper_{random.randint(1000, 9999)}.png"
        
    file.save(os.path.join(custom_dir, filename))
    return jsonify({"success": True, "filename": filename})

@app.route("/<path:path>")
def static_files(path): return send_from_directory(STATIC_FOLDER, path)

@app.route("/api/config", methods=["GET", "POST"])
def config_manager():
    if request.method == "POST":
        data = request.json
        for key in data:
            if key in STARTUP_CONFIG: STARTUP_CONFIG[key] = data[key]

        env_path = os.path.join(BASE_DIR, ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f: lines = f.readlines()
        if lines and not lines[-1].endswith("\n"): lines[-1] += "\n"

        env_keys = {
            "USE_PROXY": str(STARTUP_CONFIG['use_proxy']).lower(),
            "PROXY_URL": STARTUP_CONFIG['proxy_url'],
            "VERIFY_TLS": str(STARTUP_CONFIG['verify_tls']).lower(),
            "API_TIMEOUT": str(STARTUP_CONFIG['api_timeout']),
            "RETRY_WAIT": str(STARTUP_CONFIG['retry_wait']),
            "ANTI_BAN_PAUSE": str(STARTUP_CONFIG['anti_ban_pause']),
            "DOWNLOAD_RETRIES": str(STARTUP_CONFIG['download_retries'])
        }

        new_lines = []
        found = {k: False for k in env_keys}
        for line in lines:
            stripped = line.strip()
            matched = False
            for key, val in env_keys.items():
                if stripped.startswith(f"{key}="):
                    new_lines.append(f"{key}={val}\n")
                    found[key] = True; matched = True; break
            if not matched: new_lines.append(line)

        for key, val in env_keys.items():
            if not found[key]: new_lines.append(f"{key}={val}\n")

        with open(env_path, "w", encoding="utf-8") as f: f.writelines(new_lines)
        return jsonify({"success": True})
    return jsonify(STARTUP_CONFIG)

@app.route("/api/folder", methods=["GET", "POST"])
def folder_manager():
    if request.method == "POST":
        folder = request.json.get("folder", "")
        if folder:
            shared.MASTER_FOLDER = os.path.join(folder, "Rem God")
            return jsonify({"folder": shared.MASTER_FOLDER})
    return jsonify({"folder": shared.MASTER_FOLDER})

@app.route("/api/api-settings", methods=["GET", "POST"])
def api_settings_manager():
    env_path = os.path.join(BASE_DIR, ".env")
    if request.method == "POST":
        data = request.json
        keys_to_save = {
            "RULE34_API_KEY": data.get("rule34_api_key", ""),
            "RULE34_USER_ID": data.get("rule34_user_id", ""),
            "GELBOORU_API_KEY": data.get("gelbooru_api_key", ""),
            "GELBOORU_USER_ID": data.get("gelbooru_user_id", ""),
            "SANKA_LOGIN": data.get("sanka_login", ""),
            "SANKA_PASSWORD": data.get("sanka_password", ""),
            "PINTEREST_COOKIES": data.get("pinterest_cookies", ""),
            "PINTEREST_EMAIL": data.get("pinterest_email", ""),
            "PINTEREST_PASSWORD": data.get("pinterest_password", ""),
            "PIXIV_LOGIN_EMAIL": data.get("pixiv_login_email", ""),
            "PIXIV_LOGIN_PASSWORD": data.get("pixiv_login_password", ""),
            "PIXIV_REFRESH_TOKEN": data.get("pixiv_refresh_token", "")
        }
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f: lines = f.readlines()
        if lines and not lines[-1].endswith("\n"): lines[-1] += "\n"

        new_lines = []
        found_keys = {k: False for k in keys_to_save}
        for line in lines:
            stripped = line.strip()
            matched = False
            for key, val in keys_to_save.items():
                if stripped.startswith(f"{key}="):
                    new_lines.append(f"{key}={val}\n")
                    found_keys[key] = True; matched = True; break
            if not matched: new_lines.append(line)

        for key, val in keys_to_save.items():
            if not found_keys[key]: new_lines.append(f"{key}={val}\n")

        with open(env_path, "w", encoding="utf-8") as f: f.writelines(new_lines)
        for k, v in keys_to_save.items(): os.environ[k] = v
        return jsonify({"success": True, "message": "All API keys saved successfully!"})

    config = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
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
        "pixiv_refresh_token": config.get("PIXIV_REFRESH_TOKEN", "")
    })

@app.route("/api/pixiv/get_token", methods=["POST"])
def pixiv_get_token():
    data = request.json
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"success": False, "error": "Email and password required"}), 400
    try:
        proxy = STARTUP_CONFIG.get("proxy_url") if STARTUP_CONFIG.get("use_proxy") else None
        token, name, account = get_refresh_token(username, password, proxy)
        env_path = os.path.join(BASE_DIR, ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith("PIXIV_REFRESH_TOKEN="):
                lines[i] = f"PIXIV_REFRESH_TOKEN={token}\n"
                found = True
                break
        if not found:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"PIXIV_REFRESH_TOKEN={token}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        os.environ["PIXIV_REFRESH_TOKEN"] = token
        return jsonify({
            "success": True,
            "token": token,
            "name": name,
            "account": account,
            "message": f"Logged in as {name} ({account}). Refresh token saved to .env"
        })
    except ImportError as e:
        return jsonify({"success": False, "error": str(e), "needs_playwright": True}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/pixiv/submit_code", methods=["POST"])
def pixiv_submit_code():
    data = request.json
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"success": False, "error": "Code required"}), 400
    submit_pixiv_code(code)
    return jsonify({"success": True})

@app.route("/api/tags/waifu", methods=["POST"])
def get_waifu_tags():
    if WAIFU_TAGS_DB: return jsonify([t["name"] for t in WAIFU_TAGS_DB])
    net_config = request.json
    try:
        session = get_session("waifu", net_config)
        resp = session.get("https://api.waifu.im/tags", timeout=10)
        return jsonify(sorted(list(set([t.get("name", t.get("slug")) for t in resp.json().get("items", []) if t]))))
    except Exception: return jsonify(['maid', 'waifu', 'oppai', 'ero', 'ass', 'hentai', 'milf', 'paizuri', 'ecchi'])

@app.route("/api/tags/zerochan", methods=["POST"])
def get_zerochan_suggestions():
    data = request.json
    query = data.get("query", "")
    try:
        session = get_session("zero", data.get("net_config", {}))
        session.headers.update({"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.zerochan.net/"})
        resp = session.get(f"https://www.zerochan.net/suggest?q={urllib.parse.quote_plus(query)}", timeout=5)
        if resp.status_code == 200:
            sugs = resp.json() if "{" in resp.text or "[" in resp.text else [s.strip() for s in resp.text.split('\n') if s.strip()]
            return jsonify(list(dict.fromkeys([s.split('|')[0].strip() for s in sugs])))
    except Exception: pass
    return jsonify([])

@app.route("/api/tags/safe", methods=["POST"])
def get_safe_suggestions():
    query = request.json.get("query", "").lower()
    if not SAFE_TAGS_DB: return jsonify([])
    return jsonify([t for t in SAFE_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/rule34", methods=["POST"])
def get_rule34_suggestions():
    data = request.json
    query = data.get("query", "")
    if len(query) < 2: return jsonify([])
    try:
        session = get_session("rule34", data.get("net_config", {}))
        url = f"https://api.rule34.xxx/autocomplete.php?q={urllib.parse.quote(query)}"
        resp = session.get(url, timeout=3)
        if resp.status_code == 200: return jsonify([item.get("value") for item in resp.json() if isinstance(item, dict) and "value" in item])
    except Exception: pass
    try:
        session = get_session("rule34", data.get("net_config", {}))
        url = f"https://gelbooru.com/index.php?page=autocomplete2&term={urllib.parse.quote(query)}&type=tag_query&limit=20"
        resp = session.get(url, timeout=5)
        if resp.status_code == 200: return jsonify([item.get("value") for item in resp.json() if isinstance(item, dict) and "value" in item])
    except Exception: pass
    return jsonify([])

@app.route("/api/tags/yande", methods=["POST"])
def get_yande_suggestions():
    query = request.json.get("query", "").lower()
    if not YANDE_TAGS_DB: return jsonify([])
    return jsonify([t for t in YANDE_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/kona", methods=["POST"])
def get_kona_suggestions():
    query = request.json.get("query", "").lower()
    if not KONA_TAGS_DB: return jsonify([])
    return jsonify([t for t in KONA_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/dan", methods=["POST"])
def get_dan_suggestions():
    query = request.json.get("query", "").lower()
    if not DAN_TAGS_DB: return jsonify([])
    return jsonify([t for t in DAN_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/sankaku", methods=["POST"])
def get_sankaku_suggestions():
    query = request.json.get("query", "").lower()
    if not SANKAKU_TAGS_DB: return jsonify([])
    return jsonify([t for t in SANKAKU_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/anime_dl", methods=["POST"])
def get_anime_dl_suggestions():
    query = request.json.get("query", "").lower()
    if not ANIME_TAGS_DB: return jsonify([])
    return jsonify([t for t in ANIME_TAGS_DB if t.startswith(query)][:50])

# --- TAG HISTORY & FAVORITES API ---
TAG_HISTORY_FILE = os.path.join(DATABASE_DIR, "tag_history.json")
FAV_TAGS_FILE = os.path.join(DATABASE_DIR, "fav_tags.json")
IMAGE_HISTORY_FILE = os.path.join(DATABASE_DIR, "image_history.json")
UI_CONFIG_FILE = os.path.join(DATABASE_DIR, "ui_config.json")

def load_json_db(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except Exception: return []
    return []

def save_json_db(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f: json.dump(data, f)

@app.route("/api/history", methods=["GET"])
def get_tag_history(): return jsonify(load_json_db(TAG_HISTORY_FILE))

@app.route("/api/history/clear", methods=["POST"])
def clear_tag_history():
    save_json_db(TAG_HISTORY_FILE, [])
    return jsonify({"success": True})

@app.route("/api/history/remove", methods=["POST"])
def remove_tag_history():
    data = request.json
    hist = load_json_db(TAG_HISTORY_FILE)
    hist = [x for x in hist if not (x["site"] == data["site"] and x["tag"] == data["tag"])]
    save_json_db(TAG_HISTORY_FILE, hist)
    return jsonify({"success": True})

@app.route("/api/image_history", methods=["GET"])
def get_image_history(): return jsonify(load_json_db(IMAGE_HISTORY_FILE))

@app.route("/api/image_history/clear", methods=["POST"])
def clear_image_history():
    save_json_db(IMAGE_HISTORY_FILE, [])
    return jsonify({"success": True})

@app.route("/api/image_history/remove", methods=["POST"])
def remove_image_history():
    data = request.json
    hist = [x for x in load_json_db(IMAGE_HISTORY_FILE) if x.get("filename") != data.get("filename")]
    save_json_db(IMAGE_HISTORY_FILE, hist)
    return jsonify({"success": True})

@app.route("/api/favorites", methods=["GET", "POST"])
def manage_favorites():
    favs = load_json_db(FAV_TAGS_FILE)
    if request.method == "POST":
        data = request.json
        action = data.get("action")
        entry = {"site": data.get("site"), "tag": data.get("tag")}
        if action == "add" and entry not in favs: favs.append(entry)
        elif action == "remove" and entry in favs: favs.remove(entry)
        save_json_db(FAV_TAGS_FILE, favs)
        return jsonify({"success": True, "favorites": favs})
    return jsonify(favs)


GALLERY_FILE = os.path.join(DATABASE_DIR, "gallery.json")

EXTENSIONS_IMAGE = {'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tiff','.tif'}
EXTENSIONS_VIDEO = {'.mp4','.webm','.mov','.avi','.mkv'}

def _build_filepath_cache():
    cache = {}
    for root, _, files in os.walk(MASTER_FOLDER):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXTENSIONS_IMAGE or ext in EXTENSIONS_VIDEO:
                cache[fn] = os.path.relpath(os.path.join(root, fn), MASTER_FOLDER)
    return cache

@app.route("/api/gallery", methods=["GET"])
def get_gallery():
    search = request.args.get("search", "").lower().strip()
    site_filter_raw = request.args.get("site", "").lower().strip()
    site_filters = [s.strip() for s in site_filter_raw.split(",") if s.strip()] if site_filter_raw else []
    fav_only = request.args.get("favourites", "").lower() == "true"
    sort_by = request.args.get("sort", "newest")
    type_filter_raw = request.args.get("type", "all").lower().strip()
    type_filters = [t.strip() for t in type_filter_raw.split(",") if t.strip()] if type_filter_raw and type_filter_raw != "all" else []
    rating_filter_raw = request.args.get("rating", "").lower().strip()
    rating_filters = [r.strip() for r in rating_filter_raw.split(",") if r.strip()] if rating_filter_raw else []
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(120, max(1, int(request.args.get("per_page", 24))))

    gallery = shared.load_gallery()
    images = gallery.get("images", [])
    fp_cache = _build_filepath_cache()
    dirty = False
    for img in images:
        cached = fp_cache.get(img.get("filename", ""))
        if cached:
            if img.get("filepath") != cached:
                img["filepath"] = cached
                dirty = True
        elif img.get("filepath"):
            del img["filepath"]
            dirty = True
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
        def matches_type(img):
            ext = os.path.splitext(img.get("filename",""))[1].lower()
            for tf in type_filters:
                if tf == "image" and ext in EXTENSIONS_IMAGE - {'.gif'}: return True
                if tf == "gif" and ext == '.gif': return True
                if tf == "video" and ext in EXTENSIONS_VIDEO: return True
            return False
        images = [i for i in images if matches_type(i)]
    if rating_filters:
        SUPPORTED_RATINGS = {
            "dan": {"safe", "sensitive", "questionable", "explicit"},
            "gelbooru": {"safe", "sensitive", "questionable", "explicit"},
            "kona": {"safe", "explicit"},
            "yande": {"safe", "explicit"},
            "sankaku": {"safe", "questionable", "explicit"},
            "pixiv": {"safe", "explicit"},
        }
        rating_aliases = {
            "safe": ["safe", "rating:safe", "general", "rating:general", "rating:g"],
            "sensitive": ["sensitive", "rating:sensitive", "rating:s"],
            "questionable": ["questionable", "rating:questionable", "rating:q"],
            "explicit": ["explicit", "rating:explicit", "rating:e", "nsfw"],
        }
        def matches_any_rating(img):
            site = img.get("site", "").lower()
            fpl = img.get("filepath", "").lower()
            for rf in rating_filters:
                supported = SUPPORTED_RATINGS.get(site)
                if supported is None:
                    continue
                if rf not in supported:
                    continue
                patterns = rating_aliases.get(rf, [rf])
                for p in patterns:
                    if any(p in t.lower() for t in img.get("tags", [])):
                        return True
                    if p in fpl:
                        return True
            return False
        images = [i for i in images if matches_any_rating(i)]

    def _sort_key(img):
        ts = img.get("downloaded_at", "")
        if ts:
            try:
                ts = datetime.fromisoformat(ts).timestamp()
            except Exception:
                ts = 0
        else:
            fp = img.get("filepath", "")
            if fp:
                full = os.path.join(MASTER_FOLDER, fp)
                if os.path.exists(full):
                    ts = os.path.getmtime(full)
                else:
                    ts = 0
            else:
                ts = 0
        return ts

    if sort_by == "newest":
        images.sort(key=_sort_key, reverse=True)
    elif sort_by == "oldest":
        images.sort(key=_sort_key)
    else:
        images.sort(key=lambda x: (not x.get("favourite"), _sort_key(x)), reverse=False)

    total = len(images)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    page_imgs = images[start:start + per_page]

    return jsonify({
        "images": page_imgs,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })

@app.route("/api/gallery/favourite", methods=["POST"])
def toggle_gallery_fav():
    data = request.json
    img_id = data.get("id")
    gallery = shared.load_gallery()
    for img in gallery["images"]:
        if img["id"] == img_id:
            img["favourite"] = not img.get("favourite", False)
            shared.save_gallery(gallery)
            return jsonify({"success": True, "favourite": img["favourite"]})
    return jsonify({"success": False, "error": "not found"}), 404

@app.route("/api/gallery/tags", methods=["GET"])
def get_gallery_tags():
    gallery = shared.load_gallery()
    tags = set()
    for img in gallery.get("images", []):
        for t in img.get("tags", []):
            tags.add(t)
    return jsonify(sorted(tags))

@app.route("/api/gallery/file/<path:filepath>")
def gallery_file(filepath):
    full = os.path.normpath(os.path.join(MASTER_FOLDER, filepath))
    if not full.startswith(os.path.normpath(MASTER_FOLDER)):
        return "Forbidden", 403
    if os.path.isfile(full):
        return send_file(full)
    return "Not found", 404

THUMB_CACHE = os.path.join(DATABASE_DIR, "thumb_cache")
os.makedirs(THUMB_CACHE, exist_ok=True)

@app.route("/api/gallery/thumb/<path:filepath>")
def gallery_thumb(filepath):
    full = os.path.normpath(os.path.join(MASTER_FOLDER, filepath))
    if not full.startswith(os.path.normpath(MASTER_FOLDER)):
        return "Forbidden", 403
    if not os.path.isfile(full):
        return "Not found", 404
    ext = os.path.splitext(full)[1].lower()
    if ext in EXTENSIONS_VIDEO:
        return send_file(full)
    cache_key = hashlib.sha256(filepath.encode()).hexdigest()[:16]
    cache_path = os.path.join(THUMB_CACHE, cache_key + ".jpg")
    png_cache = os.path.join(THUMB_CACHE, cache_key + ".png")
    if os.path.exists(cache_path):
        return send_file(cache_path, mimetype='image/jpeg')
    if os.path.exists(png_cache):
        return send_file(png_cache, mimetype='image/png')
    try:
        img = Image.open(full)
        img.thumbnail((300, 300))
        use_png = ext in ('png', 'gif') or img.mode in ('RGBA', 'P', 'L', 'LA', '1')
        is_png = use_png
        if is_png:
            img.save(png_cache, format='PNG')
            return send_file(png_cache, mimetype='image/png')
        else:
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            img.save(cache_path, format='JPEG', quality=85)
            return send_file(cache_path, mimetype='image/jpeg')
    except Exception:
        return send_file(full)

@app.route("/api/gallery/sources", methods=["GET"])
def get_gallery_sources():
    gallery = shared.load_gallery()
    counts = {}
    for img in gallery.get("images", []):
        if not img.get("filepath"):
            continue
        s = img.get("site", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return jsonify(counts)

@app.route("/api/gallery/rescan", methods=["POST"])
def rescan_gallery():
    gallery = shared.load_gallery()
    by_fn = {i["filename"]: i for i in gallery["images"]}
    count_added = 0
    count_fixed = 0
    for root, dirs, files in os.walk(MASTER_FOLDER):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTENSIONS_IMAGE and ext not in EXTENSIONS_VIDEO:
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, MASTER_FOLDER)
            parts = rel.replace('\\', '/').split('/')
            site = parts[0] if len(parts) > 1 else "unknown"

            tag = parts[1] if len(parts) > 2 else ""
            tags = [tag] if tag else []
            if fn in by_fn:
                existing = by_fn[fn]
                if not existing.get("filepath"):
                    existing["filepath"] = rel
                    count_fixed += 1
                if not existing.get("tags"):
                    existing["tags"] = tags
                    count_fixed += 1
            else:
                gallery["images"].append({
                    "id": hashlib.sha256(fn.encode()).hexdigest()[:12],
                    "filename": fn, "filepath": rel, "site": site,
                    "tags": tags, "artists": [], "favourite": False,
                    "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat()
                })
                by_fn[fn] = gallery["images"][-1]
                count_added += 1
    before = len(gallery["images"])
    kept = []
    for img in gallery["images"]:
        fp = img.get("filepath", "")
        if os.path.exists(os.path.join(MASTER_FOLDER, fp)):
            kept.append(img)
        else:
            key = hashlib.sha256(fp.encode()).hexdigest()[:16]
            for ext in ('.jpg', '.png'):
                p = os.path.join(THUMB_CACHE, key + ext)
                if os.path.exists(p):
                    os.remove(p)
    gallery["images"] = kept
    count_removed = before - len(gallery["images"])
    shared.save_gallery(gallery)
    return jsonify({"success": True, "added": count_added, "fixed": count_fixed, "removed": count_removed})

@app.route("/api/gallery/import", methods=["POST"])
def import_gallery_from_history():
    hist = load_json_db(IMAGE_HISTORY_FILE)
    gallery = shared.load_gallery()
    existing = {i["filename"] for i in gallery["images"]}
    fp_cache = _build_filepath_cache()
    count = 0
    for entry in hist:
        fn = entry.get("filename", "")
        if fn and fn not in existing:
            gallery["images"].append({
                "id": hashlib.sha256(f"{entry.get('site','')}:{fn}".encode()).hexdigest()[:12],
                "filename": fn,
                "filepath": fp_cache.get(fn, ""),
                "site": entry.get("site", ""),
                "tags": entry.get("tags", []),
                "artists": entry.get("artists", []),
                "favourite": False,
                "downloaded_at": ""
            })
            existing.add(fn)
            count += 1
    shared.save_gallery(gallery)
    return jsonify({"success": True, "imported": count})

@app.route("/api/ui_config", methods=["GET", "POST"])
def manage_ui_config():
    default_config = {
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
            "Customize": {"dark": "Rem_custom_d.png", "light": "Rem_custom_l.png"}
        },
        "colors": {
            "dark": {
                "title": "#00d2d3", "text": "#ffffff", "accent": "#ff9ff3", "tab_text": "#ffffff",
                "btn_start_bg": "#00d2d3", "btn_start_text": "#0a0a0a",
                "btn_stop_bg": "#ff9ff3", "btn_stop_text": "#1a0a1a"
            },
            "light": {
                "title": "#0097e6", "text": "#2f3640", "accent": "#8c7ae6", "tab_text": "#1a1a2e",
                "btn_start_bg": "#0097e6", "btn_start_text": "#ffffff",
                "btn_stop_bg": "#8c7ae6", "btn_stop_text": "#ffffff"
            }
        }
    }

    if request.method == "POST":
        data = request.json
        save_json_db(UI_CONFIG_FILE, data)
        return jsonify({"success": True})

    config = load_json_db(UI_CONFIG_FILE)
    if not config:
        config = default_config
        save_json_db(UI_CONFIG_FILE, config)
    return jsonify(config)


# ==========================================
# === AUTO-SHUTDOWN SYSTEM ===
# ==========================================
@socketio.on("connect")
def handle_connect():
    global shutdown_timer
    if shutdown_timer:
        shutdown_timer.cancel()
        shutdown_timer = None
    print("Browser Tab Connected!")

@socketio.on("disconnect")
def handle_disconnect():
    global shutdown_timer
    print("Browser Tab Closed! Shutting down in 3 seconds if not reconnected...")

    def shutdown_server():
        print(">>> No active tabs. Killing Rem God Catcher Server... <<<")
        os._exit(0)

    shutdown_timer = threading.Timer(3.0, shutdown_server)
    shutdown_timer.start()
# === Multi-tag concurrent dispatch ===
_TAG_TASKS = {}  # (api, full_query) -> {"thread": Thread}
_TAG_TASKS_LOCK = threading.Lock()
MAX_CONCURRENT_TAGS = int(os.getenv("MAX_CONCURRENT_TAGS", "10"))
_TAG_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_TAGS)

def _task_key(data):
    tag = data.get("tag", data.get("category", "")).strip()
    parts = [tag]
    for k in sorted(data.keys()):
        if k in ("worker", "net_config", "tag", "category", "limit", "min_w", "min_h"):
            continue
        v = data[k]
        if v is None or v == "" or (isinstance(v, (list, dict)) and not v):
            continue
        if isinstance(v, bool):
            parts.append(f"{k}:{'1' if v else '0'}")
        elif isinstance(v, (list, tuple)):
            parts.append(f"{k}:" + ",".join(str(x) for x in sorted(v)))
        else:
            v_str = str(v)
            if v_str.startswith(f"{k}:"):
                parts.append(v_str)
            else:
                parts.append(f"{k}:{v_str}")
    return " ".join(parts)

_TAG_DISPATCH = {
    "zero":     (worker_zerochan,     lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("net_config", {}))),
    "waifu":    (worker_waifu,        lambda d: (d.get("tag", ""), int(d.get("limit", 30)), d.get("nsfw", False), d.get("net_config", {}))),
    "neko":     (worker_nekos_best,   lambda d: (d.get("category", ""), int(d.get("limit", 20)), d.get("net_config", {}))),
    "safe":     (worker_safebooru,    lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("exclusions", []), d.get("net_config", {}))),
    "rule34":   (worker_rule34,       lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("method", "and"), d.get("sort_type", "id"), d.get("sort_order", "desc"), d.get("exclusions", []), d.get("net_config", {}))),
    "gelbooru": (worker_gelbooru,    lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d.get("net_config", {}))),
    "nekos_life": (worker_nekos_life, lambda d: (d.get("category", ""), int(d.get("limit", 20)), d.get("net_config", {}), d.get("format", "both"))),
    "yande":    (worker_yande,        lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("net_config", {}))),
    "kona":     (worker_konachan,     lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d.get("net_config", {}))),
    "dan":      (worker_danbooru,     lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d.get("net_config", {}))),
    "sankaku":  (worker_sankaku,      lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d.get("net_config", {}))),
    "anime_dl": (worker_anime_dl,     lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("net_config", {}))),
    "pixiv":    (worker_pixiv,        lambda d: (d.get("tag", ""), int(d.get("limit", 50)), d.get("rating", ""), d.get("exclusions", []), d.get("net_config", {}))),
}

def _run_tag_task(api, task_tag, fn, args):
    try:
        _TAG_SEMAPHORE.acquire()
        fn(*args)
    except Exception as e:
        shared.log_msg(api, f"[{task_tag}] Error: {e}")
    finally:
        _TAG_SEMAPHORE.release()
        with _TAG_TASKS_LOCK:
            _TAG_TASKS.pop((api, task_tag), None)
            shared.log_msg(api, f"[{task_tag}] Task finished.")

# ==========================================

@socketio.on("start_worker")
def handle_start_worker(data):
    worker = data.get("worker")
    tag = data.get("tag", data.get("category", "")).strip()

    if tag:
        try:
            hist = load_json_db(TAG_HISTORY_FILE)
            entry = {"site": worker, "tag": tag}
            if entry not in hist:
                hist.insert(0, entry)
                save_json_db(TAG_HISTORY_FILE, hist)
        except Exception as e:
            print("History Save Error:", e)

    if worker == "pinterest":
        net_config = data.get("net_config", {})
        net_config["pinterest_cookies"] = os.getenv("PINTEREST_COOKIES", "")
        net_config["pinterest_email"] = os.getenv("PINTEREST_EMAIL", "")
        net_config["pinterest_password"] = os.getenv("PINTEREST_PASSWORD", "")
        t = threading.Thread(target=worker_pinterest, args=(
            data.get("tag", ""), int(data.get("limit", 50)),
            data.get("is_search", False), net_config,
            int(data.get("min_w", 0)), int(data.get("min_h", 0))), daemon=True)
        t.start()
        return

    entry = _TAG_DISPATCH.get(worker)
    if not entry:
        return
    fn, arg_fn = entry
    args = arg_fn(data)
    task_tag = _task_key(data)

    with _TAG_TASKS_LOCK:
        if (worker, task_tag) in _TAG_TASKS:
            shared.log_msg(worker, f"[{task_tag}] Already running.")
            return

    t = threading.Thread(target=_run_tag_task, args=(worker, task_tag, fn, args), daemon=True)
    with _TAG_TASKS_LOCK:
        _TAG_TASKS[(worker, task_tag)] = {"thread": t}
    t.start()

@socketio.on("stop_worker")
def handle_stop_worker(data):
    name = data.get("worker")
    shared.log_msg(name, ">>> STOP SIGNAL RECEIVED! Terminating connections... <<<")
    if name in shared.STOP_EVENTS:
        for evt in shared.STOP_EVENTS[name]:
            evt.set()

def startup_rescan():
    with shared.GALLERY_LOCK:
        gallery = shared.load_gallery()
        by_fn = {i["filename"]: i for i in gallery["images"]}
        count = 0
        for root, dirs, files in os.walk(MASTER_FOLDER):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in EXTENSIONS_IMAGE and ext not in EXTENSIONS_VIDEO:
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, MASTER_FOLDER)
                parts = rel.replace('\\', '/').split('/')
                site = parts[0] if len(parts) > 1 else "unknown"
                tag = parts[1] if len(parts) > 2 else ""
                tags = [tag] if tag else []
                if fn in by_fn:
                    existing = by_fn[fn]
                    if not existing.get("tags"):
                        existing["tags"] = tags
                        count += 1
                    continue
                gallery["images"].append({
                    "id": hashlib.md5(f"{site}:{fn}".encode()).hexdigest()[:12],
                    "filename": fn, "filepath": rel, "site": site,
                    "tags": tags, "artists": [], "favourite": False,
                    "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat()
                })
                by_fn[fn] = gallery["images"][-1]
                count += 1
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
    load_anime_dl_db()
    startup_rescan()
    port = 5000
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Rem God Catcher Web UI on {url} ...")
    webbrowser.open(url)
    socketio.run(app, host="127.0.0.1", port=port, debug=False, allow_unsafe_werkzeug=True)