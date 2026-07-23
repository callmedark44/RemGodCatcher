let globalNetConfig = { "proxy_url": "", "use_proxy": false, "verify_tls": false };
let uiConfig = {};
let currentActiveTheme = 'dark';

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    if (uiConfig.theme_mode === 'system') {
        applyRenderTheme(e.matches ? 'dark' : 'light');
    }
});

async function loadUIConfig() {
    try {
        let resp = await fetch("/api/ui_config");
        uiConfig = await resp.json();

        let radio = document.querySelector(`input[name="themeMode"][value="${uiConfig.theme_mode}"]`);
        if (radio) radio.checked = true;

        let resolvedTheme = uiConfig.theme_mode;
        if (resolvedTheme === 'system') {
            resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        applyRenderTheme(resolvedTheme);
        renderWallpaperGrid();
    } catch(e) { console.error("Error loading UI config", e); }
}

function applyRenderTheme(themeStr) {
    currentActiveTheme = themeStr;
    document.documentElement.setAttribute('data-theme', themeStr);

    let colors = uiConfig.colors[themeStr];
    if (!colors) return;
    updateLiveColor('title', colors.title, false);
    updateLiveColor('text', colors.text, false);
    updateLiveColor('accent', colors.accent, false);
    updateLiveColor('tab_text', colors.tab_text, false);
    updateLiveColor('tab_hover_bg', colors.tab_hover_bg, false);
    updateLiveColor('tab_active_bg', colors.tab_active_bg, false);
    updateLiveColor('btn_start_bg', colors.btn_start_bg, false);
    updateLiveColor('btn_start_text', colors.btn_start_text, false);
    updateLiveColor('btn_stop_bg', colors.btn_stop_bg, false);
    updateLiveColor('btn_stop_text', colors.btn_stop_text, false);

    let activeTabBtn = document.querySelector(".tab-btn.active");
    if (activeTabBtn) {
        let tabMatch = activeTabBtn.getAttribute("onclick").match(/'([^']+)'/);
        if (tabMatch) updateBackground(tabMatch[1]);
    }
}

function changeThemeMode(mode) {
    uiConfig.theme_mode = mode;
    let resolvedTheme = mode === 'system' ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode;
    applyRenderTheme(resolvedTheme);
}

function updateLiveColor(key, hexVal, saveToConfig = true) {
    let cssKey = key;
    if (key === 'title') cssKey = 'title-color';
    else if (key === 'text') cssKey = 'text-color';
    else if (key === 'accent') cssKey = 'accent-color';
    else cssKey = key.replace(/_/g, '-');

    document.documentElement.style.setProperty(`--${cssKey}`, hexVal);

    let colorInput = document.getElementById(`color_${key}`);
    if (colorInput) colorInput.value = hexVal;

    if (saveToConfig) uiConfig.colors[currentActiveTheme][key] = hexVal;
}

function renderWallpaperGrid() {
    let ui = document.getElementById("wpGridUI");
    if (!ui) return;
    ui.innerHTML = "";
    Object.keys(uiConfig.wallpapers).forEach(tab => {
        let boxIdDark = `file_${tab}_dark`;
        let boxIdLight = `file_${tab}_light`;

        ui.innerHTML += `
            <div style="display: flex; flex-direction: column; gap: 5px;">
                <span style="color: var(--text-color); font-size: 13px; font-weight: bold;">${tab}</span>
                <div style="display: flex; gap: 10px;">
                    <div class="wp-box dark-mode" onclick="document.getElementById('${boxIdDark}').click()">
                        Dark Mode
                        <input type="file" id="${boxIdDark}" accept="image/*" style="display:none" onchange="uploadWpBox('${tab}', 'dark', this)">
                    </div>
                    <div class="wp-box light-mode" onclick="document.getElementById('${boxIdLight}').click()">
                        Light Mode
                        <input type="file" id="${boxIdLight}" accept="image/*" style="display:none" onchange="uploadWpBox('${tab}', 'light', this)">
                    </div>
                </div>
            </div>
        `;
    });
}

async function uploadWpBox(tabName, mode, fileInput) {
    if (!fileInput.files || fileInput.files.length === 0) return;
    let formData = new FormData();
    formData.append("file", fileInput.files[0]);
    try {
        let resp = await fetch("/api/upload_wallpaper", { method: "POST", body: formData });
        let result = await resp.json();
        if (result.success) {
            uiConfig.wallpapers[tabName][mode] = result.filename;
            fileInput.parentElement.style.border = "2px solid var(--title-color)";
            setTimeout(() => fileInput.parentElement.style.border = "", 1000);

            let activeTabBtn = document.querySelector(".tab-btn.active");
            if (activeTabBtn && activeTabBtn.getAttribute("onclick").includes(`'${tabName}'`) && currentActiveTheme === mode) {
                updateBackground(tabName);
            }
        }
    } catch (e) { alert("Upload failed: " + e); }
    fileInput.value = "";
}

function updateBackground(tabName) {
    let wp = uiConfig.wallpapers && uiConfig.wallpapers[tabName];
    if (!wp) return;
    let filename = wp[currentActiveTheme] || wp['dark'];
    if (filename) {
        document.body.style.backgroundImage = `url('user_wallpapers/${filename}')`;
    }
}

// =====================================
// === COLOR PALETTE SAVE & RESET ===
// =====================================
async function saveColors() {
    await fetch("/api/ui_config", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(uiConfig) });
    let status = document.getElementById("colorSaveStatus");
    status.textContent = "Colors Saved!";
    setTimeout(()=> status.textContent = "", 2000);
}

async function resetColors() {
    if (!confirm("Are you sure you want to reset all COLORS to default? Wallpapers will not be changed.")) return;

    uiConfig.colors = {
        "dark": {
            "title": "#00d2d3", "text": "#ffffff", "accent": "#ff9ff3", "tab_text": "#ffffff",
            "tab_hover_bg": "rgba(255, 255, 255, 0.15)", "tab_active_bg": "rgba(0, 210, 211, 0.3)",
            "btn_start_bg": "#00d2d3", "btn_start_text": "#0a0a0a",
            "btn_stop_bg": "#ff9ff3", "btn_stop_text": "#1a0a1a"
        },
        "light": {
            "title": "#004d4d",
            "text": "#1a1a2e",
            "accent": "#a0008a",
            "tab_text": "#1a1a2e",
            "tab_hover_bg": "rgba(0, 0, 0, 0.05)", "tab_active_bg": "rgba(0, 122, 122, 0.12)",
            "btn_start_bg": "#004d4d", "btn_start_text": "#ffffff",
            "btn_stop_bg": "#a0008a", "btn_stop_text": "#ffffff"
        }
    };

    applyRenderTheme(currentActiveTheme);
    await saveColors();

    let status = document.getElementById("colorSaveStatus");
    status.textContent = "Colors Reset!";
    status.style.color = "var(--title-color)";
    setTimeout(() => { status.textContent = ""; }, 2000);
}


// =====================================
// === WALLPAPERS SAVE & RESET ===
// =====================================
async function saveWallpapersUI() {
    await fetch("/api/ui_config", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(uiConfig) });
    let status = document.getElementById("wpSaveStatusUI");
    status.textContent = "Wallpapers Saved!";
    setTimeout(()=> status.textContent = "", 2000);
}

async function resetWallpapersUI() {
    if (!confirm("Are you sure you want to reset all WALLPAPERS to default? Colors will not be changed.")) return;

    uiConfig.wallpapers = {
        "Main": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
        "Neko": {"dark": "Rem_neko_d.png", "light": "Rem_neko_l.png"},
        "NekosLife": {"dark": "Rem_nekolife_d.png", "light": "Rem_nekolife_l.png"},
        "Zero": {"dark": "Rem_zero_d.png", "light": "Rem_zero_l.png"},
        "Waifu": {"dark": "Rem_waifu_d.png", "light": "Rem_waifu_l.png"},
        "Safe": {"dark": "Rem_safe_d.png", "light": "Rem_safe_l.png"},
        "Gelbooru": {"dark": "Rem_gelbooru_d.png", "light": "Rem_gelbooru_l.png"},
        "Rule34": {"dark": "Rem_rule34_d.png", "light": "Rem_rule34_l.png"},
        "Yande": {"dark": "Rem_yande_d.png", "light": "Rem_yande_l.png"},
        "Danbooru": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
        "Pinterest": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
        "Pixiv": {"dark": "Rem_main_d.png", "light": "Rem_main_l.png"},
        "History": {"dark": "Rem_history_d.png", "light": "Rem_history_l.png"},
        "Options": {"dark": "Rem_option_d.png", "light": "Rem_option_l.png"},
        "Customize": {"dark": "Rem_custom_d.png", "light": "Rem_custom_l.png"}
    };

    renderWallpaperGrid();
    await saveWallpapersUI();
    updateBackground("Customize");

    let status = document.getElementById("wpSaveStatusUI");
    status.textContent = "Wallpapers Reset!";
    status.style.color = "var(--accent-color)";
    setTimeout(() => { status.textContent = ""; status.style.color = "var(--title-color)"; }, 2000);
}

const socket = io();

const WORKER_TO_TAB = {
    "neko": "neko", "nekos_life": "nekos_life", "zero": "zero", "waifu": "waifu",
    "safe": "safe", "gelbooru": "gelbooru", "rule34": "rule34", "yande": "yande",
    "kona": "kona", "dan": "dan", "sankaku": "sankaku", "anime_dl": "anime_dl",
    "pinterest": "pinterest",
    "pixiv": "pixiv"
};

function updateProgressBar(worker, msg) {
    let key = WORKER_TO_TAB[worker];
    if (!key) return;
    let wrap = document.getElementById("progressWrap_" + key);
    let fill = document.getElementById("progress_" + key);
    let txt = document.getElementById("progressText_" + key);
    if (!wrap || !fill || !txt) return;

    if (msg.includes("Phase 2: Starting parallel download")) {
        wrap.classList.add("active");
        fill.classList.remove("done");
        fill.style.width = "0%";
        txt.textContent = "0%";
        return;
    }

    if (msg.includes("[SUCCESS] Downloaded")) {
        let m = msg.match(/\[(\d+)%\]/);
        if (m) {
            let pct = Math.max(0, Math.min(parseInt(m[1]), 100));
            fill.style.width = pct + "%";
            txt.textContent = pct + "%";
        }
        return;
    }

    if (msg.includes("--- All") && msg.includes("downloads completed")) {
        fill.classList.add("done");
        fill.style.width = "100%";
        txt.textContent = "100%";
        setTimeout(() => { wrap.classList.remove("active"); fill.classList.remove("done"); }, 3000);
        return;
    }

    if (msg.includes("No new") || msg.includes("No posts") || msg.includes("Task finished") || msg.includes("Worker Terminated")) {
        wrap.classList.remove("active");
        return;
    }
}

socket.on("python_log", function (data) {
    updateProgressBar(data.worker, data.msg);
    logToConsole(data.worker, data.msg);
});

socket.on("update_history", function () {
    loadTagsData();
    loadGallery();
    populateGallerySiteFilter();
});

socket.on("pinterest_progress", function (data) {
    let pct = Math.min(100, Math.round((data.index / data.total) * 100));
    let wrap = document.getElementById("progressWrap_pinterest");
    let fill = document.getElementById("progress_pinterest");
    let txt = document.getElementById("progressText_pinterest");
    if (wrap) wrap.classList.add("active");
    if (fill) fill.style.width = pct + "%";
    if (txt) txt.textContent = pct + "%";

});

window.onload = async function () {
    try {
        let resp = await fetch("/api/config");
        let config = await resp.json();
        if (config) {
            globalNetConfig = config;
            document.getElementById("proxyEnabled").checked = config.use_proxy || false;
            document.getElementById("proxyUrl").value = config.proxy_url || "http://127.0.0.1:10808";
            document.getElementById("apiTimeout").value = config.api_timeout || 10;
            document.getElementById("retryWait").value = config.retry_wait || 5;
            document.getElementById("antiBanPause").value = config.anti_ban_pause || 3;
            document.getElementById("downloadRetries").value = config.download_retries || 3;
        }
    } catch (e) { console.error("Config error:", e); }

    try {
        let resp = await fetch("/api/folder");
        let data = await resp.json();
        if (data.folder) document.getElementById("folderDisplay").innerText = data.folder;
    } catch (e) {}

    updateNekoDropdown();
    updateNekosLifeType();
    await loadUIConfig();

    try {
        let resp = await fetch("/api/tags/waifu", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(globalNetConfig)
        });
        let waifuTags = await resp.json();
        let sel = document.getElementById("waifuTag");
        sel.innerHTML = "";
        waifuTags.forEach(t => {
            let opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            sel.appendChild(opt);
        });
    } catch (e) {}

    await loadTagsData();
    await loadApiSettings();
    await importGallery();
    loadGallery();
    populateGallerySiteFilter();
};

const nekoImages = ["husbando", "kitsune", "neko", "waifu"];
const nekoGifs = ["angry", "baka", "bite", "bleh", "blowkiss", "blush", "bonk", "bored", "carry", "clap", "confused", "cry", "cuddle", "dance", "facepalm", "feed", "handhold", "handshake", "happy", "highfive", "hug", "kabedon", "kick", "kiss", "lappillow", "laugh", "lurk", "nod", "nom", "nope", "nya", "pat", "peck", "poke", "pout", "punch", "run", "salute", "shake", "shoot", "shocked", "shrug", "sip", "slap", "sleep", "smile", "smug", "spin", "stare", "tableflip", "teehee", "think", "thumbsup", "tickle", "wag", "wave", "wink", "yawn", "yeet"];

function updateNekoDropdown() {
    let fmt = document.getElementById("nekoFormat").value;
    let sel = document.getElementById("nekoCat");
    sel.innerHTML = "";
    
    let targetList = fmt === "Images" ? nekoImages : nekoGifs;
    targetList.forEach(t => {
        let opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        sel.appendChild(opt);
    });
}

function toggleGifExclusion(formatId, checkboxId) {
    let format = document.getElementById(formatId).value;
    let checkbox = document.getElementById(checkboxId);
    let label = checkbox.nextElementSibling;
    if (format === 'gifs') {
        checkbox.style.display = 'none';
        label.style.display = 'none';
    } else {
        checkbox.style.display = '';
        label.style.display = '';
    }
}

function updateNekosLifeType() {
    const gifOnly = ["ngif", "hug", "pat", "cuddle", "tickle", "feed", "slap", "kiss", "smug"];
    const staticOnly = ["gecg", "meow", "neko", "lewd", "gasm", "8ball", "avatar", "woof", "fox_girl", "waifu"];
    const mixed = ["goose", "wallpaper", "lizard", "span"];
    
    let cat = document.getElementById("nekosLifeCat").value;
    let typeEl = document.getElementById("nekosLifeType");
    let formatLabel = document.getElementById("nekosLifeFormatLabel");
    let formatSelect = document.getElementById("nekosLifeFormat");
    
    if (gifOnly.includes(cat)) {
        typeEl.textContent = "[GIF]";
        typeEl.style.color = "var(--accent-color)";
        formatLabel.style.display = "none";
        formatSelect.style.display = "none";
    } else if (staticOnly.includes(cat)) {
        typeEl.textContent = "[STATIC]";
        typeEl.style.color = "#00d2d3";
        formatLabel.style.display = "none";
        formatSelect.style.display = "none";
    } else if (mixed.includes(cat)) {
        typeEl.textContent = "[MIXED]";
        typeEl.style.color = "#ffd93d";
        formatLabel.style.display = "";
        formatSelect.style.display = "";
    } else {
        typeEl.textContent = "";
        formatLabel.style.display = "none";
        formatSelect.style.display = "none";
    }
}

function updateNekosLifeFormatHint() {
    // Optional: add hint text based on format selection
}

async function saveProxySettings() {
    globalNetConfig.use_proxy = document.getElementById("proxyEnabled").checked;
    globalNetConfig.proxy_url = document.getElementById("proxyUrl").value;
    try {
        await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(globalNetConfig) });
        logToConsole("main", "Proxy updated.");
    } catch (e) {}
}

async function browseFolder() {
    let folder = prompt("Enter the master download folder path:");
    if (!folder) return;
    try {
        let resp = await fetch("/api/folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: folder }) });
        let data = await resp.json();
        if (data.folder) {
            document.getElementById("folderDisplay").innerText = data.folder;
            logToConsole("main", `Master folder updated to: ${data.folder}`);
        }
    } catch(e) {}
}

function openTab(tabName, btn) {
    let contents = document.getElementsByClassName("tab-content");
    for (let i = 0; i < contents.length; i++) contents[i].style.display = "none";
    let buttons = document.getElementsByClassName("tab-btn");
    for (let i = 0; i < buttons.length; i++) buttons[i].classList.remove("active");

    document.getElementById(tabName).style.display = "flex";
    btn.classList.add("active");
    updateBackground(tabName);
}

function clearLog(tabID) {
    let boxMap = {
        "main": "consoleLog_main", "neko": "consoleLog_neko", "nekos_life": "consoleLog_nekos_life",
        "zero": "consoleLog_zero", "waifu": "consoleLog_waifu", "safe": "consoleLog_safe",
        "rule34": "consoleLog_rule34", "gelbooru": "consoleLog_gelbooru", "yande": "consoleLog_yande",
        "kona": "consoleLog_kona", "dan": "consoleLog_dan", "sankaku": "consoleLog_sankaku",
        "anime_dl": "consoleLog_anime_dl", "pinterest": "consoleLog_pinterest",
        "pixiv": "consoleLog_pixiv"
    };
    let cb = document.getElementById(boxMap[tabID.toLowerCase()] || "consoleLog_main");
    if (cb) cb.innerHTML = "";
}

function logToConsole(tabID, msg) {
    let boxMap = {
        "main": "consoleLog_main", "neko": "consoleLog_neko", "nekos_life": "consoleLog_nekos_life",
        "zero": "consoleLog_zero", "waifu": "consoleLog_waifu", "safe": "consoleLog_safe",
        "rule34": "consoleLog_rule34", "gelbooru": "consoleLog_gelbooru", "yande": "consoleLog_yande",
        "kona": "consoleLog_kona", "dan": "consoleLog_dan", "sankaku": "consoleLog_sankaku",
        "anime_dl": "consoleLog_anime_dl", "pinterest": "consoleLog_pinterest",
        "pixiv": "consoleLog_pixiv"
    };
    let cb = document.getElementById(boxMap[tabID.toLowerCase()] || "consoleLog_main");
    if (cb) {
        let line = document.createElement("div");
        line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        cb.appendChild(line);
        cb.scrollTop = cb.scrollHeight;
    }
}

async function startWorker(workerName) {
    let payload = { worker: workerName, net_config: { ...globalNetConfig } };
    payload.net_config.api_timeout = document.getElementById("apiTimeout").value;
    payload.net_config.retry_wait = document.getElementById("retryWait").value;
    payload.net_config.anti_ban_pause = document.getElementById("antiBanPause").value;
    
    if (workerName === 'zero') {
        payload.tag = document.getElementById('zeroTag').value;
        payload.limit = document.getElementById('zeroLimit').value;
    } else if (workerName === 'waifu') {
        payload.tag = document.getElementById('waifuTag').value;
        payload.limit = document.getElementById('waifuLimit').value;
        payload.nsfw = document.getElementById('waifuNsfw').checked;
    } else if (workerName === 'neko') {
        payload.category = document.getElementById('nekoCat').value;
        payload.limit = document.getElementById('nekoAmount').value;
    } else if (workerName === 'nekos_life') {
        payload.category = document.getElementById('nekosLifeCat').value;
        payload.limit = document.getElementById('nekosLifeAmount').value;
        // Add format parameter for Mixed categories
        const mixed = ["goose", "wallpaper", "lizard", "span"];
        if (mixed.includes(payload.category)) {
            payload.format = document.getElementById('nekosLifeFormat').value;
        }
    } else if (workerName === 'safe') {
        payload.tag = document.getElementById('safeTag').value;
        payload.limit = document.getElementById('safeLimit').value;
        payload.exclusions = [];

    } else if (workerName === 'gelbooru') {
        payload.tag = document.getElementById('gelbooruTag').value;
        payload.limit = document.getElementById('gelbooruLimit').value;
        payload.rating = document.getElementById('gelbooruRating').value;
        
        let format = document.getElementById('gelFormat').value;
        let ex = [];
        if (format === 'images') ex.push('-video');
        else if (format === 'videos') {
            ex.push('-image');
            payload.tag += " video";
        }
        payload.exclusions = ex;
        if (document.getElementById('gelNoAI').checked) payload.tag += " -ai_generated";

    } else if (workerName === 'yande') {
        payload.tag = document.getElementById('yandeTag').value;
        payload.limit = document.getElementById('yandeLimit').value;
        payload.rating = document.getElementById('yandeRating').value;

    } else if (workerName === 'dan') {
        payload.tag = document.getElementById('danTag').value;
        payload.limit = document.getElementById('danLimit').value;
        payload.rating = document.getElementById('danRating').value;

        let format = document.getElementById('danFormat').value;
        let ex = [];
        if (format === 'images') ex.push('-video');
        else if (format === 'videos') {
            ex.push('-image');
            payload.tag += " video";
        }
        if (document.getElementById('danExGif').checked) ex.push('-gif');
        payload.exclusions = ex;

    } else if (workerName === 'kona') {
        payload.tag = document.getElementById('konaTag').value;
        payload.limit = document.getElementById('konaLimit').value;
        payload.rating = document.getElementById('konaRating').value;

        let format = document.getElementById('konaFormat').value;
        let ex = [];
        if (format === 'images') ex.push('-video');
        else if (format === 'videos') {
            ex.push('-image');
            payload.tag += " video";
        }
        if (document.getElementById('konaExGif').checked) ex.push('-gif');
        payload.exclusions = ex;

    } else if (workerName === 'rule34') {
        payload.tag = document.getElementById('rule34Tag').value;
        payload.limit = document.getElementById('rule34Limit').value;
        payload.method = document.getElementById('rule34Method').value;
        payload.sort_type = document.getElementById('rule34SortType').value;
        payload.sort_order = document.getElementById('rule34SortOrder').value;
        
        let format = document.getElementById('rule34Format').value;
        let ex = [];
        if (format === 'images') ex.push('-video');
        else if (format === 'gifs') {
            ex.push('-video');
            ex.push('-image');
        }
        else if (format === 'videos') {
            ex.push('-image');
            payload.tag += " video";
        }
        
        if (document.getElementById('exGif').checked) ex.push('-gif');
        if (document.getElementById('exComic').checked) ex.push('-comic');
        if (document.getElementById('ex3D').checked) ex.push('-3d');
        payload.exclusions = ex;
    } else if (workerName === 'sankaku') {
        payload.tag = document.getElementById('sankakuTag').value;
        payload.limit = document.getElementById('sankakuLimit').value;
        payload.rating = document.getElementById('sankakuRating').value;
        payload.exclusions = [];
        payload.net_config.hide_pools = document.getElementById('sankakuHideBooks').checked;
    } else if (workerName === 'anime_dl') {
        payload.tag = document.getElementById('animeDlTag').value;
        payload.limit = document.getElementById('animeDlLimit').value;
    } else if (workerName === 'pinterest') {
        payload.tag = document.getElementById('pinterestTag').value;
        payload.limit = document.getElementById('pinterestLimit').value;
        payload.is_search = document.getElementById('pinterestMode').value === 'search';
        payload.min_w = +document.getElementById('pinterestMinW').value || 0;
        payload.min_h = +document.getElementById('pinterestMinH').value || 0;
    } else if (workerName === 'pixiv') {
        let mode = document.getElementById('pixivMode').value;
        let ranking = document.getElementById('pixivRankingMode').value;

        if (mode === 'ranking') {
            payload.tag = 'ranking:' + ranking;
        } else {
            let val = document.getElementById('pixivTag').value.trim();
            if (!val) { logToConsole('pixiv', 'Error: Please enter a user ID or search term'); return; }
            payload.tag = mode + ':' + val;
        }

        payload.limit = document.getElementById('pixivLimit').value;
        payload.rating = document.getElementById('pixivRating').value;

        payload.exclusions = [];

        let existingToken = document.getElementById('pixivToken').value.trim();
        let pixivEmail = document.getElementById('pixivLoginEmail').value.trim();
        let pixivPassword = document.getElementById('pixivLoginPassword').value.trim();

        if (!existingToken && pixivEmail && pixivPassword) {
            let statusEl = document.getElementById('pixivLoginStatus');
            statusEl.textContent = 'Logging in...';
            try {
                let resp = await fetch('/api/pixiv/get_token', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: pixivEmail, password: pixivPassword})
                });
                let result = await resp.json();
                if (result.success) {
                    document.getElementById('pixivToken').value = result.token;
                } else {
                    let msg = result.error || result.message || 'Login failed';
                    statusEl.textContent = '✗ ' + msg;
                    logToConsole('pixiv', 'Auth failed: ' + msg);
                    return;
                }
            } catch (e) {
                statusEl.textContent = '✗ Network error';
                logToConsole('pixiv', 'Auth error: network request failed');
                return;
            }
        } else if (!existingToken) {
            logToConsole('pixiv', 'Auth error: enter Pixiv email/password in Options tab or provide a refresh token');
            return;
        }
    }
    
    socket.emit("start_worker", payload);

    let key = WORKER_TO_TAB[workerName];
    if (key) {
        let wrap = document.getElementById("progressWrap_" + key);
        let fill = document.getElementById("progress_" + key);
        let txt = document.getElementById("progressText_" + key);
        if (wrap && fill && txt) {
            wrap.classList.add("active");
            fill.classList.remove("done");
            fill.style.width = "0%";
            txt.textContent = "Gathering...";
        }
    }

    setTimeout(loadTagsData, 1000);
}

function stopWorker(workerName) {
    socket.emit("stop_worker", { worker: workerName });
    let key = WORKER_TO_TAB[workerName];
    if (key) {
        let wrap = document.getElementById("progressWrap_" + key);
        if (wrap) wrap.classList.remove("active");
    }
}

async function loadApiSettings() {
    let resp = await fetch("/api/api-settings");
    let settings = await resp.json();
    document.getElementById("r34Key").value = settings.rule34_api_key || "";
    document.getElementById("r34Uid").value = settings.rule34_user_id || "";
    document.getElementById("gelKey").value = settings.gelbooru_api_key || "";
    document.getElementById("gelUid").value = settings.gelbooru_user_id || "";
    document.getElementById("sankaLogin").value = settings.sanka_login || "";
    document.getElementById("sankaPassword").value = settings.sanka_password || "";
    document.getElementById("pinterestCookies").value = settings.pinterest_cookies || "";
    document.getElementById("pinterestEmail").value = settings.pinterest_email || "";
    document.getElementById("pinterestPassword").value = settings.pinterest_password || "";
    document.getElementById("pixivLoginEmail").value = settings.pixiv_login_email || "";
    document.getElementById("pixivLoginPassword").value = settings.pixiv_login_password || "";
    document.getElementById("pixivToken").value = settings.pixiv_refresh_token || "";
}

async function saveApiSettings() {
    let payload = {
        rule34_api_key: document.getElementById("r34Key").value.trim(),
        rule34_user_id: document.getElementById("r34Uid").value.trim(),
        gelbooru_api_key: document.getElementById("gelKey").value.trim(),
        gelbooru_user_id: document.getElementById("gelUid").value.trim(),
        sanka_login: document.getElementById("sankaLogin").value.trim(),
        sanka_password: document.getElementById("sankaPassword").value.trim(),
        pinterest_cookies: document.getElementById("pinterestCookies").value.trim(),
        pinterest_email: document.getElementById("pinterestEmail").value.trim(),
        pinterest_password: document.getElementById("pinterestPassword").value.trim(),
        pixiv_login_email: document.getElementById("pixivLoginEmail").value.trim(),
        pixiv_login_password: document.getElementById("pixivLoginPassword").value.trim(),
        pixiv_refresh_token: document.getElementById("pixivToken").value.trim()
    };
    let resp = await fetch("/api/api-settings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    let result = await resp.json();
    let statusEl = document.getElementById("apiSaveStatus");
    statusEl.textContent = result.success ? "Saved!" : "Error!";
    setTimeout(()=> statusEl.textContent = "", 2000);
}

async function saveDownloadSettings() {
    globalNetConfig.api_timeout = document.getElementById("apiTimeout").value;
    globalNetConfig.retry_wait = document.getElementById("retryWait").value;
    globalNetConfig.anti_ban_pause = document.getElementById("antiBanPause").value;
    globalNetConfig.download_retries = document.getElementById("downloadRetries").value;
    await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(globalNetConfig) });
    document.getElementById("dlSettingsStatus").textContent = "Saved!";
    setTimeout(()=> document.getElementById("dlSettingsStatus").textContent = "", 2000);
}

// ==========================================
// === AUTO-SUGGEST FIX ===
// ==========================================
async function fetchZero(val) {
    if (val.length < 3) return;
    try {
        let resp = await fetch("/api/tags/zerochan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: val, net_config: globalNetConfig }) });
        let tags = await resp.json();
        let dl = document.getElementById("zeroList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchSafe(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/safe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("safeList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchRule34(val) {
    if (val.length < 2) return;
    try {
        let resp = await fetch("/api/tags/rule34", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: val, net_config: globalNetConfig }) });
        let tags = await resp.json();
        let dl = document.getElementById("rule34List");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchYande(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/yande", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("yandeList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchKona(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/kona", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("konaList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchDan(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/dan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("danList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchGelbooru(val) {
    if (val.length < 2) return;
    try {
        let resp = await fetch("/api/tags/rule34", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: val, net_config: globalNetConfig }) });
        let tags = await resp.json();
        let dl = document.getElementById("gelbooruList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchSankaku(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/sankaku", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("sankakuList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

async function fetchAnimeDl(val) {
    if (val.length < 2) return;
    let words = val.split(" "); let lastWord = words[words.length - 1]; if(lastWord.length < 2) return;
    try {
        let resp = await fetch("/api/tags/anime_dl", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: lastWord }) });
        let tags = await resp.json();
        let dl = document.getElementById("animeDlList");
        let dHtml = "";
        tags.forEach(t => dHtml += `<option value="${words.slice(0,-1).join(" ") + (words.length>1?" ":"") + t}">`);
        dl.innerHTML = dHtml;
    } catch(e) {}
}

// ==========================================
// === HISTORY & FAVORITES SYSTEM ===
// ==========================================
let historyTags = [];
let favoriteTags = [];
let imageHistory = [];

async function loadTagsData() {
    try {
        let resHist = await fetch("/api/history");
        historyTags = await resHist.json();
        
        let resFav = await fetch("/api/favorites");
        favoriteTags = await resFav.json();

        let resImgHist = await fetch("/api/image_history");
        imageHistory = await resImgHist.json();
        
        renderHistory();
        renderFavorites();
        renderImageHistory();
    } catch(e) { console.error("Error loading tags", e); }
}

function isFavorite(site, tag) {
    return favoriteTags.some(x => x.site === site && x.tag === tag);
}

function renderHistory() {
    let ui = document.getElementById("historyListUI");
    if(!ui) return;
    let currentScroll = ui.parentElement.scrollTop;
    let htmlStr = "";
    if (historyTags.length === 0) {
        htmlStr = "<p style='color: var(--text-color); opacity: 0.7; font-size: 13px;'>No search history yet.</p>";
    } else {
        historyTags.forEach(item => {
            let isFav = isFavorite(item.site, item.tag);
            let heartIcon = isFav ? "★" : "☆";

            htmlStr += `
                <div style="display: flex; justify-content: space-between; align-items: center; background: var(--input-bg); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color);">
                    <div>
                        <span style="color: var(--accent-color); font-size: 11px; text-transform: uppercase; border: 1px solid var(--accent-color); padding: 2px 5px; border-radius: 4px; margin-right: 10px;">${item.site}</span>
                        <span style="font-size: 14px; color: var(--text-color);">${item.tag}</span>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <button class="action-btn" style="padding: 4px 8px; font-size: 12px; background: transparent; border: 1px solid var(--border-color); color: var(--text-color);" onclick="jumpToSite('${item.site}', '${item.tag}')">&rarr;</button>
                        <button class="action-btn" style="padding: 4px 8px; font-size: 12px; background: transparent; border: 1px solid var(--border-color);" onclick="toggleFavorite('${item.site}', '${item.tag}')">${heartIcon}</button>
                        <button class="action-btn stop-btn" style="padding: 4px 8px; font-size: 12px;" onclick="removeFromHistory('${item.site}', '${item.tag}')">&times;</button>
                    </div>
                </div>
            `;
        });
    }
    ui.innerHTML = htmlStr;
    ui.parentElement.scrollTop = currentScroll;
}

function renderFavorites() {
    let ui = document.getElementById("favoritesListUI");
    if(!ui) return;
    ui.innerHTML = "";
    if (favoriteTags.length === 0) {
        ui.innerHTML = "<p style='color: var(--text-color); opacity: 0.7; font-size: 12px;'>Click ☆ in the History tab to add favorites.</p>";
        return;
    }

    favoriteTags.forEach(item => {
        ui.innerHTML += `
            <div style="background: var(--tab-active-bg); border: 1px solid var(--title-color); padding: 5px 10px; border-radius: 20px; font-size: 13px; display: flex; align-items: center; gap: 5px; transition: 0.2s;">
                <span onclick="jumpToSite('${item.site}', '${item.tag}')" style="cursor: pointer; display: flex; align-items: center; gap: 5px; flex: 1; color: var(--text-color);">
                    <span>✦</span>
                    <span style="color: var(--title-color); font-weight: bold; font-size: 10px; text-transform: uppercase;">[${item.site}]</span>
                    <span>${item.tag}</span>
                </span>
                <button onclick="event.stopPropagation(); toggleFavorite('${item.site}', '${item.tag}')" style="background: transparent; border: none; color: #ff6b6b; cursor: pointer; font-size: 12px; padding: 0 0 0 5px; line-height: 1;">✕</button>
            </div>
        `;
    });
}

async function toggleFavorite(site, tag) {
    let action = isFavorite(site, tag) ? "remove" : "add";
    let resp = await fetch("/api/favorites", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site: site, tag: tag, action: action })
    });
    let data = await resp.json();
    favoriteTags = data.favorites;
    renderHistory();
    renderFavorites();
    renderImageHistory();
}

async function removeFromHistory(site, tag) {
    await fetch("/api/history/remove", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site: site, tag: tag })
    });
    await loadTagsData();
}

async function clearHistory() {
    if(confirm("Are you sure you want to delete all search history?")) {
        await fetch("/api/history/clear", { method: "POST" });
        await loadTagsData();
    }
}

// تابع پرش از صفحه اصلی به تب سایت و پر کردن خودکار
function jumpToSite(site, tag) {
    let siteMap = {
        "zero":      { tab: "Zero",     input: "zeroTag" },
        "waifu":     { tab: "Waifu",    input: "waifuTag" },
        "neko":      { tab: "Neko",     input: null },
        "nekos_life":{ tab: "NekosLife", input: null },
        "safe":      { tab: "Safe",     input: "safeTag" },
        "gelbooru":  { tab: "Gelbooru", input: "gelbooruTag" },
        "yande":     { tab: "Yande",    input: "yandeTag" },
        "kona":      { tab: "Kona",     input: "konaTag" },
        "dan":       { tab: "Danbooru", input: "danTag" },
        "rule34":    { tab: "Rule34",    input: "rule34Tag" },
        "sankaku":   { tab: "Sankaku",  input: "sankakuTag" },
        "anime_dl":  { tab: "AnimeDL",  input: "animeDlTag" },
        "pinterest": { tab: "Pinterest", input: "pinterestTag" },
        "pixiv": { tab: "Pixiv", input: null }
    };
    let mapping = siteMap[site] || { tab: "Safe", input: "safeTag" };

    let btn = Array.from(document.querySelectorAll('.tab-btn')).find(el => el.textContent.toLowerCase().includes(mapping.tab.toLowerCase()));
    if(btn) openTab(mapping.tab, btn);

    if(mapping.input) {
        let inputEl = document.getElementById(mapping.input);
        if(inputEl) inputEl.value = tag;
    }
}

function renderImageHistory() {
    let ui = document.getElementById("imageHistoryUI");
    if(!ui) return;
    
    let currentScroll = ui.parentElement.scrollTop;
    let htmlStr = "";
    
    if (imageHistory.length === 0) {
        htmlStr = "<p style='color: var(--text-color); opacity: 0.7; font-size: 13px;'>No images downloaded yet.</p>";
    } else {
        imageHistory.forEach(img => {
            let tagsHtml = img.tags.map(t => {
                let isFav = isFavorite(img.site, t);
                let bgColor = isFav ? "var(--tab-active-bg)" : "var(--input-bg)";
                let borderColor = isFav ? "var(--accent-color)" : "transparent";
                let textColor = isFav ? "var(--accent-color)" : "var(--text-color)";
                return `<span onclick="addFavoriteFromImage('${img.site}', '${t}')" style="background: ${bgColor}; border: 1px solid ${borderColor}; color: ${textColor}; padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer; transition: 0.2s; white-space: nowrap; display: inline-block;">${t}</span>`;
            }).join('');

            let artistHtml = img.artists && img.artists.length > 0 
                ? `<div style="margin-top: 10px; border-top: 1px solid var(--border-color); padding-top: 8px;">
                       <span style="color: var(--title-color); font-size: 12px; font-weight: bold;">Artists:</span> 
                       <span style="font-size: 12px; color: var(--text-color); opacity: 0.8;">${img.artists.join(', ')}</span>
                   </div>` 
                : "";

            htmlStr += `
                <div style="background: var(--input-bg); padding: 15px; border-radius: 8px; border: 1px solid var(--border-color); position: relative;">
                    <button onclick="removeImageHistory('${img.filename}')" class="action-btn stop-btn" style="position: absolute; top: 10px; right: 10px; padding: 2px 6px; font-size: 10px;">&times;</button>
                    <h3 style="color: var(--text-color); font-size: 16px; margin-bottom: 12px; padding-right: 30px; word-break: break-all;">${img.filename} <span style="font-size: 10px; color: var(--accent-color); border: 1px solid var(--accent-color); padding: 2px 4px; border-radius: 4px; vertical-align: middle; margin-left: 10px;">${img.site}</span></h3>
                    
                    <div style="display: flex; flex-wrap: wrap; gap: 6px; max-height: 150px; overflow-y: auto; padding-right: 5px;">
                        ${tagsHtml}
                    </div>
                    ${artistHtml}
                </div>
            `;
        });
    }
    ui.innerHTML = htmlStr;
    ui.parentElement.scrollTop = currentScroll;
}

async function addFavoriteFromImage(site, tag) {
    await toggleFavorite(site, tag);
}

async function removeImageHistory(filename) {
    await fetch("/api/image_history/remove", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: filename })
    });
    await loadTagsData();
}

async function clearImageHistory() {
    if(confirm("Delete all image tag history?")) {
        await fetch("/api/image_history/clear", { method: "POST" });
        await loadTagsData();
    }
}

// ==========================================
// === GALLERY SYSTEM ===
// ==========================================
let galleryState = { images: [], total: 0, page: 1, total_pages: 1, per_page: 24 };
let currentGalleryPage = 1;
let galleryFavFilter = false;
let galleryGridSize = 140;

const SOURCE_RATINGS = {
    dan: ['safe', 'sensitive', 'questionable', 'explicit'],
    gelbooru: ['safe', 'sensitive', 'questionable', 'explicit'],
    kona: ['safe', 'explicit'],
    yande: ['safe', 'explicit'],
    sankaku: ['safe', 'questionable', 'explicit'],
    pinterest: [],
    pixiv: ['safe', 'explicit'],
};

function updateRatingDropdown() {
    const checks = document.querySelectorAll('#sourceDropdown input[type="checkbox"]');
    let selectedSources = [];
    let allSelected = false;
    checks.forEach(c => { if (c.checked) { if (c.value === '') allSelected = true; else selectedSources.push(c.value); } });
    if (allSelected || selectedSources.length === 0) {
        document.querySelectorAll('#ratingDropdown .dd-item').forEach(el => el.style.display = '');
        return;
    }
    let common = null;
    selectedSources.forEach(s => {
        const r = SOURCE_RATINGS[s.toLowerCase()] || [];
        if (common === null) common = new Set(r);
        else common = new Set([...common].filter(x => r.includes(x)));
    });
    if (common === null) common = new Set();
    common.add('');
    document.querySelectorAll('#ratingDropdown .dd-item').forEach(el => {
        const cb = el.querySelector('input[type="checkbox"]');
        const show = common.has(cb.value);
        el.style.display = show ? '' : 'none';
        if (!show) cb.checked = false;
    });
    const firstCheck = document.querySelector('#ratingDropdown .dd-item input[type="checkbox"]');
    if (firstCheck) {
        const anyChecked = [...document.querySelectorAll('#ratingDropdown input[type="checkbox"]')].some(c => c.checked);
        if (!anyChecked) firstCheck.checked = true;
    }
}

function updateSourceDropdown() {
    const checks = document.querySelectorAll('#ratingDropdown input[type="checkbox"]');
    let selectedRatings = [];
    let allSelected = false;
    checks.forEach(c => { if (c.checked) { if (c.value === '') allSelected = true; else selectedRatings.push(c.value); } });
    if (allSelected || selectedRatings.length === 0) {
        document.querySelectorAll('#sourceDropdown .dd-item').forEach(el => el.style.display = '');
        return;
    }
    document.querySelectorAll('#sourceDropdown .dd-item').forEach(el => {
        const cb = el.querySelector('input[type="checkbox"]');
        if (cb.value === '') { el.style.display = ''; return; }
        const ratings = SOURCE_RATINGS[cb.value.toLowerCase()];
        const show = ratings && selectedRatings.every(r => ratings.includes(r));
        el.style.display = show ? '' : 'none';
        if (!show) cb.checked = false;
    });
    const firstCheck = document.querySelector('#sourceDropdown .dd-item input[type="checkbox"]');
    if (firstCheck) {
        const anyChecked = [...document.querySelectorAll('#sourceDropdown input[type="checkbox"]')].some(c => c.checked);
        if (!anyChecked) firstCheck.checked = true;
    }
}

function getMultiSelectValues(id) {
    const checks = document.querySelectorAll(`#${id} input[type="checkbox"]`);
    const vals = [];
    let allChecked = false;
    checks.forEach(c => { if (c.checked) { if (c.value === '') allChecked = true; else vals.push(c.value); } });
    if (allChecked || vals.length === 0) return '';
    return vals.join(',');
}

function getMultiLabel(id, noneLabel) {
    const checks = document.querySelectorAll(`#${id} input[type="checkbox"]`);
    let count = 0;
    let allChecked = false;
    checks.forEach(c => { if (c.checked) { if (c.value === '') allChecked = true; else count++; } });
    if (allChecked || count === 0) return noneLabel;
    return `${count} selected`;
}

async function loadGallery(page) {
    if (page) currentGalleryPage = page;
    const search = document.getElementById("gallerySearch").value;
    const site = getMultiSelectValues('sourceDropdown');
    const sort = document.getElementById("sortDropdown").dataset.sort || 'newest';
    const type = getMultiSelectValues('typeDropdown');
    const rating = getMultiSelectValues('ratingDropdown');
    const params = new URLSearchParams({
        search, site, sort, type, rating,
        page: currentGalleryPage, per_page: 24
    });
    if (galleryFavFilter) params.set("favourites", "true");
    try {
        let resp = await fetch(`/api/gallery?${params}`);
        galleryState = await resp.json();
        renderGallery();
    } catch (e) { console.error("Gallery load error:", e); }
}

async function loadGalleryPage(page, callback) {
    const search = document.getElementById("gallerySearch").value;
    const site = getMultiSelectValues('sourceDropdown');
    const sort = document.getElementById("sortDropdown").dataset.sort || 'newest';
    const type = getMultiSelectValues('typeDropdown');
    const rating = getMultiSelectValues('ratingDropdown');
    const params = new URLSearchParams({
        search, site, sort, type, rating,
        page, per_page: 24
    });
    if (galleryFavFilter) params.set("favourites", "true");
    try {
        let resp = await fetch(`/api/gallery?${params}`);
        galleryState = await resp.json();
        currentGalleryPage = page;
        if (callback) callback();
    } catch (e) { console.error("Gallery page load error:", e); }
}

function applyGalleryZoom() {
    const grid = document.getElementById("galleryGrid");
    if (grid) grid.style.setProperty("grid-template-columns", `repeat(auto-fill, minmax(${galleryGridSize}px, 1fr))`);
    const label = document.getElementById("galleryZoomLabel");
    if (label) label.textContent = Math.round(galleryGridSize / 140 * 100) + "%";
}

function galleryZoom(delta) {
    galleryGridSize = Math.max(80, Math.min(300, galleryGridSize + delta * 140));
    applyGalleryZoom();
}

function renderGallery() {
    const grid = document.getElementById("galleryGrid");
    const pagination = document.getElementById("galleryPagination");
    if (!grid) return;

    const { images, total, page, total_pages, per_page } = galleryState;

    if (images.length === 0) {
        grid.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-color);opacity:0.5;font-size:14px;">No images found.</div>';
        pagination.innerHTML = '';
        return;
    }

    let html = '';
    images.forEach(img => {
        const fp = (img.filepath || '').replace(/\\/g, '/');
        const ext = ((img.filename || '').split('.').pop() || '').toLowerCase();
        const isVideo = ['mp4','webm','mov','avi','mkv'].includes(ext);
        const src = `/api/gallery/${isVideo ? 'file' : 'thumb'}/${encodeURI(fp)}`;
        html += `
            <div class="gallery-card" onclick="openGalleryViewer('${img.id}')">
                 ${isVideo ? '<span class="gallery-card-play"></span>' : `<img src="${src}" loading="lazy" decoding="async" onerror="this.closest('.gallery-card').classList.add('broken')">`}
                <button class="gallery-card-heart" onclick="event.stopPropagation();toggleGalleryFav('${img.id}')">${img.favourite ? '♥' : '♡'}</button>
            </div>
        `;
    });
    grid.innerHTML = html;

    let pHtml = '<button onclick="loadGallery(1)" ' + (page<=1?'disabled':'') + '>«</button>';
    pHtml += '<button onclick="loadGallery('+(page-1)+')" ' + (page<=1?'disabled':'') + '>‹</button>';
    const range = paginationRange(page, total_pages);
    range.forEach(p => {
        pHtml += `<button onclick="loadGallery(${p})" ${p===page?'class="active"':''}>${p}</button>`;
    });
    pHtml += '<button onclick="loadGallery('+(page+1)+')" ' + (page>=total_pages?'disabled':'') + '>›</button>';
    pHtml += '<button onclick="loadGallery('+total_pages+')" ' + (page>=total_pages?'disabled':'') + '>»</button>';
    pHtml += `<span>${total} images</span>`;
    pagination.innerHTML = pHtml;
    applyGalleryZoom();
}

async function copyImageToClipboard(fp, btn) {
    btn.textContent = '...';
    try {
        const resp = await fetch(window.location.origin + '/api/gallery/file/' + fp);
        const blob = await resp.blob();
        const item = {};
        item[blob.type] = blob;
        try {
            await navigator.clipboard.write([new ClipboardItem(item)]);
        } catch (_) {
            const png = await toPngBlob(blob);
            await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
        }
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = '⧉'; }, 1500);
    } catch (err) {
        console.error('Copy failed:', err);
        btn.textContent = '⧉';
    }
}

function toPngBlob(blob) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        const url = URL.createObjectURL(blob);
        img.onload = () => {
            const c = document.createElement('canvas');
            c.width = img.naturalWidth; c.height = img.naturalHeight;
            c.getContext('2d').drawImage(img, 0, 0);
            c.toBlob(b => { URL.revokeObjectURL(url); b ? resolve(b) : reject(); }, 'image/png');
        };
        img.onerror = () => { URL.revokeObjectURL(url); reject(); };
        img.src = url;
    });
}

function copyViewerImage(el) {
    const img = galleryState.images[viewerIndex];
    if (!img) return;
    const fp = (img.filepath || '').replace(/\\/g, '/');
    copyImageToClipboard(encodeURI(fp), el);
}

function paginationRange(current, total) {
    if (total <= 7) return Array.from({length: total}, (_,i)=>i+1);
    const range = [];
    if (current <= 4) { for (let i=1; i<=5; i++) range.push(i); range.push(0, total); }
    else if (current >= total-3) { range.push(1, 0); for (let i=total-4; i<=total; i++) range.push(i); }
    else { range.push(1, 0); for (let i=current-1; i<=current+1; i++) range.push(i); range.push(0, total); }
    return range;
}

function toggleFavFilter() {
    galleryFavFilter = !galleryFavFilter;
    document.getElementById("galleryFavBtn").classList.toggle("active", galleryFavFilter);
    loadGallery(1);
}

async function toggleGalleryFav(id) {
    try {
        let resp = await fetch("/api/gallery/favourite", {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id})
        });
        if (resp.ok) loadGallery();
    } catch (e) { console.error("Fav toggle error:", e); }
}

let viewerIndex = -1;
let viewerZoom = 1;

function openGalleryViewer(id) {
    viewerIndex = galleryState.images.findIndex(i => i.id === id);
    if (viewerIndex < 0) return;
    viewerZoom = 1;
    showViewerImage();
}

function showViewerImage() {
    const viewer = document.getElementById("galleryViewer");
    const viewerImg = document.getElementById("galleryViewerImg");
    const img = galleryState.images[viewerIndex];
    if (!img) return closeGalleryViewer();

    viewerImg.src = '';
    let vw = document.querySelector('.gallery-video-wrap');
    if (vw) { vw.remove(); }

    const safeFp = (img.filepath || '').replace(/\\/g, '/');
    const fullSrc = safeFp ? `/api/gallery/file/${encodeURI(safeFp)}` : '';
    const ext = ((img.filename || '').split('.').pop() || '').toLowerCase();
    const isVideo = ['mp4','webm','mov','avi','mkv'].includes(ext);

    viewerImg.className = '';
    viewerImg.style.transform = '';
    viewerDrag.active = false;
    const zl = document.getElementById("galleryViewerZoom");
    zl.textContent = '100%';
    zl.classList.remove('show');
    viewerZoom = 1;

    if (isVideo) {
        viewerImg.style.display = 'none';
        const old = document.querySelector('.gallery-video-wrap');
        if (old) old.remove();
        const wrap = document.createElement('div');
        wrap.className = 'gallery-video-wrap';
        const video = document.createElement('video');
        video.id = 'galleryViewerVideo';
        video.src = fullSrc;
        const ctrls = document.createElement('div');
        ctrls.className = 'gallery-video-ctrls';
        ctrls.innerHTML = `
            <button class="gv-play-btn">&#9654;</button>
            <div class="gv-progress-wrap"><div class="gv-progress"><div class="gv-progress-fill"></div><div class="gv-progress-thumb"></div></div></div>
            <span class="gv-time">0:00 / 0:00</span>
            <button class="gv-vol-btn">&#9835;</button>
            <input type="range" class="gv-vol-slider" min="0" max="1" step="0.05" value="1">
            <button class="gv-fs-btn">&#x26F6;</button>
        `;
        wrap.append(video, ctrls);
        viewer.insertBefore(wrap, viewerImg.nextSibling);
        const playBtn = ctrls.querySelector('.gv-play-btn');
        const progressFill = ctrls.querySelector('.gv-progress-fill');
        const progressThumb = ctrls.querySelector('.gv-progress-thumb');
        const progressWrap = ctrls.querySelector('.gv-progress-wrap');
        const timeEl = ctrls.querySelector('.gv-time');
        const volBtn = ctrls.querySelector('.gv-vol-btn');
        const volSlider = ctrls.querySelector('.gv-vol-slider');
        function fmt(t) { const m = Math.floor(t/60); const s = Math.floor(t%60); return m+':'+(s<10?'0':'')+s; }
        video.addEventListener('loadedmetadata', () => { timeEl.textContent = '0:00 / '+fmt(video.duration); });
        video.addEventListener('timeupdate', () => {
            const pct = video.duration ? (video.currentTime/video.duration*100) : 0;
            progressFill.style.width = pct+'%'; progressThumb.style.left = pct+'%';
            timeEl.textContent = fmt(video.currentTime)+' / '+fmt(video.duration);
        });
        function togglePlay() { if (video.paused) { video.play(); playBtn.innerHTML='&#9646;&#9646;'; } else { video.pause(); playBtn.innerHTML='&#9654;'; } }
        playBtn.onclick = togglePlay;
        video.onclick = togglePlay;
        video.addEventListener('play', () => playBtn.innerHTML='&#9646;&#9646;');
        video.addEventListener('pause', () => playBtn.innerHTML='&#9654;');
        progressWrap.onclick = (e) => {
            const r = progressWrap.getBoundingClientRect();
            video.currentTime = ((e.clientX-r.left)/r.width)*video.duration;
        };
        volSlider.oninput = () => { video.volume = volSlider.value; volBtn.textContent = volSlider.value=='0'?'X':volSlider.value<0.5?'♪':'♫'; };
        video.addEventListener('volumechange', () => { volSlider.value = video.volume; });
        video.addEventListener('ended', () => playBtn.innerHTML='&#9654;');
        const fsBtn = ctrls.querySelector('.gv-fs-btn');
        fsBtn.onclick = (e) => { e.stopPropagation();
            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                if (video.requestFullscreen) video.requestFullscreen();
                else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
            } else {
                if (document.exitFullscreen) document.exitFullscreen();
                else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
            }
        };
        function fsIcon() { fsBtn.innerHTML = (document.fullscreenElement || document.webkitFullscreenElement) ? '&#x2715;' : '&#x26F6;'; }
        document.addEventListener('fullscreenchange', fsIcon);
        document.addEventListener('webkitfullscreenchange', fsIcon);
        video.play();
    } else {
        viewerImg.style.display = '';
        viewerImg.src = fullSrc;
    }

    document.getElementById("galleryViewerFav").textContent = img.favourite ? '♥' : '♡';
    viewer.style.display = 'flex';
}

function closeGalleryViewer() {
    document.getElementById("galleryViewer").style.display = 'none';
    document.getElementById("galleryViewerImg").src = '';
    document.getElementById("galleryViewerImg").className = '';
    document.getElementById("galleryViewerImg").style.transform = '';
    const vw = document.querySelector('.gallery-video-wrap');
    if (vw) { vw.remove(); }
    viewerZoom = 1;
    viewerIndex = -1;
    viewerDrag.active = false;
}

function viewerNav(dir) {
    const total = galleryState.images.length;
    const newIdx = viewerIndex + dir;
    if (newIdx < 0 && currentGalleryPage > 1) {
        loadGalleryPage(currentGalleryPage - 1, () => { viewerIndex = galleryState.images.length - 1; showViewerImage(); });
        return;
    }
    if (newIdx >= total && currentGalleryPage < galleryState.total_pages) {
        loadGalleryPage(currentGalleryPage + 1, () => { viewerIndex = 0; showViewerImage(); });
        return;
    }
    if (newIdx >= total && currentGalleryPage >= galleryState.total_pages) {
        showToast("Last image");
        return;
    }
    if (newIdx < 0 && currentGalleryPage <= 1) { return; }
    viewerIndex = newIdx;
    viewerZoom = 1;
    showViewerImage();
}

function toggleViewerFav() {
    const img = galleryState.images[viewerIndex];
    if (!img) return;
    img.favourite = !img.favourite;
    document.getElementById("galleryViewerFav").textContent = img.favourite ? '♥' : '♡';
    fetch("/api/gallery/favourite", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: img.id})
    }).catch(e => console.error("Fav toggle error:", e));
}

function getViewerTransform() {
    const img = document.getElementById("galleryViewerImg");
    const cur = img.style.transform;
    const m = cur.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/);
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : [0, 0];
}

function setViewerTransform(tx, ty) {
    const img = document.getElementById("galleryViewerImg");
    const zoomed = viewerZoom > 1;
    img.className = zoomed ? 'zoomed' : '';
    if (zoomed) {
        img.style.transform = `translate(${tx}px, ${ty}px) scale(${viewerZoom})`;
    } else {
        img.style.transform = '';
    }
}

function zoomViewer(delta, cx, cy) {
    const img = document.getElementById("galleryViewerImg");
    if (img.style.display === 'none') return;
    const old = viewerZoom;
    viewerZoom = Math.max(0.25, Math.min(10, viewerZoom + delta));
    const zoomed = viewerZoom > 1;
    if (!zoomed) {
        setViewerTransform(0, 0);
        stopViewerDrag();
        const label = document.getElementById("galleryViewerZoom");
        label.textContent = Math.round(viewerZoom * 100) + '%';
        label.classList.remove('show');
        return;
    }
    const rect = img.getBoundingClientRect();
    const [tx, ty] = getViewerTransform();
    const ratio = viewerZoom / old;
    let newTx, newTy;
    if (cx != null && cy != null) {
        const mx = cx - rect.left;
        const my = cy - rect.top;
        newTx = tx + mx * (1 - ratio);
        newTy = ty + my * (1 - ratio);
    } else {
        newTx = tx + (rect.width / 2) * (1 - ratio);
        newTy = ty + (rect.height / 2) * (1 - ratio);
    }
    setViewerTransform(newTx, newTy);
    const label = document.getElementById("galleryViewerZoom");
    label.textContent = Math.round(viewerZoom * 100) + '%';
    label.classList.add('show');
}

document.addEventListener('keydown', function(e) {
    const viewer = document.getElementById("galleryViewer");
    if (viewer && viewer.style.display === 'flex') {
        if (e.key === 'Escape') closeGalleryViewer();
        else if (e.key === 'ArrowLeft') viewerNav(-1);
        else if (e.key === 'ArrowRight') viewerNav(1);
        else if (e.key === '+' || e.key === '=') zoomViewer(0.05, window.innerWidth/2, window.innerHeight/2);
        else if (e.key === '-') zoomViewer(-0.05, window.innerWidth/2, window.innerHeight/2);
    } else if (document.getElementById("Gallery") && document.getElementById("Gallery").style.display !== 'none') {
        if (e.key === '+' || e.key === '=') galleryZoom(0.2);
        else if (e.key === '-') galleryZoom(-0.2);
    }
});

let viewerDrag = { active: false, startX: 0, startY: 0, imgX: 0, imgY: 0 };

document.getElementById("galleryViewer").addEventListener('click', function(e) {
    if (e.target === this) closeGalleryViewer();
});

let zoomThrottle = 0;
document.getElementById("galleryViewer").addEventListener('wheel', function(e) {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const now = Date.now();
    if (now - zoomThrottle < 80) return;
    zoomThrottle = now;
    zoomViewer(e.deltaY < 0 ? 0.05 : -0.05, e.clientX, e.clientY);
}, { passive: false });

function stopViewerDrag() {
    viewerDrag.active = false;
    const img = document.getElementById("galleryViewerImg");
    if (img) img.classList.remove('dragging');
}

document.getElementById("galleryViewerImg").addEventListener('mousedown', function(e) {
    if (viewerZoom <= 1 || e.button !== 0) return;
    e.preventDefault();
    viewerDrag.active = true;
    viewerDrag.startX = e.clientX;
    viewerDrag.startY = e.clientY;
    const t = getViewerTransform();
    viewerDrag.imgX = t[0];
    viewerDrag.imgY = t[1];
    this.classList.add('dragging');
});

document.addEventListener('mousemove', function(e) {
    if (!viewerDrag.active) return;
    e.preventDefault();
    const dx = e.clientX - viewerDrag.startX;
    const dy = e.clientY - viewerDrag.startY;
    setViewerTransform(viewerDrag.imgX + dx, viewerDrag.imgY + dy);
});

document.addEventListener('mouseup', stopViewerDrag);
document.addEventListener('mouseleave', stopViewerDrag);

async function importGallery() {
    if (localStorage.getItem('gallery_imported')) return;
    try {
        let resp = await fetch("/api/gallery/import", {method: "POST"});
        let data = await resp.json();
        if (data.success) {
            localStorage.setItem('gallery_imported', '1');
            loadGallery(1);
            populateGallerySiteFilter();
        }
    } catch (e) { console.error("Import error:", e); }
}

async function rescanGallery() {
    try {
        let resp = await fetch("/api/gallery/rescan", {method: "POST"});
        let data = await resp.json();
        if (data.success) {
            alert(`Rescan complete. Added ${data.added} new images, removed ${data.removed} missing entries.`);
            loadGallery(1);
            populateGallerySiteFilter();
        }
    } catch (e) { console.error("Rescan error:", e); }
}

function toggleCheck(el) {
    const cb = el.querySelector('input[type="checkbox"]');
    const menu = el.closest('.gallery-dropdown-menu');
    if (cb.value !== '') {
        const allCheck = menu.querySelector('input[value=""]');
        if (allCheck && allCheck.checked) allCheck.checked = false;
    }
    cb.checked = !cb.checked;
    if (menu.id === 'sourceDropdown') onSourceChange();
    else if (menu.id === 'ratingDropdown') onRatingChange();
    else if (menu.id === 'typeDropdown') onTypeChange();
}

async function populateGallerySiteFilter() {
    const container = document.getElementById("sourceDropdown");
    container.innerHTML = '<div class="dd-item" onclick="toggleCheck(this)"><span>All</span><input type="checkbox" value="" checked></div>';
    try {
        let resp = await fetch("/api/gallery/sources");
        const counts = await resp.json();
        const sorted = Object.entries(counts).sort((a,b) => a[0].localeCompare(b[0]));
        sorted.forEach(([site, count]) => {
            const div = document.createElement("div");
            div.className = "dd-item";
            div.onclick = function() { toggleCheck(this); };
            div.innerHTML = `<span>${site} (${count})</span><input type="checkbox" value="${site}">`;
            container.appendChild(div);
        });
    } catch (e) {}
    updateSourceDropdown();
}

function toggleDropdown(id) {
    const menu = document.getElementById(id);
    document.querySelectorAll('.gallery-dropdown-menu.open').forEach(m => { if (m.id !== id) m.classList.remove('open'); });
    menu.classList.toggle('open');
}

function onSourceChange() {
    const checks = document.querySelectorAll('#sourceDropdown input[type="checkbox"]');
    const allCheck = checks[0];
    if (allCheck.checked) {
        for (let i = 1; i < checks.length; i++) checks[i].checked = false;
    } else {
        let anyChecked = false;
        for (let i = 1; i < checks.length; i++) { if (checks[i].checked) { anyChecked = true; break; } }
        if (!anyChecked) allCheck.checked = true;
    }
    const btn = document.querySelector('[onclick="toggleDropdown(\'sourceDropdown\')"]');
    if (btn) btn.textContent = getMultiLabel('sourceDropdown', 'All Sources') + ' ▾';
    updateRatingDropdown();
    loadGallery(1);
}

function onRatingChange() {
    const checks = document.querySelectorAll('#ratingDropdown input[type="checkbox"]');
    const allCheck = checks[0];
    if (allCheck.checked) {
        for (let i = 1; i < checks.length; i++) checks[i].checked = false;
    } else {
        let anyChecked = false;
        for (let i = 1; i < checks.length; i++) { if (checks[i].checked) { anyChecked = true; break; } }
        if (!anyChecked) allCheck.checked = true;
    }
    const btn = document.querySelector('[onclick="toggleDropdown(\'ratingDropdown\')"]');
    if (btn) btn.textContent = getMultiLabel('ratingDropdown', 'All Ratings') + ' ▾';
    updateSourceDropdown();
    loadGallery(1);
}

function onTypeChange() {
    const checks = document.querySelectorAll('#typeDropdown input[type="checkbox"]');
    const allCheck = checks[0];
    if (allCheck.checked) {
        for (let i = 1; i < checks.length; i++) checks[i].checked = false;
    } else {
        let anyChecked = false;
        for (let i = 1; i < checks.length; i++) { if (checks[i].checked) { anyChecked = true; break; } }
        if (!anyChecked) allCheck.checked = true;
    }
    const btn = document.querySelector('[onclick="toggleDropdown(\'typeDropdown\')"]');
    if (btn) btn.textContent = getMultiLabel('typeDropdown', 'All Types') + ' ▾';
    loadGallery(1);
}

function selectSort(el, value) {
    document.getElementById("sortDropdown").dataset.sort = value;
    const btn = document.querySelector('[onclick="toggleDropdown(\'sortDropdown\')"]');
    btn.textContent = el.textContent.trim() + ' ▾';
    document.getElementById("sortDropdown").classList.remove('open');
    loadGallery(1);
}

function updatePixivMode() {
    let mode = document.getElementById("pixivMode").value;
    let rankingDropdown = document.getElementById("pixivRankingMode");
    let tagInput = document.getElementById("pixivTag");

    if (mode === "ranking") {
        rankingDropdown.style.display = "inline-block";
        tagInput.placeholder = "Ranking mode ignores value field";
        tagInput.style.display = "none";
    } else {
        rankingDropdown.style.display = "none";
        tagInput.style.display = "inline-block";
        if (mode === "search") tagInput.placeholder = "tag name (e.g. blue_hair)";
        else if (mode === "bookmark") tagInput.placeholder = "user ID";
        else tagInput.placeholder = "user ID";
    }
}

async function submitPixivCode() {
    let code = document.getElementById('pixivCodeInput').value.trim();
    let statusEl = document.getElementById('pixivCodeStatus');
    if (!code) {
        statusEl.textContent = 'Enter the code first.';
        return;
    }
    try {
        let resp = await fetch('/api/pixiv/submit_code', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({code: code})
        });
        let result = await resp.json();
        if (result.success) {
            statusEl.textContent = 'Code submitted - waiting for login to complete...';
            document.getElementById('pixivCodeInput').value = '';
        } else {
            statusEl.textContent = '✗ ' + (result.error || 'Submit failed');
        }
    } catch (e) {
        statusEl.textContent = '✗ Network error';
    }
}

function showToast(msg) {
    const el = document.getElementById('galleryToast') || (() => {
        const t = document.createElement('div');
        t.id = 'galleryToast';
        t.style.cssText = 'position:fixed;bottom:40px;left:50%;transform:translateX(-50%);background:#222;color:#eee;padding:10px 24px;border-radius:8px;font-size:14px;z-index:2000;opacity:0;transition:opacity 0.3s;pointer-events:none;';
        document.body.appendChild(t);
        return t;
    })();
    el.textContent = msg;
    el.style.opacity = '1';
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.style.opacity = '0'; }, 2000);
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.gallery-dropdown')) {
        document.querySelectorAll('.gallery-dropdown-menu.open').forEach(m => m.classList.remove('open'));
    }
});