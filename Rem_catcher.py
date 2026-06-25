import eel
import os
import sys
import time
import threading
import requests
import urllib3
import urllib.parse
import random
import re
import json
import xml.etree.ElementTree as ET
import customtkinter as ctk

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# === GLOBAL VARIABLES ===
# ==========================================
STOP_EVENTS = {}
SAFE_TAGS_DB = []
MASTER_FOLDER = os.path.join(os.getcwd(), "Rem God")
HISTORY_LOCK = threading.Lock()

STARTUP_CONFIG = {
    "use_proxy": False,
    "proxy_url": "http://127.0.0.1:10808",
    "verify_tls": False
}

# ==========================================
# === JSON HISTORY MANAGEMENT ===
# ==========================================
def load_history(site_root):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        if os.path.exists(hist_path):
            try:
                with open(hist_path, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

def save_history(site_root, history_set):
    hist_path = os.path.join(site_root, "download_history.json")
    with HISTORY_LOCK:
        try:
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(list(history_set), f, indent=4)
        except Exception as e:
            print(f"Error saving history: {e}")

# ==========================================
# === 1. STARTUP CONFIG WINDOW ===
# ==========================================
def load_startup_fonts():
    base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    font_dir = os.path.join(base_dir, "web", "Fonts")
    playfair = os.path.join(font_dir, "Playfair-VariableFont_wdth,opsz.ttf")
    if os.path.exists(playfair):
        ctk.FontManager.load_font(playfair)

class StartupConfigWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("❄️ Rem Catcher - Pre-Flight Check")
        self.geometry("420x280")
        self.eval('tk::PlaceWindow . center')
        
        self.C_CYAN = "#00d2d3"
        self.C_PINK = "#ff9ff3"
        self.UI_FONT = ("Playfair", 14)
        self.launched = False

        ctk.CTkLabel(self, text="NETWORK SETUP", text_color=self.C_CYAN, font=("Playfair", 18, "bold")).pack(pady=(15, 5))
        ctk.CTkLabel(self, text="Configure this BEFORE connecting to any APIs.", text_color="gray", font=self.UI_FONT).pack(pady=(0, 15))

        self.var_proxy = ctk.BooleanVar(value=False)
        self.chk_proxy = ctk.CTkCheckBox(self, text="Enable Proxy (e.g. v2rayN)", variable=self.var_proxy, fg_color=self.C_CYAN, font=self.UI_FONT)
        self.chk_proxy.pack(pady=5)

        self.ent_proxy = ctk.CTkEntry(self, width=250, font=self.UI_FONT)
        self.ent_proxy.insert(0, "http://127.0.0.1:10808")
        self.ent_proxy.pack(pady=5)

        self.var_tls = ctk.BooleanVar(value=False)
        self.chk_tls = ctk.CTkCheckBox(self, text="Verify TLS/SSL", variable=self.var_tls, fg_color=self.C_CYAN, font=self.UI_FONT)
        self.chk_tls.pack(pady=5)

        self.btn_launch = ctk.CTkButton(self, text="Launch Rem Catcher", fg_color=self.C_PINK, hover_color="#f368e0", text_color="black", font=self.UI_FONT, command=self.on_launch)
        self.btn_launch.pack(pady=20)

    def on_launch(self):
        global STARTUP_CONFIG
        STARTUP_CONFIG["use_proxy"] = self.var_proxy.get()
        STARTUP_CONFIG["proxy_url"] = self.ent_proxy.get()
        STARTUP_CONFIG["verify_tls"] = self.var_tls.get()
        self.launched = True
        self.destroy() 

# ==========================================
# === 2. MAIN ENGINE (EEL) ===
# ==========================================
def load_safe_db():
    global SAFE_TAGS_DB
    base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "safe_tag_names.json")
    if not os.path.exists(db_path): db_path = os.path.join(base_dir, "tag_names.json")
        
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f: SAFE_TAGS_DB = json.load(f)
            print(f"[SYSTEM] Loaded {len(SAFE_TAGS_DB)} offline tags for Safebooru.")
        except Exception as e: print(f"[SYSTEM] Error parsing JSON: {e}")

def log_msg(worker_name, msg):
    try: eel.pythonLog(worker_name, msg)
    except: print(f"[{worker_name.upper()}] {msg}")

def get_session(site, net_config):
    session = requests.Session()
    if net_config.get("use_proxy"):
        p = net_config.get("proxy_url")
        session.proxies = {"http": p, "https": p}
    else:
        session.proxies = {"http": "", "https": "", "no_proxy": "*"}
        
    session.verify = net_config.get("verify_tls", False)

    if site == "safe":
        session.headers.update({"User-Agent": "RemGodCatcher/2.0", "Accept": "application/json"})
    elif site == "zero":
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/json,*/*"})
        retry_strategy = Retry(total=3, backoff_factor=2.0, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    elif site in ["waifu", "neko"]:
        session.headers.update({"Accept": "application/json"})
    return session

@eel.expose
def get_startup_config(): return STARTUP_CONFIG

@eel.expose
def get_current_folder(): return MASTER_FOLDER

@eel.expose
def choose_folder_py():
    global MASTER_FOLDER
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    folder = filedialog.askdirectory(title="Choose Master Download Folder")
    root.destroy()
    if folder:
        MASTER_FOLDER = os.path.join(folder, "Rem God")
        return MASTER_FOLDER
    return None

# ==========================================
# === BACKGROUND TAG FETCHING ===
# ==========================================
@eel.expose
def get_waifu_tags(net_config):
    try:
        session = get_session("waifu", net_config)
        resp = session.get("https://api.waifu.im/tags", timeout=10)
        data = resp.json()
        tags = [t.get("name", t.get("slug")) for t in data.get("items", [])] if "items" in data else data.get("versatile", []) + data.get("nsfw", [])
        return sorted(list(set([t for t in tags if t])))
    except Exception as e:
        return sorted(['maid', 'waifu', 'marin-kitagawa', 'mori-calliope', 'raiden-shogun', 'oppai', 'selfies', 'uniform', 'kamisato-ayaka', 'ero', 'ass', 'hentai', 'milf', 'oral', 'paizuri', 'ecchi'])

@eel.expose
def get_neko_tags(net_config):
    try:
        session = get_session("neko", net_config)
        resp = session.get("https://nekos.best/api/v2/endpoints", timeout=8)
        resp.raise_for_status()
        data = resp.json()
        images = sorted([cat for cat, d in data.items() if d.get("format") == "png"])
        gifs = sorted([cat for cat, d in data.items() if d.get("format") == "gif"])
        return {"image": images, "gif": gifs}
    except Exception as e:
        return {"image": [], "gif": []}

@eel.expose
def get_zerochan_suggestions(query, net_config):
    try:
        session = get_session("zero", net_config)
        session.headers.update({"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.zerochan.net/"})
        resp = session.get(f"https://www.zerochan.net/suggest?q={urllib.parse.quote_plus(query)}", timeout=5)
        if resp.status_code == 200:
            sugs = resp.json() if "{" in resp.text or "[" in resp.text else [s.strip() for s in resp.text.split('\n') if s.strip()]
            return list(dict.fromkeys([s.split('|')[0].strip() for s in sugs]))
    except: pass
    return []

@eel.expose
def get_safe_suggestions(query):
    query = query.lower()
    if not SAFE_TAGS_DB: return []
    return [t for t in SAFE_TAGS_DB if t.startswith(query)][:50]

@eel.expose
def get_rule34_suggestions(query, net_config):
    if len(query) < 2: return []
    try:
        session = get_session("rule34", net_config)
        url = f"https://api.rule34.xxx/autocomplete.php?q={urllib.parse.quote(query)}"
        resp = session.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return [item.get("value") for item in data if isinstance(item, dict) and "value" in item]
    except: pass
    
    try:
        session = get_session("rule34", net_config)
        url = f"https://gelbooru.com/index.php?page=autocomplete2&term={urllib.parse.quote(query)}&type=tag_query&limit=20"
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [item.get("value") for item in data if isinstance(item, dict) and "value" in item]
    except: pass
    return []

# ==========================================
# === WORKER CONTROLS ===
# ==========================================
@eel.expose
def stop_worker(name):
    log_msg(name, ">>> STOP SIGNAL RECEIVED! Terminating connections immediately... <<<")
    if name in STOP_EVENTS: STOP_EVENTS[name].set()

@eel.expose
def start_zerochan(tag, limit, net_config):
    limit = int(limit) if str(limit).strip().isdigit() else 0
    threading.Thread(target=worker_zerochan, args=(tag, limit, net_config), daemon=True).start()

@eel.expose
def start_waifu(tag, limit, is_nsfw, net_config):
    limit = int(limit) if str(limit).strip().isdigit() else 0
    threading.Thread(target=worker_waifu, args=(tag, limit, is_nsfw, net_config), daemon=True).start()

@eel.expose
def start_neko(category, limit, net_config):
    limit = int(limit) if str(limit).strip().isdigit() else 0
    threading.Thread(target=worker_nekos_best, args=(category, limit, net_config), daemon=True).start()

@eel.expose
def start_safe(tag, limit, net_config):
    limit = int(limit) if str(limit).strip().isdigit() else 0
    threading.Thread(target=worker_safebooru, args=(tag, limit, net_config), daemon=True).start()

@eel.expose
def start_rule34(tag, limit, method, sort_type, sort_order, exclusions, net_config):
    limit = int(limit) if str(limit).strip().isdigit() else 0
    threading.Thread(target=worker_rule34, args=(tag, limit, method, sort_type, sort_order, exclusions, net_config), daemon=True).start()

# ==========================================
# === WORKER FUNCTIONS ===
# ==========================================

# ----------------- RULE34 WORKER (RULE34PY LIBRARY REBORN) -----------------
def worker_rule34(tag, amount, method, sort_type, sort_order, exclusions, net_config):
    name = "rule34"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]

    log_msg(name, f"Initializing worker... [RULE34PY LIBRARY MODE]")
    
    # ۱. مرتب کردن تگ‌ها بدون هیچ کوتیشنِ اضافی
    tag_list = [t.strip() for t in tag.strip().lower().split() if t.strip()]
    
    if len(tag_list) > 10:
        log_msg(name, "⚠️ Warning: Max 10 tags allowed! Truncating your list...")
        tag_list = tag_list[:10]

    # ۲. پیاده‌سازی منطق AND / OR (فیکس شده دقیقاً مطابق اسکریپت اصلی تو)
    TAGS = []
    if method == "or":
        if any(t.startswith('-') for t in tag_list):
            log_msg(name, "❌ Error: Cannot use negative (-tag) in OR method.")
            log_msg(name, "⚙️ Auto-switching to AND method...")
            TAGS.extend(tag_list)
        else:
            # 🚨 فیکس بزرگ: ترکیب تگ‌ها با علامت ~ در یک استرینگ واحد 🚨
            TAGS.append(" ~ ".join(tag_list))
    else:
        TAGS.extend(tag_list)

    # ۳. اضافه کردن سورت و فیلترهای استثنا (باگ desc رفع شده)
    if sort_order == "desc":
        TAGS.append(f"sort:{sort_type}")
    else:
        TAGS.append(f"sort:{sort_type}:{sort_order}")
        
    if exclusions:
        TAGS.extend(exclusions)

    log_msg(name, f"🔍 Final Payload sent to rule34Py: {TAGS}")

    site_root = os.path.join(MASTER_FOLDER, "Rule34")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)
    
    clean_folder_name = " ".join([t for t in tag_list if not t.startswith('-')])
    safe_tag_dir = re.sub(r'[\\/*?:"<>|~]', "", clean_folder_name).strip().replace(' ', '_')
    if not safe_tag_dir: safe_tag_dir = "mixed_tags"
    
    tag_dir = os.path.join(site_root, safe_tag_dir)
    os.makedirs(tag_dir, exist_ok=True)

    try:
        from rule34Py import rule34Py
        client = rule34Py()
        
        # ====================================================
        # 🔑 RULE34 ACCOUNT LOGIN
        # ====================================================
        client.api_key = "69c74ebb1438ba4c11bb32ee8be892af9366800ce90a4ea3892b857f0dd9c77de5c16880a94d51ed56db6dc4cf792cd93b2ef27f4b4da74fcecf079e672b4507"
        client.user_id = 6407946
        
        downloaded = 0
        page = 0
        
        while not stop_event.is_set() and (amount == 0 or downloaded < amount):
            log_msg(name, f"📡 Scanning via rule34Py... (Page {page})")
            
            chunk_limit = min(1000, amount - downloaded if amount > 0 else 100)
            
            # حلقه سماجت برای کندی اینترنت (Retry Loop)
            results = None
            max_retries = 5
            
            for attempt in range(max_retries):
                try:
                    results = client.search(TAGS, page_id=page, limit=chunk_limit)
                    break
                except TypeError as e:
                    if "string indices must be integers" in str(e):
                        results = [] # صفر نتیجه تلقی می‌شود
                        break
                    else:
                        raise e
                except Exception as e:
                    error_msg = str(e)
                    if "timeout" in error_msg.lower() or "read timed out" in error_msg.lower():
                        log_msg(name, f"⚠️ Network Timeout (Attempt {attempt+1}/{max_retries}). Retrying in 3s...")
                        time.sleep(3)
                    else:
                        raise e
                        
            if results is None:
                log_msg(name, "❌ Failed to connect to Rule34 after 5 attempts. Check your VPN/Proxy.")
                break
            
            if not results:
                if page == 0:
                    log_msg(name, f"❌ 0 images found for {TAGS}.")
                else:
                    log_msg(name, "🛑 End of database reached.")
                break

            for result in results:
                if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
                
                file_url = result.image
                if not file_url: continue
                
                ext = file_url.split('.')[-1].lower()
                
                if ext in ["mp4", "webm", "zip"] and "-video" in exclusions: continue
                if ext == "gif" and "-gif" in exclusions: continue

                post_id = getattr(result, 'id', random.randint(1000,99999))
                filename = f"{post_id}.{ext}"
                filepath = os.path.join(tag_dir, filename)
                
                if filename in dl_history or os.path.exists(filepath): 
                    log_msg(name, f"[SKIP] {filename} (Already in history/disk)")
                    continue

                try:
                    resp = requests.get(file_url, stream=True, timeout=30)
                    resp.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            if stop_event.is_set(): break
                            f.write(chunk)
                    
                    if stop_event.is_set():
                        os.remove(filepath)
                        break
                        
                    downloaded += 1
                    dl_history.add(filename)
                    save_history(site_root, dl_history)
                    
                    log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                    time.sleep(random.uniform(0.6, 1.2))
                except Exception as e: 
                    log_msg(name, f"[FAILED] {filename}: {e}")

            page += 1
            if not stop_event.is_set() and (amount == 0 or downloaded < amount):
                delay = random.uniform(3.0, 5.0)
                log_msg(name, f"🕵️ Tactical pause... ({delay:.1f}s)")
                time.sleep(delay)

    except Exception as e:
        log_msg(name, f"❌ Unexpected Error: {str(e)}")
            
    log_msg(name, "--- Worker Terminated ---")


# ----------------- SAFEBOORU WORKER -----------------
def worker_safebooru(tag, amount, net_config):
    name = "safe"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]

    tag = tag.strip().lower()
    log_msg(name, f"Initializing worker for tag: '{tag}'")
    
    site_root = os.path.join(MASTER_FOLDER, "Safebooru")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)
    session = get_session("safe", net_config)

    safe_tag = re.sub(r'[\\/*?:"<>|]', "", tag).replace(' ', '_')
    tag_dir = os.path.join(site_root, safe_tag)
    os.makedirs(tag_dir, exist_ok=True)

    downloaded = 0; page = 1
    while not stop_event.is_set() and (amount == 0 or downloaded < amount):
        try:
            log_msg(name, f"📡 Scanning API... (Page {page})")
            limit_val = min(100, amount - downloaded if amount > 0 else 100)
            
            resp = session.get("https://safebooru.donmai.us/posts.json", params={"tags": tag, "page": page, "limit": limit_val}, timeout=15)
            if resp.status_code in [403, 429]: 
                log_msg(name, f"❌ ERROR {resp.status_code}. Change proxy.")
                break
            resp.raise_for_status()
            
            text_resp = resp.text.strip()
            if not text_resp or text_resp == "[]":
                if page == 1: log_msg(name, f"❌ ZERO images found for '{tag}'.")
                break
                
            raw_data = resp.json()
            if isinstance(raw_data, dict):
                if "success" in raw_data and not raw_data["success"]:
                    log_msg(name, f"❌ API Alert: {raw_data.get('message', 'Unknown Error')}")
                    break
                posts = [raw_data] 
            elif isinstance(raw_data, list):
                posts = raw_data
            else: 
                break
                
            if not posts: break
            
        except Exception as e: 
            log_msg(name, f"❌ API Error: {e}"); time.sleep(5); continue

        for post in posts:
            if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
            if not isinstance(post, dict): continue
            
            url = post.get("file_url") or post.get("large_file_url")
            if not url: continue
            if url.startswith("https://"): url = url.replace("https://", "http://")
            
            ext = (post.get("file_ext") or "").lower()
            if ext in ["mp4", "webm", "zip", "gif"]: continue

            filename = f"{post.get('id')}.{ext}"
            filepath = os.path.join(tag_dir, filename)
            
            if filename in dl_history or os.path.exists(filepath): 
                continue

            try:
                r = session.get(url, stream=True, timeout=20)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break
                    
                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                time.sleep(random.uniform(0.5, 2.0))
            except Exception as e: log_msg(name, f"[FAILED] {filename}: {e}")

        page += 1
        if not stop_event.is_set() and (amount == 0 or downloaded < amount):
            delay = random.uniform(3.0, 5.0)
            log_msg(name, f"🕵️ Anti-ban pause... ({delay:.1f}s)")
            time.sleep(delay)
            
    log_msg(name, "--- Worker Terminated ---")

# ----------------- ZEROCHAN WORKER -----------------
def worker_zerochan(tag, amount, net_config):
    name = "zero"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]
    
    tag = tag.split('|')[0].strip()
    log_msg(name, f"Initializing worker for tag: '{tag}'")
    session = get_session("zero", net_config)

    site_root = os.path.join(MASTER_FOLDER, "Zerochan")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)

    try:
        r_resp = session.get(f"https://www.zerochan.net/{urllib.parse.quote_plus(tag)}", timeout=10, allow_redirects=True)
        if r_resp.url and "/search?q=" not in r_resp.url:
            real_tag = urllib.parse.unquote(r_resp.url.split('/')[-1]).replace('+', ' ')
            if real_tag and real_tag.lower() != tag.lower(): tag = real_tag
    except: pass 

    safe_tag = re.sub(r'[\\/*?:"<>|]', "", tag).replace(' ', '_')
    tag_dir = os.path.join(site_root, safe_tag)
    os.makedirs(tag_dir, exist_ok=True)
    encoded_tag = urllib.parse.quote_plus(tag)

    downloaded = 0; page = 1
    while not stop_event.is_set() and (amount == 0 or downloaded < amount):
        try:
            log_msg(name, f"📡 Scanning API... (Page {page})")
            resp = session.get(f"https://www.zerochan.net/{encoded_tag}?json", params={"p": page, "l": 48}, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items: 
                log_msg(name, f"🛑 End of database reached.")
                break
        except Exception as e: log_msg(name, f"Network/Limit: {e}"); break

        for item in items:
            if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
            try:
                det_resp = session.get(f"https://www.zerochan.net/{item.get('id')}?json", timeout=10)
                img_url = det_resp.json().get("full") or det_resp.json().get("large")
            except: continue 
            if not img_url: continue

            filename = img_url.split('/')[-1]
            filepath = os.path.join(tag_dir, filename)
            
            if filename in dl_history or os.path.exists(filepath): 
                continue

            try:
                r = session.get(img_url, stream=True, timeout=20)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set(): 
                    os.remove(filepath)
                    break
                
                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                time.sleep(random.uniform(0.3, 1.2))
            except Exception as e: log_msg(name, f"[FAILED] {filename}")

        page += 1
        if not stop_event.is_set() and (amount == 0 or downloaded < amount):
            delay = random.uniform(3.0, 6.0)
            log_msg(name, f"🕵️ Stealth delay... ({delay:.1f}s)")
            time.sleep(delay)
            
    log_msg(name, "--- Worker Terminated ---")

# ----------------- WAIFU WORKER -----------------
def worker_waifu(tag, amount, is_nsfw, net_config):
    name = "waifu"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]

    tag = tag.lower()
    log_msg(name, f"Initializing worker for tag: '{tag}' (NSFW: {is_nsfw})")
    
    site_root = os.path.join(MASTER_FOLDER, "Waifu.im")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)

    safe_tag = re.sub(r'[\\/*?:"<>|]', "", tag).replace(' ', '_')
    tag_dir = os.path.join(site_root, "nsfw_" + safe_tag if is_nsfw else safe_tag)
    os.makedirs(tag_dir, exist_ok=True)
    session = get_session("waifu", net_config)

    downloaded = 0
    while not stop_event.is_set() and (amount == 0 or downloaded < amount):
        params = {"IncludedTags": tag}
        if is_nsfw: params["IsNsfw"] = "True"

        try:
            log_msg(name, f"📡 Scanning API...")
            resp = session.get("https://api.waifu.im/images", params=params, timeout=10)
            if resp.status_code == 404: log_msg(name, f"❌ ERROR 404: Tag not found!"); break
            elif resp.status_code == 403: log_msg(name, "❌ ERROR 403: Adult tag detected. Check NSFW box."); break
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items: 
                log_msg(name, f"🛑 End of database reached.")
                break
        except Exception as e: log_msg(name, f"API Error: {e}"); time.sleep(5); continue

        for img in items:
            if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
            url = img.get("url")
            if not url: continue
            
            filename = url.split('/')[-1]
            filepath = os.path.join(tag_dir, filename)
            
            if filename in dl_history or os.path.exists(filepath): 
                continue

            try:
                r = session.get(url, stream=True, timeout=15)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break
                
                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                time.sleep(random.uniform(0.6, 1.0)) 
            except Exception as e: log_msg(name, f"[FAILED] {filename}: {e}")

        if not stop_event.is_set() and (amount == 0 or downloaded < amount):
            delay = random.uniform(0.6, 1.0)
            log_msg(name, f"🕵️ Resting... ({delay:.1f}s)")
            time.sleep(delay)

    log_msg(name, "--- Worker Terminated ---")

# ----------------- NEKO WORKER -----------------
def worker_nekos_best(category, amount, net_config):
    name = "neko"
    STOP_EVENTS[name] = threading.Event()
    stop_event = STOP_EVENTS[name]

    log_msg(name, f"Initializing worker for category: '{category}'")
    
    site_root = os.path.join(MASTER_FOLDER, "Nekos.best")
    os.makedirs(site_root, exist_ok=True)
    dl_history = load_history(site_root)

    cat_dir = os.path.join(site_root, category)
    os.makedirs(cat_dir, exist_ok=True)
    session = get_session("neko", net_config)

    downloaded = 0
    while not stop_event.is_set() and (amount == 0 or downloaded < amount):
        fetch_url = f"https://nekos.best/api/v2/{category}?amount={min(20, amount - downloaded if amount > 0 else 20)}"
        try:
            log_msg(name, f"📡 Scanning API...")
            resp = session.get(fetch_url, timeout=10)
            if resp.status_code in [403, 429]: log_msg(name, f"❌ API BAN ({resp.status_code}). Change VPN node."); break
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                log_msg(name, f"🛑 End of database reached.")
                break
        except Exception as e: log_msg(name, f"Network delay, retrying... ({e})"); time.sleep(5); continue

        for item in results:
            if stop_event.is_set() or (amount > 0 and downloaded >= amount): break
            url = item.get("url")
            if not url: continue
            
            filename = url.split('/')[-1]
            filepath = os.path.join(cat_dir, filename)
            
            if filename in dl_history or os.path.exists(filepath): 
                continue

            try:
                r = session.get(url, stream=True, timeout=15)
                r.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if stop_event.is_set(): break
                        f.write(chunk)
                if stop_event.is_set():
                    os.remove(filepath)
                    break
                
                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)
                
                log_msg(name, f"[SUCCESS] Downloaded {filename} ({downloaded}/{amount})")
                time.sleep(random.uniform(0.3, 1.2))
            except Exception as e: log_msg(name, f"[FAILED] {filename}: {e}")
        
        if not stop_event.is_set() and (amount == 0 or downloaded < amount):
            delay = random.uniform(3.5, 6.5)
            log_msg(name, f"🕵️ Tactical pause... ({delay:.1f}s)")
            time.sleep(delay)
            
    log_msg(name, "--- Worker Terminated ---")


if __name__ == "__main__":
    load_startup_fonts()
    startup_app = StartupConfigWindow()
    startup_app.mainloop()
    
    if startup_app.launched:
        load_safe_db()
        base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        web_dir = os.path.join(base_dir, 'web')
        
        if not os.path.exists(web_dir) or not os.path.exists(os.path.join(web_dir, 'index.html')):
            print("❌ ERROR: 'web' folder not found!")
            time.sleep(10)
            sys.exit()

        eel.init(web_dir)
        print("Starting Rem God Catcher Web UI...")
        try:
            eel.start('index.html', size=(950, 750), port=0)
        except (SystemExit, MemoryError, KeyboardInterrupt):
            print("Application Closed.")