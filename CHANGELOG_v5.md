## Rem God Catcher 5.0 (Beta)

### 🌟 Major UI/UX Overhaul
- **New Dropdown Tag Auto-Suggestions:** The clunky HTML <datalist> has been completely ripped out and replaced with a gorgeous, dark-themed custom dropdown (.autosuggest-dropdown) for **all workers** (AnimeDL, Gelbooru, Safebooru, Danbooru, Konachan, E-Shuushuu, NekosAPI, Nekosia, etc). Features keyboard navigation and elegant styling.
- **Removed "Scanning API..." Bar:** Removed the redundant "Scanning API..." bar from the UI to make the interface much cleaner. Now, a single elegant "Downloading..." bar shows the actual progress.
- **Enhanced Download Completion Logs:** The UI now displays a beautiful end message showing how many images succeeded and how many failed (e.g. ⚠️ Finished: 48 Downloaded, 2 Failed).
- **Dynamic Limit Warnings:** The console log now actively warns users if the category contains fewer items than the requested limit (e.g., ⚠️ Notice: You requested 50 images, but only 20 exist.).

### ⚙️ Core Engine & Network Updates
- **New Nekosia Worker:** Created a brand new worker for Nekosia using the modern pi/v1/images/{tag} endpoint.
- **E-Shuushuu Downloader Fixed:** Fixed the crash related to iohttp's 8190-byte limit on massive headers. The worker now flawlessly mixes equests (for scanning) and iohttp (for downloading) bypassing all issues.
- **AnimePictures.net Downloader Fixed:** Rewrote the nime_dl.py worker entirely using curl_cffi to flawlessly impersonate TLS (chrome131) and avoid Cloudflare blocks, all while perfectly hooking into the BaseDownloader queueing system.
- **Zerochan Login Integration:** Added Zerochan Login to the Settings tab! The zerochan.py worker now automatically feeds your username and password into gallery-dl under the hood, unlocking full API access for members. If no login is provided, it gracefully continues and logs an informative message.
- **BaseDownloader Error Tracking:** The shared.py base engine now meticulously tracks ailed_count and passes accurate error ratios back to the frontend UI upon task completion.

### 🧹 Fixes & Stability
- Fixed ZerochanWorker's self.session initialization crash which caused immediate failures upon start.
- Installed and handled the curl_cffi dependency effectively.
- Fixed a massive syntax error block that destroyed UI Javascript execution.
