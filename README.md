# Rem God Catcher

A powerful, cross-platform image downloading tool designed to interact with various imageboard APIs. It features a modern Glass-morphism Web UI (powered by Flask + Socket.IO) and a robust Python backend capable of batch-downloading images with advanced tag filtering.

## Features

* **Multi-Platform Support:** Built-in modules for Rule34, Safebooru, Zerochan, Waifu.im, and Nekos.best.
* **Modern Web UI:** A sleek, dark-themed glass-morphism interface with real-time console logging. Opens in your default browser.
* **Advanced Search Logic:**
  * Support for `AND` & `OR` (`~`) tag queries.
  * Tag exclusions (e.g., `-video`, `-gif`).
  * Custom sorting (Score, ID, Ascending, Descending).
* **Titan Engine:** Anti-ban protections, tactical delays, and a resilient retry-loop to handle slow networks and API rate limits.
* **API Key Management:** Configure Rule34 API credentials directly from the Web UI. Keys are stored in a local `.env` file.

---

## How to Customize Background Images (Wallpapers)

The Web UI changes its background wallpaper dynamically depending on the tab you are currently browsing. To personalize these wallpapers with your own images:

1. Navigate to the `web/wallpaper/` directory.
2. Replace the default placeholder files with your own images. **You must keep the exact same filenames and extensions** listed below:

```text
web/wallpaper/
├── Rem_main.png     <- Main / System Setup Tab
├── Rem_neko.jpg     <- Nekos.best Tab
├── Rem_zero.jpg     <- Zerochan Tab
├── Rem_waifu.png    <- Waifu.im Tab
├── Rem_safe.jpg     <- Safebooru Tab
└── Rem_rule34.jpg   <- Rule34 Tab
```

Restart the application to see your custom themes in action!

## Installation & Usage

1. Clone this repository:
   ```bash
   git clone https://github.com/YourUsername/Rem-God-Catcher.git
   cd Rem-God-Catcher
   ```

2. Install the required Python dependencies:
   ```bash
   pip install flask flask-socketio requests urllib3 python-dotenv rule34Py
   ```

3. (Optional) Configure your Rule34 API key:
   - Edit the `.env` file in the project root, or
   - Open the Web UI and go to the **API Keys** tab.

4. Launch the application:
   ```bash
   python Rem_catcher.py
   ```
   The Web UI will automatically open in your default browser at `http://127.0.0.1:5000`.

## Dependencies

| Package | Purpose |
|---------|---------|
| `flask` | Web server for serving the UI and REST API |
| `flask-socketio` | Real-time WebSocket communication for live log streaming |
| `requests` | HTTP client for API calls and image downloads |
| `urllib3` | Low-level HTTP utilities and retry strategies |
| `python-dotenv` | Load API keys from `.env` file |
| `rule34Py` | Rule34 API wrapper library |

## Disclaimer & Terms of Use

* **Educational Purposes:** This software is provided for educational and archiving purposes only.
* **NSFW Content:** Some of the APIs supported by this tool index Not Safe For Work (NSFW) content. Users must be of legal age in their jurisdiction to use the tool for such purposes.
* **API Limits:** This tool is designed to respect the target servers by using rate-limiting and tactical pauses. Please do not modify the code to aggressively spam requests.

## License

MIT License
