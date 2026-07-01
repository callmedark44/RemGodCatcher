۱. فایل shared.py (اضافه کردن پل ارتباطی تگ‌ها)
ابتدا باید یک تابع به هسته مشترک اضافه کنیم تا کارگرها بتوانند تگ‌ها را به سرور بفرستند.
این کد را به فایل shared.py، دقیقاً زیر تابع log_msg اضافه کن:

Python
# --- درون فایل shared.py، زیر تابع log_msg این را اضافه کن ---

def default_tag_handler(worker_name, tags_list):
    pass

tag_callback = default_tag_handler

def send_tags(worker_name, tags_list):
    tag_callback(worker_name, tags_list)
۲. فایل Rem_catcher.py (پردازش و ذخیره تگ‌ها در هیستوری)
در فایل اصلی سرور، باید تگ‌های دریافتی را پردازش کنیم، تکراری‌ها را حذف کنیم، در فایل JSON ذخیره کنیم و به رابط کاربری دستور آپدیت بدهیم.
این کد را پیدا کن:

Python
def socketio_logger(worker_name, msg):
    try:
        socketio.emit("python_log", {"worker": worker_name, "msg": msg})
    except Exception:
        print(f"[{worker_name.upper()}] {msg}")

shared.log_callback = socketio_logger
کد زیر را دقیقاً بعد از آن اضافه کن:

Python
def socketio_tag_handler(worker_name, tags_list):
    try:
        hist = load_json_db(TAG_HISTORY_FILE)
        # ساخت یک ست (Set) از تگ‌های موجود برای جلوگیری از تکرار
        existing = {(x["site"], x["tag"]) for x in hist}
        new_entries = []
        
        for t in tags_list:
            t = t.strip()
            if t and (worker_name, t) not in existing:
                new_entries.append({"site": worker_name, "tag": t})
                existing.add((worker_name, t))
        
        if new_entries:
            # تگ‌های جدید را به ابتدای لیست اضافه کن و لیست را به 500 عدد محدود کن
            hist = new_entries + hist
            hist = hist[:500] 
            save_json_db(TAG_HISTORY_FILE, hist)
            # به جاوااسکریپت دستور بده تب History را رفرش کند
            socketio.emit("update_history")
    except Exception as e:
        print("Tag Save Error:", e)

shared.tag_callback = socketio_tag_handler
۳. آپدیت کارگرها (حذف تگ از لاگ و ارسال به History)
در هر ۴ کارگر اصلی، تگ‌های طولانی را از لاگ پاک می‌کنیم و آن‌ها را به عنوان یک لیست به shared.py می‌فرستیم.

فایل workers/gelbooru.py:
حدود خطوط ۸۵، کدهای استخراج تگ و چاپ لاگ را به این شکل تغییر بده:

Python
            # --- تبدیل تگ‌ها به لیست ---
            tags_raw = post.get("tags", "")
            tags_list = [t.strip() for t in tags_raw.split() if t.strip()]

            ext = file_url.split('.')[-1].lower()
            
            # ... (کدهای فیلتر ویدیو و دانلود) ...
            
                downloaded += 1
                page_downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)

                # لاگ تمیز و ارسال تگ‌ها به هیستوری
                log_msg(name, f"[SUCCESS] {filename} ({downloaded}/{amount})")
                shared.send_tags(name, tags_list)
                time.sleep(random.uniform(0.5, 1.5))
فایل workers/safebooru.py:
حدود خطوط ۷۵، تغییرات مشابه اعمال شود:

Python
            # --- تبدیل تگ‌ها به لیست ---
            tags_raw = post.get("tags", "")
            tags_list = [t.strip() for t in tags_raw.split() if t.strip()]

            ext = (post.get("file_ext") or "").lower()
            
            # ... (کدهای فیلتر ویدیو و دانلود) ...
            
                downloaded += 1
                page_downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)

                # لاگ تمیز و ارسال تگ‌ها به هیستوری
                log_msg(name, f"[SUCCESS] {filename} ({downloaded}/{amount})")
                shared.send_tags(name, tags_list)
                time.sleep(random.uniform(0.5, 2.0))
فایل workers/rule34.py:
حدود خطوط ۱۱۸:

Python
                # --- استخراج و تبدیل تگ‌ها از Rule34Py ---
                tags_raw = getattr(result, 'tags', "")
                if isinstance(tags_raw, str): tags_list = [t.strip() for t in tags_raw.split() if t.strip()]
                else: tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
                
                ext = file_url.split('.')[-1].lower()
                
                # ... (کدهای فیلتر و دانلود) ...
                
                    downloaded += 1
                    dl_history.add(filename)
                    save_history(site_root, dl_history)

                    # لاگ تمیز و ارسال تگ‌ها
                    log_msg(name, f"[SUCCESS] {filename} ({downloaded}/{amount})")
                    shared.send_tags(name, tags_list)
                    time.sleep(random.uniform(0.6, 1.2))
فایل workers/zerochan.py:
در تابع دانلودِ Zerochan:

Python
            try:
                det_resp = session.get(f"https://www.zerochan.net/{item.get('id')}?json", timeout=10)
                json_data = det_resp.json()
                img_url = json_data.get("full") or json_data.get("large")
                
                # --- استخراج تگ‌ها ---
                tags_raw = json_data.get("tags", [])
                if isinstance(tags_raw, str): tags_list = [t.strip() for t in tags_raw.split(',') if t.strip()]
                else: tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
            except Exception: continue
            
            # ... (کدهای دانلود) ...
            
                downloaded += 1
                dl_history.add(filename)
                save_history(site_root, dl_history)

                # لاگ تمیز و ارسال
                log_msg(name, f"[SUCCESS] {filename} ({downloaded}/{amount})")
                shared.send_tags(name, tags_list)
                time.sleep(random.uniform(0.3, 1.2))
۴. فایل web/script.js (بروزرسانی زنده بدون پرش اسکرول)
در جاوااسکریپت دو کار انجام می‌دهیم: یکی گوش دادن به پیام update_history و دیگری حفظ کردن جایگاه اسکرول (Scroll Position) تا وقتی در حال اسکرول تب History هستی و تگ‌های جدید اضافه می‌شوند، صفحه به بالا نپرد!

۱. اضافه کردن Socket Listener:
در ابتدای فایل (حدود خط ۱۰)، زیر رویداد python_log این را اضافه کن:

JavaScript
socket.on("python_log", function (data) {
    logToConsole(data.worker, data.msg);
});

// این کد جدید را اضافه کن
socket.on("update_history", function () {
    loadTagsData(); // رفرش کردن تب هیستوری به صورت خودکار
});
۲. حفظ اسکرول در تابع renderHistory:
کد قبلی تابع renderHistory() (اواخر فایل) را به طور کامل پاک کن و این نسخه بهینه‌تر را جایگزین آن کن:

JavaScript
function renderHistory() {
    let ui = document.getElementById("historyListUI");
    if(!ui) return;
    
    // ذخیره موقعیت اسکرول فعلی برای جلوگیری از پرش تصویر
    let currentScroll = ui.parentElement.scrollTop;

    let htmlStr = "";
    if (historyTags.length === 0) {
        htmlStr = "<p style='color: gray; font-size: 13px;'>No search history yet.</p>";
    } else {
        historyTags.forEach(item => {
            let isFav = isFavorite(item.site, item.tag);
            let heartIcon = isFav ? "💖" : "🤍";
            
            htmlStr += `
                <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.5); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                    <div>
                        <span style="color: #ff9ff3; font-size: 11px; text-transform: uppercase; border: 1px solid #ff9ff3; padding: 2px 5px; border-radius: 4px; margin-right: 10px;">${item.site}</span>
                        <span style="font-size: 14px; color: white;">${item.tag}</span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="action-btn" style="padding: 4px 8px; font-size: 12px; background: transparent; border: 1px solid rgba(255,255,255,0.2);" onclick="toggleFavorite('${item.site}', '${item.tag}')">${heartIcon}</button>
                        <button class="action-btn stop-btn" style="padding: 4px 8px; font-size: 12px;" onclick="removeFromHistory('${item.site}', '${item.tag}')">❌</button>
                    </div>
                </div>
            `;
        });
    }
    
    ui.innerHTML = htmlStr;
    
    // بازگرداندن اسکرول به جایگاه قبلی
    ui.parentElement.scrollTop = currentScroll;
}
حالا برنامه‌ات دقیقاً همانطور که خواستی کار می‌کند. لاگ‌ها تمیز می‌مانند و به محض دانلود شدن هر عکس، تمام تگ‌های جالب آن عکس به لیست History اضافه می‌شوند. تو می‌توانی از بین صدها تگ اکتشافی اسکرول کنی و بهترین‌ها را قلب 💖 بدهی! لذت ببر برادر.