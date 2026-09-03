import os
import sys
import threading
import requests
import urllib3
import urllib.parse
import random
import hashlib
import webview
from PIL import Image
from datetime import datetime

from flask import Flask, send_from_directory, send_file, jsonify, request
from flask_socketio import SocketIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from database import DatabaseManager, SettingsManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
from workers.gsbooru import worker_gsbooru
from workers.nekos_life import worker_nekos_life
from workers.yande import worker_yande
from workers.konachan import worker_konachan
from workers.danbooru import worker_danbooru
from workers.sankaku import worker_sankaku
from workers.anime_dl import worker_anime_dl
from workers.pinterest_worker import worker_pinterest
from workers.pixiv import worker_pixiv

MASTER_FOLDER = os.path.join(BASE_DIR, "Rem God")
DATABASE_DIR = os.path.join(BASE_DIR, "database")

settings = SettingsManager(BASE_DIR)

SAFE_TAGS_DB = []
YANDE_TAGS_DB = []
KONA_TAGS_DB = []
DAN_TAGS_DB = []
SANKAKU_TAGS_DB = []
GELBOORU_TAGS_DB = []
ANIME_TAGS_DB = []
WAIFU_TAGS_DB = []
WAIFU_TAG_MAP = {}
ESHUUSHUU_TAGS_DB = []
NEKOSAPI_TAGS_DB = []
NEKOSIA_TAGS_DB = []
GSBOORU_TAGS_DB = []

if settings.get("use_proxy"):
    os.environ["HTTP_PROXY"] = str(settings.get("proxy_url") or "")
    os.environ["HTTPS_PROXY"] = str(settings.get("proxy_url") or "")
    os.environ.pop("no_proxy", None)
else:
    os.environ["HTTP_PROXY"] = ""
    os.environ["HTTPS_PROXY"] = ""
    os.environ["no_proxy"] = "*"

app = Flask(__name__, static_folder=STATIC_FOLDER)
# ponytail: pin threading mode — gevent (installed) buffers emits from our native worker threads
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

shutdown_timer = None


def log_msg(worker_name, msg):
    print(f"[{worker_name.upper()}] {msg}", flush=True)
    try: socketio.emit("python_log", {"worker": worker_name, "msg": msg})
    except Exception: pass

shared.log_callback = log_msg

def socketio_tag_handler(worker_name, filename, tags_list, artist_list, filepath=None, characters=None, copyrights=None, metadata_tags=None):
    try:
        DatabaseManager.add_image_history(worker_name, filename, tags_list, artist_list, filepath, characters, copyrights, metadata_tags)
        socketio.emit("update_history")
    except Exception as e:
        print("Image Tag Save Error:", e)

shared.tag_callback = socketio_tag_handler
shared.MASTER_FOLDER = MASTER_FOLDER

def socketio_emit(event, data):
    try: socketio.emit(event, data)
    except Exception: print(f"[SOCKETIO] {event}: {data}")

shared.emit_callback = socketio_emit


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
    elif site in ["waifu", "neko"]: session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    elif site == "yande": session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return session


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
        settings.update(data)
        settings.save_config()
        if data.get("use_proxy"):
            os.environ["HTTP_PROXY"] = str(data.get("proxy_url") or "")
            os.environ["HTTPS_PROXY"] = str(data.get("proxy_url") or "")
            os.environ.pop("no_proxy", None)
        else:
            os.environ["HTTP_PROXY"] = ""
            os.environ["HTTPS_PROXY"] = ""
            os.environ["no_proxy"] = "*"
        return jsonify({"success": True})
    return jsonify(settings.config)

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
    if request.method == "POST":
        settings.save_api_settings(request.json)
        return jsonify({"success": True, "message": "All API keys saved successfully!"})
    return jsonify(settings.load_api_settings())

@app.route("/api/pixiv/exchange-cookie", methods=["POST"])
def pixiv_exchange_cookie():
    """Exchange a pixiv.net PHPSESSID cookie for an OAuth refresh token.

    Same flow as `gallery-dl oauth:pixiv`, but the login step is done
    server-side with the user's cookie instead of a browser:
    1. GET the pixiv-android login URL (PKCE) with the PHPSESSID cookie
    2. Grab the `code` from the callback redirect
    3. Exchange code + verifier for tokens at oauth.secure.pixiv.net
    Pixiv is only reachable through the proxy, so the exchange always
    goes through the configured proxy (default 127.0.0.1:10808).
    """
    import re as _re
    import secrets as _secrets
    import hashlib as _hashlib
    import base64 as _base64

    raw = (request.json or {}).get("cookie", "").strip()
    if not raw:
        return jsonify({"success": False, "error": "No cookie provided"}), 400

    m = _re.search(r"PHPSESSID=([0-9a-fA-F_]+)", raw)
    phpsessid = m.group(1) if m else raw.split(";")[0].strip()
    if not phpsessid or "=" in phpsessid:
        return jsonify({"success": False, "error": "Could not find PHPSESSID in the provided cookie"}), 400

    proxy_url = settings.get("proxy_url") or "http://127.0.0.1:10808"
    session = requests.Session()
    session.proxies = {"http": proxy_url, "https": proxy_url}
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": f"PHPSESSID={phpsessid}",
    })

    try:
        verifier = _base64.urlsafe_b64encode(_secrets.token_bytes(64)).rstrip(b"=").decode()
        challenge = _base64.urlsafe_b64encode(
            _hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = _secrets.token_urlsafe(16)

        login_url = "https://app-api.pixiv.net/web/v1/login"
        params = {"client": "pixiv-android", "code_challenge": challenge,
                  "code_challenge_method": "S256", "state": state}
        resp = session.get(login_url, params=params, timeout=30, allow_redirects=True)

        code = None
        for r in [resp, *resp.history]:
            loc = r.headers.get("Location", "") or r.url
            cm = _re.search(r"[?&]code=([^&#]+)", loc)
            if cm:
                code = cm.group(1)
                break
        if not code:
            cm = _re.search(r"[?&]code=([^&#]+)", resp.text)
            code = cm.group(1) if cm else None
        if not code:
            return jsonify({"success": False, "error": "Login with this cookie failed (no auth code returned). The cookie may be expired — log in to pixiv.net again and copy a fresh PHPSESSID."}), 400

        token_resp = session.post(
            "https://oauth.secure.pixiv.net/auth/token",
            headers={"User-Agent": "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"},
            data={
                "client_id": "MOBrBDS8blbauoSck0ZfDbtuzpyT",
                "client_secret": "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj",
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "include_policy": "true",
                "redirect_uri": "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback",
            },
            timeout=30,
        )
        body = token_resp.json()
        if "error" in body:
            return jsonify({"success": False, "error": f"Token exchange failed: {body.get('error')}"}), 400

        refresh_token = body.get("refresh_token", "")
        if not refresh_token:
            return jsonify({"success": False, "error": "Token exchange returned no refresh token"}), 400

        settings.save_api_settings({**settings.load_api_settings(), "pixiv_refresh_token": refresh_token, "pixiv_cookie": raw})
        return jsonify({"success": True, "refresh_token": refresh_token})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:300]}), 500

@app.route("/api/tags/waifu", methods=["POST"])
def get_waifu_tags():
    net_config = request.json
    # ponytail: live list first (slugs, only tags with images), stale tags.json as offline fallback
    try:
        session = get_session("waifu", net_config)
        resp = session.get("https://api.waifu.im/tags", timeout=10)
        items = resp.json().get("items", [])
        live = sorted({t["slug"] for t in items if t.get("slug") and t.get("imageCount", 0) > 0})
        if live:
            return jsonify(live)
    except Exception:
        pass
    if WAIFU_TAGS_DB:
        return jsonify([t["name"] for t in WAIFU_TAGS_DB])
    return jsonify(['ass', 'ecchi', 'ero', 'genshin-impact', 'hentai', 'kamisato-ayaka', 'maid', 'marin-kitagawa', 'milf', 'mori-calliope', 'nami', 'one-piece', 'oppai', 'oral', 'paizuri', 'raiden-shogun', 'rem', 'selfies', 'uniform', 'waifu'])

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

@app.route("/api/tags/gelbooru", methods=["POST"])
def get_gelbooru_suggestions():
    query = request.json.get("query", "").lower()
    if not GELBOORU_TAGS_DB: return jsonify([])
    return jsonify([t for t in GELBOORU_TAGS_DB if t.lower().startswith(query)][:50])

@app.route("/api/tags/anime_dl", methods=["POST"])
def get_anime_dl_suggestions():
    query = request.json.get("query", "").lower()
    if not ANIME_TAGS_DB: return jsonify([])
    return jsonify([t for t in ANIME_TAGS_DB if t.startswith(query)][:50])

@app.route("/api/tags/eshuushuu", methods=["POST"])
def get_eshuushuu_suggestions():
    query = request.json.get("query", "").lower()
    if not ESHUUSHUU_TAGS_DB: return jsonify([])
    return jsonify([t for t in ESHUUSHUU_TAGS_DB if t.lower().startswith(query)][:50])

@app.route("/api/tags/nekosapi", methods=["POST"])
def get_nekosapi_suggestions():
    query = request.json.get("query", "").lower()
    if not NEKOSAPI_TAGS_DB: return jsonify([])
    return jsonify([t for t in NEKOSAPI_TAGS_DB if t.lower().startswith(query)][:50])

@app.route("/api/tags/nekosia", methods=["POST"])
def get_nekosia_suggestions():
    query = request.json.get("query", "").lower()
    if not NEKOSIA_TAGS_DB: return jsonify([])
    return jsonify([t for t in NEKOSIA_TAGS_DB if t.lower().startswith(query)][:50])

@app.route("/api/tags/gsbooru", methods=["POST"])
def get_gsbooru_suggestions():
    query = request.json.get("query", "").lower()
    if not GSBOORU_TAGS_DB: return jsonify([])
    return jsonify([t for t in GSBOORU_TAGS_DB if t.lower().startswith(query)][:50])

# --- TAG HISTORY & FAVORITES API ---
@app.route("/api/history", methods=["GET"])
def get_tag_history(): return jsonify(DatabaseManager.load_tag_history())

@app.route("/api/history/clear", methods=["POST"])
def clear_tag_history():
    DatabaseManager.clear_tag_history()
    return jsonify({"success": True})

@app.route("/api/history/remove", methods=["POST"])
def remove_tag_history():
    data = request.json
    DatabaseManager.remove_tag_history(data["site"], data["tag"])
    return jsonify({"success": True})

@app.route("/api/image_history", methods=["GET"])
def get_image_history(): return jsonify(DatabaseManager.load_image_history())

@app.route("/api/image_history/clear", methods=["POST"])
def clear_image_history():
    DatabaseManager.clear_image_history()
    return jsonify({"success": True})

@app.route("/api/image_history/remove", methods=["POST"])
def remove_image_history():
    data = request.json
    DatabaseManager.remove_image_history(data.get("filename"))
    return jsonify({"success": True})

@app.route("/api/favorites", methods=["GET", "POST"])
def manage_favorites():
    if request.method == "POST":
        data = request.json
        favs = DatabaseManager.toggle_favorite(data.get("site"), data.get("tag"))
        return jsonify({"success": True, "favorites": favs})
    return jsonify(DatabaseManager.load_favorites())


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

def _apply_gallery_filters(images, search, site_filters, fav_only, type_filters, rating_filters):
    def _get_all_tags(img):
        tags = img.get("tags", {})
        if isinstance(tags, dict):
            result = []
            for v in tags.values():
                if isinstance(v, list):
                    result.extend(v)
            return result
        return tags if isinstance(tags, list) else []

    if search:
        images = [i for i in images if any(search in t.lower() for t in _get_all_tags(i))]
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
            "safe": {"safe"},
            "dan": {"safe", "sensitive", "questionable", "explicit"},
            "gelbooru": {"safe", "sensitive", "questionable", "explicit"},
            "gsbooru": {"safe", "sensitive", "questionable", "explicit"},
            "kona": {"safe", "questionable", "explicit"},
            "yande": {"safe", "questionable", "explicit"},
            "sankaku": {"safe", "questionable", "explicit"},
            "rule34": {"explicit"},
            "safebooru": {"safe"},
            "nekosapi": {"safe", "sensitive", "questionable", "explicit"},
            "nekosia": {"safe", "sensitive"},
            "waifu.im": {"safe", "explicit"},
        }
        rating_aliases = {
            "safe": ["safe", "rating:safe", "general", "rating:general", "rating:g"],
            "sensitive": ["sensitive", "suggestive", "rating:sensitive", "rating:s"],
            "questionable": ["questionable", "borderline", "rating:questionable", "rating:q"],
            "explicit": ["explicit", "rating:explicit", "rating:e", "nsfw"],
        }
        def matches_any_rating(img):
            site = shared.normalize_site(img.get("site", ""))
            fpl = img.get("filepath", "").lower()
            all_tags = _get_all_tags(img)
            for rf in rating_filters:
                supported = SUPPORTED_RATINGS.get(site)
                if supported is None:
                    continue
                if rf not in supported:
                    continue
                patterns = rating_aliases.get(rf, [rf])
                for p in patterns:
                    if any(p in t.lower() for t in all_tags):
                        return True
                    if p in fpl:
                        return True
            return False
        images = [i for i in images if matches_any_rating(i)]
    return images

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
    per_page = min(400, max(1, int(request.args.get("per_page", 24))))

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
    images = _apply_gallery_filters(images, search, site_filters, fav_only, type_filters, rating_filters)

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
        img_tags = img.get("tags", {})
        if isinstance(img_tags, dict):
            for v in img_tags.values():
                if isinstance(v, list):
                    for t in v:
                        tags.add(t)
        elif isinstance(img_tags, list):
            for t in img_tags:
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

@app.route("/api/thumb_by_name/<filename>")
def thumb_by_name(filename):
    full = os.path.join(MASTER_FOLDER, filename)
    if not os.path.isfile(full):
        # Search subdirectories
        for root, _, files in os.walk(MASTER_FOLDER):
            if filename in files:
                full = os.path.join(root, filename)
                break
        else:
            return "Not found", 404
    return redirect_to_thumb(full, filename)

def redirect_to_thumb(full_path, rel_filename):
    cache_key = hashlib.sha256(rel_filename.encode()).hexdigest()[:16]
    cache_path = os.path.join(THUMB_CACHE, cache_key + ".jpg")
    if os.path.exists(cache_path):
        return send_file(cache_path, mimetype='image/jpeg')
    try:
        img = Image.open(full_path)
        img.draft('RGB', (300, 300))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        img.save(cache_path, format='JPEG', quality=85)
        return send_file(cache_path, mimetype='image/jpeg')
    except Exception:
        return "Thumbnail generation failed", 415

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
    cache_key = hashlib.sha256(filepath.encode()).hexdigest()[:16]
    cache_path = os.path.join(THUMB_CACHE, cache_key + ".jpg")

    if os.path.exists(cache_path):
        return send_file(cache_path, mimetype='image/jpeg')

    if ext in EXTENSIONS_VIDEO:
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", full, "-vframes", "1", "-ss", "0", "-vf", "scale=300:300:force_original_aspect_ratio=decrease,pad=300:300:(ow-iw)/2:(oh-ih)/2", cache_path],
                       capture_output=True, timeout=10)
        if os.path.exists(cache_path):
            return send_file(cache_path, mimetype='image/jpeg')
        return "", 415

    try:
        img = Image.open(full)
        # ponytail: cap memory usage for very large images; decompress bomb protection
        img.draft('RGB', (300, 300))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        img.save(cache_path, format='JPEG', quality=85)
        return send_file(cache_path, mimetype='image/jpeg')
    except Exception as e:
        print("Thumb generation error:", e)
        # اگه ارور داد، همون عکس اصلی رو بفرست تا والپیپر سیاه نشون نده!
        return send_file(full)

@app.route("/api/gallery/sources", methods=["GET"])
def get_gallery_sources():
    search = request.args.get("search", "").lower().strip()
    fav_only = request.args.get("favourites", "").lower() == "true"
    type_filter_raw = request.args.get("type", "all").lower().strip()
    type_filters = [t.strip() for t in type_filter_raw.split(",") if t.strip()] if type_filter_raw and type_filter_raw != "all" else []
    rating_filter_raw = request.args.get("rating", "").lower().strip()
    rating_filters = [r.strip() for r in rating_filter_raw.split(",") if r.strip()] if rating_filter_raw else []
    images = shared.load_gallery().get("images", [])
    images = _apply_gallery_filters(images, search, [], fav_only, type_filters, rating_filters)
    counts = {}
    for img in images:
        s = shared.normalize_site(img.get("site", "unknown"))
        counts[s] = counts.get(s, 0) + 1
    return jsonify(counts)

@app.route("/api/gallery/delete", methods=["POST"])
def delete_gallery_image():
    data = request.json
    img_id = data.get("id")
    gallery = shared.load_gallery()
    for i, img in enumerate(gallery["images"]):
        if img["id"] == img_id:
            # پاک کردن فیزیکی فایل از روی هارد
            full_path = os.path.join(shared.MASTER_FOLDER, img.get("filepath", ""))
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                print("Error deleting file:", e)
            # حذف از دیتابیس گالری
            gallery["images"].pop(i)
            shared.save_gallery(gallery)
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "Not found"}), 404 

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
            tags = {"tag": [tag]} if tag else {"tag": []}
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
                    "tags": tags, "favourite": False,
                    "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat()
                })
                by_fn[fn] = gallery["images"][-1]
                count_added += 1
    shared.save_gallery(gallery)
    return jsonify({"success": True, "added": count_added, "fixed": count_fixed})

@app.route("/api/gallery/import", methods=["POST"])
def import_gallery_from_history():
    from shared import tags_dict_from_lists
    hist = DatabaseManager.load_image_history()
    gallery = shared.load_gallery()
    existing = {i["filename"] for i in gallery["images"]}
    fp_cache = _build_filepath_cache()
    count = 0
    for entry in hist:
        fn = entry.get("filename", "")
        if fn and fn not in existing:
            entry_tags = entry.get("tags", {})
            entry_artists = entry.get("artists", [])
            if isinstance(entry_tags, dict):
                tags = entry_tags
            else:
                tags = tags_dict_from_lists(entry_tags, entry_artists)
            gallery["images"].append({
                "id": hashlib.sha256(f"{entry.get('site','')}:{fn}".encode()).hexdigest()[:12],
                "filename": fn,
                "filepath": fp_cache.get(fn, ""),
                "site": entry.get("site", ""),
                "tags": tags,
                "favourite": False,
                "downloaded_at": ""
            })
            existing.add(fn)
            count += 1
    shared.save_gallery(gallery)
    return jsonify({"success": True, "imported": count})

@app.route("/api/ui_config", methods=["GET", "POST"])
def manage_ui_config():
    if request.method == "POST":
        DatabaseManager.save_ui_config(request.json)
        return jsonify({"success": True})
    return jsonify(DatabaseManager.load_ui_config())


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

# ==========================================

@socketio.on("start_worker")
def handle_start_worker(data):
    worker = data.get("worker")
    net_config = data.get("net_config", {})

    tag = data.get("tag", data.get("category", "")).strip()

    if tag:
        try:
            DatabaseManager.add_tag_history(worker, tag)
        except Exception as e:
            print("History Save Error:", e)

    if worker == "zero":
        net_config["zerochan_login"] = os.getenv("ZEROCHAN_LOGIN") or os.getenv("ZEROCHAN_USERNAME", "")
        net_config["zerochan_password"] = os.getenv("ZEROCHAN_PASSWORD", "")
        threading.Thread(target=worker_zerochan, args=(data.get("tag", ""), int(data.get("limit", 50)), net_config), daemon=True).start()
    elif worker == "waifu": threading.Thread(target=worker_waifu, args=(data.get("tag", ""), int(data.get("limit", 30)), data.get("nsfw", False), net_config), daemon=True).start()
    elif worker == "neko": threading.Thread(target=worker_nekos_best, args=(data.get("category", ""), int(data.get("limit", 20)), net_config), daemon=True).start()
    elif worker == "safe": threading.Thread(target=worker_safebooru, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "rule34": threading.Thread(target=worker_rule34, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("method", "and"), data.get("sort_type", "id"), data.get("sort_order", "desc"), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "gelbooru": threading.Thread(target=worker_gelbooru, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "gsbooru": threading.Thread(target=worker_gsbooru, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "nekos_life": threading.Thread(target=worker_nekos_life, args=(data.get("category", ""), int(data.get("limit", 20)), net_config, data.get("format", "both")), daemon=True).start()
    elif worker == "yande": threading.Thread(target=worker_yande, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), net_config), daemon=True).start()
    elif worker == "kona": threading.Thread(target=worker_konachan, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "dan": threading.Thread(target=worker_danbooru, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "sankaku": threading.Thread(target=worker_sankaku, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "anime_dl": threading.Thread(target=worker_anime_dl, args=(data.get("tag", ""), int(data.get("limit", 50)), net_config), daemon=True).start()
    elif worker == "pinterest":
        net_config["pinterest_cookies"] = os.getenv("PINTEREST_COOKIES", "")
        net_config["pinterest_email"] = os.getenv("PINTEREST_EMAIL", "")
        net_config["pinterest_password"] = os.getenv("PINTEREST_PASSWORD", "")
        threading.Thread(target=worker_pinterest, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("is_search", False), net_config, int(data.get("min_w", 0) or 0), int(data.get("min_h", 0) or 0)), daemon=True).start()
    elif worker == "pixiv":
        net_config["pixiv_refresh_token"] = os.getenv("PIXIV_REFRESH_TOKEN", "")
        threading.Thread(target=worker_pixiv, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), data.get("exclusions", []), net_config), daemon=True).start()
    elif worker == "eshuushuu":
        from workers.eshuushuu import worker_eshuushuu
        threading.Thread(target=worker_eshuushuu, args=(data.get("tag", ""), int(data.get("limit", 50)), [], data.get("user_id", ""), net_config), daemon=True).start()
    elif worker == "nekosapi":
        from workers.nekosapi import worker_nekosapi
        threading.Thread(target=worker_nekosapi, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", ""), net_config), daemon=True).start()
    elif worker == "nekosia":
        try:
            from workers.nekosia import worker_nekosia
            threading.Thread(target=worker_nekosia, args=(data.get("tag", ""), int(data.get("limit", 50)), data.get("rating", "safe"), net_config), daemon=True).start()
        except ImportError:
            pass # در صورتی که بعدا خواستی فایل nekosia.py رو بسازی ارور نده

@socketio.on("stop_worker")
def handle_stop_worker(data):
    name = data.get("worker")
    shared.log_msg(name, ">>> STOP SIGNAL RECEIVED! Terminating connections... <<<")
    if name in shared.STOP_EVENTS:
        for evt in shared.STOP_EVENTS[name]:
            evt.set()

def startup_rescan():
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
            tags = {"tag": [tag]} if tag else {"tag": []}
            if fn in by_fn:
                existing = by_fn[fn]
                if not existing.get("tags"):
                    existing["tags"] = tags
                    count += 1
                continue
            gallery["images"].append({
                "id": hashlib.sha256(fn.encode()).hexdigest()[:12],
                "filename": fn, "filepath": rel, "site": site,
                "tags": tags, "favourite": False,
                "downloaded_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat()
            })
            by_fn[fn] = gallery["images"][-1]
            count += 1
    if count:
        print(f"Rescanned {count} new images into gallery")

    # prune entries whose file no longer exists (deleted manually or by cleanups)
    kept = [i for i in gallery["images"]
            if os.path.isfile(os.path.join(MASTER_FOLDER, i.get("filepath", "")))]
    removed = len(gallery["images"]) - len(kept)
    if removed:
        gallery["images"] = kept
        print(f"Pruned {removed} dead gallery entries")

    if count or removed:
        shared.save_gallery(gallery)

if __name__ == "__main__":
    SAFE_TAGS_DB = DatabaseManager.load_safe_tags()
    WAIFU_TAGS_DB, WAIFU_TAG_MAP = DatabaseManager.load_waifu_tags()
    shared.WAIFU_TAG_MAP = WAIFU_TAG_MAP
    YANDE_TAGS_DB = DatabaseManager.load_yande_tags()
    KONA_TAGS_DB = DatabaseManager.load_kona_tags()
    DAN_TAGS_DB = DatabaseManager.load_dan_tags()
    SANKAKU_TAGS_DB = DatabaseManager.load_sankaku_tags()
    GELBOORU_TAGS_DB = DatabaseManager.load_gelbooru_tags()
    ANIME_TAGS_DB = DatabaseManager.load_anime_dl_tags()
    ESHUUSHUU_TAGS_DB = DatabaseManager.load_eshuushuu_tags()
    NEKOSAPI_TAGS_DB = DatabaseManager.load_nekosapi_tags()
    NEKOSIA_TAGS_DB = DatabaseManager.load_nekosia_tags()
    GSBOORU_TAGS_DB = DatabaseManager.load_gsbooru_tags()
    startup_rescan()
    port = 5000
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Rem God Catcher on {url} ...")

    def start_server():
        socketio.run(app, host="127.0.0.1", port=port, debug=False, allow_unsafe_werkzeug=True)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    webview.create_window("Rem God Catcher", url, width=1400, height=900)
    gui = "gtk" if sys.platform == "linux" else None
    webview.start(gui=gui)
