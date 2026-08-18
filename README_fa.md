# Rem God Catcher 5.0

برنامه Rem God Catcher یک سیستم مدیریت دانلود و استخراج تصاویر از بهترین سایت‌های هنری انیمه است.

## ✨ قابلیت‌های جدید در نسخه 5.0
- **منوی پیشنهادات جذاب:** منوی سرچ و پیشنهاد تگ‌ها برای تمام ورکرها آپدیت شده و بسیار زیبا شده است.
- **رفع باگ AnimePictures:** با استفاده از curl_cffi سیستم ضد ربات سایت بای‌پس شد.
- **لاگین Zerochan:** حالا می‌توانید از قسمت تنظیمات، نام‌کاربری و رمز خود را وارد کنید تا به تصاویر پریمیوم دسترسی پیدا کنید.
- **سیستم خطایابی جدید:** از این به بعد اگر تعداد عکس‌های یک تگ کمتر از مقدار درخواستی شما باشد، برنامه به شما هشدار می‌دهد. همچنین اگر دانلودی خراب شود، تعداد دقیق خطاها در انتها نمایش داده می‌شود.

## سایت‌های پشتیبانی شده
* AnimePictures.net (Anime DL)
* Danbooru
* E-Shuushuu
* Gelbooru
* Konachan
* Nekos.best
* Nekos.life
* NekosAPI
* Nekosia
* Pinterest
* Rule34
* Safebooru
* Sankaku
* Waifu.im
* Yande.re
* Zerochan

## نصب و راه‌اندازی
ابتدا پیش‌نیازها را نصب کنید:
pip install flask flask-socketio requests python-dotenv pillow aiohttp curl_cffi rule34Py gallery-dl

سپس برنامه را اجرا کنید:
python Rem_catcher.py

