# Rem God Catcher 5.0

Rem God Catcher is a massive multi-threaded image and media scraping application. It is designed to flawlessly connect to various APIs (Rule34, Gelbooru, E-Shuushuu, Nekosia, Zerochan, etc.), download the content cleanly, and index it locally.

## ✨ New in Version 5.0
- **Beautiful Auto-Suggest Dropdowns:** Fully restyled interactive tag suggestions for ALL workers.
- **AnimePictures.net Fixed:** Completely bypassed TLS blocking using curl_cffi impersonation.
- **Zerochan Login Integration:** Unlock restricted Zerochan images by entering your login details in the Settings!
- **Error Tracking & Limit Warnings:** Rem God Catcher now tells you if a tag has fewer images than you asked for, and clearly displays if any images failed during the download process.

## Supported Sites
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

## Installation
1. Clone the repository
2. Create and activate a python virtual environment
3. Install dependencies: pip install flask flask-socketio requests python-dotenv pillow aiohttp curl_cffi rule34Py gallery-dl
4. Run: python Rem_catcher.py

