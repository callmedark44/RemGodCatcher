<div align="center">

# Rem God Catcher

**A modern, cross-platform image & video downloader with a glass-morphism web UI.**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-yellow.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://flask.palletsprojects.com)
[![Version](https://img.shields.io/badge/Version-4.2.0-ff9ff3.svg)](CHANGELOG.md)

<video controls width="720" src="assets/demo.mp4" alt="Demo">
  Your browser does not support the video tag. <a href="assets/demo.mp4">Download the demo</a>.
</video>

> **Drop `assets/demo.mp4` and `assets/demo-poster.png` in the repo root to replace the placeholder above.**

</div>

---

## Features

- **Multi-Platform** — Built-in modules for 15 imageboard and gallery APIs (Rule34, Gelbooru, Danbooru, Yande.re, Konachan, Sankaku, Zerochan, Safebooru, Waifu.im, Nekos.best, Nekos.life, Nekosia, Pixiv, Pinterest, Anime-Pictures)
- **Modern Web UI** — Glass-morphism dark & light themes, opens in your default browser
- **Concurrent Downloads** — Run multiple tags and APIs simultaneously, each with independent progress
- **Discovery Engine & Archives** — Live extraction of tags and artists from downloaded media, displayed in a dedicated Image Archive tab.
- **Favorites & Search History** — Add tags to your favorites list for one-click search automation, and maintain a log of your search history.
- **Video & GIF Support** — Exclusively target `.mp4`, `.webm`, or GIF files via format filtering.
- **Ugoira-to-GIF** — Pixiv ugoira (animated illustrations) are automatically converted to GIF.
- **Real-Time Logs** — Live console output via WebSocket (Socket.IO) with per-tab clear button.
- **Full UI Customization** — Custom colors for text, accents, buttons, and tab backgrounds; per-tab wallpapers with dark/light mode.
- **Advanced Search** — AND/OR tag queries, exclusions (`-video`, `-image`), custom sorting, rating filters.
- **Anti-Ban Engine** — Tactical delays, retry loops, rate-limit handling.
|- **Proxy Support** — Per-worker proxy toggle in each worker tab. Set proxy URL in Options tab, enable per-worker.
- **Tag Auto-Suggest** — Live autocomplete for all platforms with offline tag databases.
- **Hydrus Sidecar Files** — Auto-generates `.filename.txt` sidecar files with tags, artists, and source for Hydrus Network import.
- **Pixiv OAuth** — Login via Pixiv email/password or refresh token, with fallback to browser-based code authorization.
- **Persistent Settings** — Proxy, API keys, and download settings saved in `.env`.

---

## Gallery

<details>
<summary><strong>Screenshots</strong> (click to expand)</summary>

| Dark Theme | Light Theme |
|---|---|
| ![Dark Theme](assets/screenshot-dark.png) | ![Light Theme](assets/screenshot-light.png) |
| **Downloads Tab** | **Gallery Tab** |
| ![Downloads](assets/screenshot-downloads.png) | ![Gallery](assets/screenshot-gallery.png) |

> Drop your screenshots as `assets/screenshot-*.png` in the repo root.

</details>

---

## Quick Start

```bash
git clone https://github.com/RemLover-Dev/RemGodCatcher.git
cd RemGodCatcher
pip install -r requirements.txt
python Rem_catcher.py
```

Opens at `http://127.0.0.1:5000`. Most features work immediately without configuration.

---

## Project Structure

```
Rem God Catcher/
├── Rem_catcher.py          # Flask + Socket.IO backend
├── shared.py               # Core utilities, BaseDownloader, gallery
├── workers/                # API-specific download modules (15 workers)
├── database/               # Tag databases & user data (git-ignored)
├── web/                    # Frontend (index.html, script.js, style.css)
├── assets/                 # Screenshots, demos, media
├── README.html             # Rich HTML readme (supports video/GIF)
├── requirements.txt        # Python dependencies
├── .env.example            # Configuration template
├── CHANGELOG.md
├── README.md
└── LICENSE
```

---

## Supported Platforms

| Platform | Tags | NSFW | Auth | Notes |
|---|---|---|---|---|
| **Rule34** | AND/OR, exclusions, sorting | Yes | API key + User ID from account settings | Options tab |
|| **Safebooru** | Standard tag | No | None | May need proxy (Cloudflare) |
|| **Gelbooru** | Full search, exclusions | Yes | API Key + User ID from account | Options tab |
|| **Danbooru** | Full tag, rating filter | Yes | None | Offline tag DB |
|| **Yande.re** | Full tag, rating filter | Yes | None | Moebooru API |
|| **Konachan** | Full tag, rating filter | Yes | None | Video/GIF filter |
|| **Sankaku** | Full tag, rating, exclusions | Yes | Login email + password | Options tab (auto-login) |
|| **Zerochan** | Tag search with live suggestions | No | None | Built-in retry & rate limiting |
|| **Waifu.im** | Name-to-slug, NSFW toggle | Yes | None | Local `tags.json` |
|| **Nekos.best** | Category-based (PNG/GIF) | No | None | Simple endpoint |
|| **Nekos.life** | Category-based (GIF/Static) | Yes | None | Animated neko, hug, pat |
|| **Nekosia** | Tag search, exclusions | Suggestive | None | Async worker |
|| **Eshuushuu** | Tag name or numeric tag ID | Suggestive | None | Tag/user ID search fields |
|| **Pixiv** | Search, bookmark, ranking, user | Yes | OAuth2 refresh token | Options tab → "Get Token" button |
|| **Pinterest** | Search, board URL | Varies | Browser cookies OR email+password | Options tab |
|| **Anime-Pictures** | Tag search | No | None | Cookie bypass built in |

---

## Authentication Quick Reference

| Service | What to get | Where to enter |
|---|---|---|
| Rule34 | API Key + User ID from account settings | Options tab |
| Gelbooru | API Key + User ID from account options | Options tab |
| Sankaku | Login email + password (auto-login) | Options tab |
| Pinterest | Browser cookies (export from DevTools) or email + password | Options tab |
| Pixiv | OAuth2 refresh token — click "Get Token" to generate via browser | Options tab |

### Pixiv token setup
1. Enter your Pixiv email and password in the Options tab  
2. Click **"Get Token"** — the app opens a browser for OAuth2 authorization  
3. Approve the scopes, the refresh token is auto-saved to `.env` as `PIXIV_REFRESH_TOKEN`

---

## Download Folder Structure

```
Rem God/
├── Danbooru/tag_name/
│   ├── Safe/images/
│   ├── Sensitive/images/
│   ├── Questionable/images/
│   └── NSFW/images/
├── Pixiv/tag_name/General/images/
└── Pinterest/query_or_board/images/
```

---

## Disclaimer

For **educational and archiving purposes only**. Some APIs index NSFW content — users must be of legal age. Respect API rate limits.

---

## License

[MIT License](LICENSE)