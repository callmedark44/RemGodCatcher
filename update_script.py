import re

with open('E:/RemGodCatcher new/web/script.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove scan update logic in startWorker
content = re.sub(
    r'let scanBar = document\.getElementById\("scanBar_" \+ key\);\s*let scanCount = document\.getElementById\("scanCount_" \+ key\);\s*let dlBar = document\.getElementById\("dlBar_" \+ key\);\s*let dlText = document\.getElementById\("dlText_" \+ key\);\s*if \(container && scanBar && scanCount && dlBar && dlText\) \{\s*container\.style\.display = "flex";\s*scanBar\.style\.width = "100%";\s*scanBar\.style\.animation = "progressShimmer 1\.5s linear infinite";\s*scanCount\.textContent = "Found: 0";\s*dlBar\.style\.width = "0%";\s*dlText\.textContent = "0%";\s*\}',
    'let dlBar = document.getElementById("dlBar_" + key);\n        let dlText = document.getElementById("dlText_" + key);\n\n        if (container && dlBar && dlText) {\n            container.style.display = "flex";\n            dlBar.style.width = "0%";\n            dlText.textContent = "0%";\n        }',
    content
)

# Remove scan logic in updateProgressBar
content = re.sub(
    r'if \(msg\.includes\("Phase 1"\)\) \{.*?return;\s*\}',
    'if (msg.includes("Phase 1")) {\n        container.innerHTML = \n            <div style="display:flex; justify-content:space-between; font-size:12px; margin-top:10px; margin-bottom:5px;">\n                <span>🚀 Downloading...</span>\n                <span id="dlText_">0%</span>\n            </div>\n            <div class="progress-bar-bg"><div class="progress-bar-fill dl-fill" id="dlBar_" style="width:0%;"></div></div>\n        ;\n        container.style.display = "block";\n        return;\n    }',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'let scanTitle = document\.getElementById\("scanTitle_" \+ key\);\s*let scanCount = document\.getElementById\("scanCount_" \+ key\);\s*',
    '',
    content
)

content = re.sub(
    r'if \(!scanTitle \|\| !scanCount \|\| !dlBar \|\| !dlText\) return;',
    'if (!dlBar || !dlText) return;',
    content
)

content = re.sub(
    r'// آپدیت متن اسکن\s*if \(msg\.includes\("Total valid items found:"\)\) \{.*?return;\s*\}',
    '',
    content,
    flags=re.DOTALL
)

# Replace the individual fetch functions with setupAutosuggest calls
autosuggest_setup = """
    setupAutosuggest("animeDlTag", "animeDlAutosuggest", "/api/tags/anime_dl");
    setupAutosuggest("danTag", "danAutosuggest", "/api/tags/dan");
    setupAutosuggest("gelbooruTag", "gelbooruAutosuggest", "/api/tags/gelbooru");
    setupAutosuggest("konaTag", "konaAutosuggest", "/api/tags/kona");
    setupAutosuggest("safeTag", "safeAutosuggest", "/api/tags/safe");
    setupAutosuggest("sankakuTag", "sankakuAutosuggest", "/api/tags/sankaku");
    setupAutosuggest("yandeTag", "yandeAutosuggest", "/api/tags/yande");
    setupAutosuggest("zeroTag", "zeroAutosuggest", "/api/tags/zerochan");
"""

content = content.replace(
    'setupAutosuggest("nekosiaTag", "nekosiaAutosuggest", "/api/tags/nekosia");',
    'setupAutosuggest("nekosiaTag", "nekosiaAutosuggest", "/api/tags/nekosia");' + autosuggest_setup
)

dropdowns_array = '["eshuushuuAutosuggest", "nekosapiAutosuggest", "nekosiaAutosuggest"' + ', "animeDlAutosuggest", "danAutosuggest", "gelbooruAutosuggest", "konaAutosuggest", "safeAutosuggest", "sankakuAutosuggest", "yandeAutosuggest", "zeroAutosuggest"]'
inputs_array = '["eshuushuuTag", "nekosapiTag", "nekosiaTag"' + ', "animeDlTag", "danTag", "gelbooruTag", "konaTag", "safeTag", "sankakuTag", "yandeTag", "zeroTag"]'

content = re.sub(r'let dropdowns = \[[^\]]+\];', f'let dropdowns = {dropdowns_array};', content)
content = re.sub(r'let inputs = \[[^\]]+\];', f'let inputs = {inputs_array};', content)

# Remove old fetchXXX functions
content = re.sub(r'async function fetch[a-zA-Z]+\(val\) \{.*?\}\s*', '', content, flags=re.DOTALL)

with open('E:/RemGodCatcher new/web/script.js', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated script.js")
