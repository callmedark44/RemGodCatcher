// --- INITIALIZATION ---
let globalNetConfig = { "proxy_url": "", "use_proxy": false, "verify_tls": false };
window.nekoData = { image: [], gif: [] };

window.onload = async function() {
    let config = await eel.get_startup_config()();
    if (config) globalNetConfig = config;

    let currentFolder = await eel.get_current_folder()();
    if (currentFolder) document.getElementById("folderDisplay").innerText = currentFolder;

    await loadNekoCategories();
    document.getElementById("nekoCat").onclick = function() {
        if(this.value.includes("Network Error")) {
            this.value = "Retrying...";
            loadNekoCategories();
        }
    };

    let waifuTags = await eel.get_waifu_tags(globalNetConfig)();
    let wl = document.getElementById("waifuList");
    wl.innerHTML = "";
    waifuTags.forEach(t => wl.innerHTML += `<option value="${t}">`);
    if (waifuTags.length > 0) document.getElementById("waifuTag").value = waifuTags[0];
};

async function loadNekoCategories() {
    let data = await eel.get_neko_tags(globalNetConfig)();
    if (data.image.length === 0 && data.gif.length === 0) {
        document.getElementById("nekoCat").value = "Network Error (Click to Retry)";
    } else {
        window.nekoData = data;
        updateNekoDropdown();
    }
}

async function browseFolder() {
    let newFolder = await eel.choose_folder_py()();
    if (newFolder) {
        document.getElementById("folderDisplay").innerText = newFolder;
        logToConsole("main", `Master folder updated to: ${newFolder}`);
    }
}

function updateNekoDropdown() {
    let fmt = document.getElementById("nekoFormat").value;
    let nl = document.getElementById("nekoList");
    nl.innerHTML = "";
    
    let targetList = [];
    if (fmt === "Images (PNG)") targetList = window.nekoData.image;
    else if (fmt === "GIFs (Animations)") targetList = window.nekoData.gif;
    else targetList = window.nekoData.image.concat(window.nekoData.gif).sort();

    targetList.forEach(t => nl.innerHTML += `<option value="${t}">`);
    if (targetList.length > 0) document.getElementById("nekoCat").value = targetList[0];
}

async function fetchZero(val) {
    if(val.length < 3) return;
    let tags = await eel.get_zerochan_suggestions(val, globalNetConfig)();
    let dl = document.getElementById("zeroList");
    dl.innerHTML = "";
    tags.forEach(t => dl.innerHTML += `<option value="${t}">`);
}

async function fetchSafe(val) {
    if(val.length < 2) return;
    let words = val.split(" ");
    let lastWord = words[words.length - 1];
    if(lastWord.length < 2) return;

    let tags = await eel.get_safe_suggestions(lastWord)();
    let dl = document.getElementById("safeList");
    dl.innerHTML = "";
    tags.forEach(t => {
        let suggestion = words.slice(0, -1).join(" ") + (words.length > 1 ? " " : "") + t;
        dl.innerHTML += `<option value="${suggestion}">`;
    });
}

// --- THE LIVE RULE34 TAG ENGINE ---
async function fetchRule34(val) {
    if(val.length < 2) return;
    let tags = await eel.get_rule34_suggestions(val, globalNetConfig)();
    let dl = document.getElementById("rule34List");
    dl.innerHTML = "";
    tags.forEach(t => dl.innerHTML += `<option value="${t}">`);
}

function openTab(tabName, wallpaperFile, btn) {
    let contents = document.getElementsByClassName("tab-content");
    for (let i = 0; i < contents.length; i++) contents[i].style.display = "none";

    let buttons = document.getElementsByClassName("tab-btn");
    for (let i = 0; i < buttons.length; i++) buttons[i].classList.remove("active");

    document.getElementById(tabName).style.display = "block";
    btn.classList.add("active");
    document.body.style.backgroundImage = `url('wallpaper/${wallpaperFile}')`;
}

eel.expose(pythonLog);
function pythonLog(tabID, msg) {
    logToConsole(tabID, msg);
}

function logToConsole(tabID, msg) {
    let boxMap = {
        "main": "consoleLog_main",
        "neko": "consoleLog_neko",
        "zero": "consoleLog_zero",
        "waifu": "consoleLog_waifu",
        "safe": "consoleLog_safe",
        "rule34": "consoleLog_rule34"
    };
    
    let targetBoxId = boxMap[tabID.toLowerCase()] || "consoleLog_main";
    let consoleBox = document.getElementById(targetBoxId);
    
    if (consoleBox) {
        let time = new Date().toLocaleTimeString();
        consoleBox.innerHTML += `[${time}] ${msg}\n`;
        consoleBox.scrollTop = consoleBox.scrollHeight;
    }
}

function startWorker(workerName) {
    try {
        if (workerName === 'zero') {
            let tag = document.getElementById('zeroTag').value;
            let limit = document.getElementById('zeroLimit').value;
            if(!tag) return logToConsole('zero', '❌ Error: Tag Name cannot be empty!');
            eel.start_zerochan(tag, limit, globalNetConfig)();
        } 
        else if (workerName === 'waifu') {
            let tag = document.getElementById('waifuTag').value;
            let limit = document.getElementById('waifuLimit').value;
            let nsfw = document.getElementById('waifuNsfw').checked;
            if(!tag) return logToConsole('waifu', '❌ Error: Tag Name cannot be empty!');
            eel.start_waifu(tag, limit, nsfw, globalNetConfig)();
        }
        else if (workerName === 'neko') {
            let tag = document.getElementById('nekoCat').value;
            let limit = document.getElementById('nekoAmount').value;
            if(!tag) return logToConsole('neko', '❌ Error: Category cannot be empty!');
            eel.start_neko(tag, limit, globalNetConfig)();
        }
        else if (workerName === 'safe') {
            let tag = document.getElementById('safeTag').value;
            let limit = document.getElementById('safeLimit').value;
            if(!tag) return logToConsole('safe', '❌ Error: Search Tags cannot be empty!');
            eel.start_safe(tag, limit, globalNetConfig)();
        }
        else if (workerName === 'rule34') {
            let tag = document.getElementById('rule34Tag').value;
            let limit = document.getElementById('rule34Limit').value;
            let method = document.getElementById('rule34Method').value;
            let sortType = document.getElementById('rule34SortType').value;
            let sortOrder = document.getElementById('rule34SortOrder').value;

            if(!tag) return logToConsole('rule34', '❌ Error: Search Tags cannot be empty!');
            
            // خواندن وضعیت چک‌باکس‌های فیلتر
            let exclusions = [];
            if (document.getElementById('exVideo').checked) exclusions.push('-video');
            if (document.getElementById('exGif').checked) exclusions.push('-gif');
            if (document.getElementById('exComic').checked) exclusions.push('-comic');
            if (document.getElementById('ex3D').checked) exclusions.push('-3d');

            // ارسال تمام پارامترها به هسته پایتون
            eel.start_rule34(tag, limit, method, sortType, sortOrder, exclusions, globalNetConfig)();
        }
    } catch (e) {
        logToConsole('main', `❌ UI Error: ${e}`);
    }
}

function stopWorker(workerName) { 
    eel.stop_worker(workerName)(); 
}