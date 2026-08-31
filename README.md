<div align="center">

# Rem God Catcher 5.1

**A massive multi-threaded image & media scraping application with a beautiful glass-morphism web UI.**

Supports Rule34, Safebooru, Gelbooru, Zerochan, Waifu.im, Nekos.best, Nekos.life, Yande.re, Konachan, Danbooru, e-shuushuu, NekosAPI, Nekosia, and Pinterest.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://python.org)
[![Version](https://img.shields.io/badge/Version-5.1.0-ff9ff3.svg)](CHANGELOG.md)

[English](README.md) | [فارسی](README_fa.md)

</div>

---

## ✨ New in Version 5.1
- **Zerochan Categorized Tags:** HTML tag parser extracts categories (mangaka, character, game, theme, source, vtuber, outfit, series, etc.) with color-coded badges.
- **Rating System Fix:** All workers now properly tag ratings (`rating:g`, `rating:s`, `rating:q`, `rating:e`) for gallery filtering. Nekosapi, Nekosia, and Waifu.im added to rating filters.
- **Zerochan Pagination:** Page-by-page gallery-dl enumeration — stops as soon as enough non-duplicate posts are found.
- **Gallery-dl Patch:** Modified extractor included in `gallery_dl_patch/` for categorized tag parsing.
- **GSBooru Rewrite:** Full tag caching and categorization for Gelbooru.

## ✨ Previous (5.0)
- **Beautiful Auto-Suggest:** Fully restyled interactive tag suggestions for ALL workers with keyboard support.
- **Immersive Gallery:** "Focus Mode" for pure image viewing, instant next-image on delete.
- **New Platforms:** Nekosia, NekosAPI, and e-shuushuu added to the fleet.
- **Anti-Ban Magic:** AnimePictures.net completely bypassed using `curl_cffi` TLS impersonation.

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/RemLover-Dev/RemGodCatcher.git
cd RemGodCatcher
```

### 2. Install Dependencies

```bash
pip install flask flask-socketio requests urllib3 python-dotenv rule34Py
```

### 3. Install gallery-dl Patch (Required for Zerochan)

The Zerochan worker uses a modified gallery-dl extractor for categorized tag parsing. Install it after gallery-dl:

```bash
pip install gallery-dl
bash gallery_dl_patch/install.sh
```

### 4. Configure (Optional)

Edit `.env` or use the **Options** tab in the Web UI:

```env
RULE34_API_KEY=your_api_key_here
RULE34_USER_ID=your_user_id_here
USE_PROXY=false
PROXY_URL=http://127.0.0.1:10808
VERIFY_TLS=false
API_TIMEOUT=10
RETRY_WAIT=5
ANTI_BAN_PAUSE=3.0
```

### 4. Run

```bash
python Rem_catcher.py
```

The Web UI opens automatically at `http://127.0.0.1:5000`.

---


## 🔑 How to get API Keys / Credentials (Step-by-Step)

Entering credentials in the **Settings** tab unlocks higher API limits and restricted content.

**1. Rule34.xxx**
* Go to [Rule34.xxx](https://rule34.xxx) and Log in.
* Click **My Account** -> **Settings**.
* Scroll down to **API Key** and click **Generate**. Copy this key.
* Click on your username to go to your profile. Check the URL for `id=XXXXXX`. That number is your **User ID**.

**2. Gelbooru**
* Go to [Gelbooru.com](https://gelbooru.com) and Log in.
* Click **My Account** -> **Options**.
* Under **Miscellaneous Options**, find **API Key** and click **Generate API Key**.
* Go back to your account page, find the URL (e.g. `&uid=123456`). That number is your **User ID**.

**3. Sankaku Complex**
* Simply use your standard Sankaku **Username/Email** and **Password** in the UI.

**4. Zerochan**
* Some images are restricted to guests. Use your standard Zerochan **Username** and **Password** in the UI to let the `gallery-dl` engine fetch everything.

**5. Pinterest**
* Standard method: Enter your Pinterest **Email** and **Password**.
* Alternative (If blocked): Use a browser extension (like *EditThisCookie*) to export your Pinterest cookies as a `.json` file. Provide the absolute file path in the `Cookies` field.

---

## Features

- **Multi-Platform** -- Built-in modules for 14 imageboard APIs
- **Modern Web UI** -- Glass-morphism dark & light themes, opens in your default browser
- **Discovery Engine & Archives** -- Live extraction of tags and artists from downloaded media, displayed in a dedicated Image Archive tab.
- **Favorites & Search History** -- Add tags to your favorites list for one-click search automation, and maintain a log of your search history.
- **Video & GIF Support** -- Exclusively target `.mp4`, `.webm`, or GIF files via format filtering.
- **GIFs Only Filter** -- Rule34 supports a dedicated GIFs Only mode alongside Images/Videos/All.
- **Real-Time Logs** -- Live console output via WebSocket (Socket.IO) with per-tab clear button
- **Full UI Customization** -- Custom colors for text, accents, buttons, and tab backgrounds; per-tab wallpapers with dark/light mode
- **Advanced Search** -- AND/OR tag queries, exclusions (`-video`, `-image`), custom sorting, category-based browsing
- **Rating Filtering** -- Filter gallery by Safe/Sensitive/Questionable/NSFW across all platforms with proper rating tags
- **Categorized Tags** -- Zerochan tags parsed into 10+ categories (mangaka, character, game, theme, source, vtuber, outfit, series, group, studio) with color-coded badges
- **Anti-Ban Engine** -- Tactical delays, retry loops, rate-limit handling
- **Proxy Support** -- Full proxy configuration from the UI (v2rayN, Clash, etc.)
- **API Key Management** -- Manage Rule34 credentials directly from the Web UI
- **Tag Auto-Suggest** -- Live autocomplete for all platforms including offline Konachan tag DB
- **Hydrus Sidecar Files** -- Auto-generates `.filename.txt` sidecar files with tags, artists, and source for Hydrus Network import
- **Persistent Settings** -- Proxy, API keys, and download settings saved in `.env`


## Project Structure

```
Rem God Catcher/
├── Rem_catcher.py          # Python backend (Flask + Socket.IO)
├── shared.py               # Core utilities, tag handler, and logging bridge
├── workers/                # API-specific download modules
├── gallery_dl_patch/       # Modified gallery-dl extractor for Zerochan
│   ├── zerochan.py             # Patched extractor with page_html support
│   └── install.sh              # Auto-installer script
├── tags.json               # Waifu.im tag database (name -> slug mapping)
├── database/               # Tag databases & user data
│   ├── dan_tag_names.json      # Danbooru offline tag database
│   ├── safe_tag_names.json     # Safebooru offline tag database
│   ├── yande_tag_names.json    # Yande.re offline tag database
│   ├── kona_tag_names.json     # Konachan offline tag database (82k+ tags)
│   ├── tag_caches/             # Per-site tag type caches
│   ├── tag_history.json        # Search history database (git-ignored)
│   ├── fav_tags.json           # User favorites database (git-ignored)
│   ├── image_history.json      # Per-image tag archive (git-ignored)
│   └── ui_config.json          # Theme & wallpaper config (git-ignored)
├── .env                    # API keys & proxy config (git-ignored)
├── .gitignore
├── LICENSE
├── README.md
├── README_fa.md            # Persian documentation
├── CHANGELOG.md
└── web/
    ├── index.html           # Main HTML (tabs, forms, archives, settings)
    ├── script.js            # Frontend logic (Socket.IO + fetch API)
    ├── style.css            # Glass-morphism dark theme (Inter font)
    ├── Fonts/               # Offline fonts (Playfair, MonoLisa)
    └── wallpaper/           # Background images per tab (dark/light mode)
```

## Supported Platforms

| Platform | Tags | Ratings | Notes |
|----------|------|---------|-------|
| **Rule34** | AND/OR queries, exclusions, sorting, video format support | NSFW | Requires API key for best results |
| **Safebooru** | Standard tag search, artist extraction, tag categorization | Safe | May require proxy (Cloudflare) |
| **Gelbooru** | Full search, format exclusions, video/GIF support, artist extraction | All 4 | Uses Danbooru-style rating system |
| **Danbooru** | Full tag search, artist extraction, offline tag DB, video/image separation | All 4 | Sorts into Safe/Sensitive/Questionable/NSFW folders |
| **Zerochan** | HTML tag parser with 10+ categories (mangaka, character, theme, vtuber, etc.) | None | Uses patched gallery-dl, page-by-page enumeration |
| **Waifu.im** | Name-to-slug conversion, NSFW toggle | Safe/NSFW | Uses local `tags.json` for suggestions |
| **Nekos.best** | Category-based (PNG / GIF) | None | Multiple format support |
| **Nekos.life** | Category-based with type indicators (GIF/Static/Mixed) | None | Animated neko, hug, pat, cuddle, and more |
| **Yande.re** | Full tag search, artist extraction, local tag DB | Safe/Questionable/NSFW | Moebooru API, images only |
| **Konachan** | Full tag search, artist extraction, local tag DB, video/GIF format filtering | Safe/Questionable/NSFW | Moebooru API |
| **NekosAPI** | Tag search, artist extraction | All 4 | REST API with rating filter |
| **Nekosia** | Tag search, artist extraction | Safe/Sensitive | REST API |
| **e-shuushuu** | Tag search | None | XML API |
| **Pinterest** | Board-based scraping | None | Requires cookies for auth |

---

## Disclaimer

This software is provided for **educational and archiving purposes only**. Some supported APIs index NSFW content -- users must be of legal age in their jurisdiction. Please respect API rate limits and do not aggressively spam requests.

---

## License

[MIT License](LICENSE)
