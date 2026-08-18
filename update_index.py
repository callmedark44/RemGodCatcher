import re

with open('E:/RemGodCatcher new/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove Scanning API text and progress bar
content = re.sub(
    r'<div style="display:flex; justify-content:space-between; font-size:12px;"><span>🔍 Scanning API\.\.\.</span>.*?</div>\s*<div class="progress-bar-bg"><div class="progress-bar-fill scan-fill" id="scanBar_[a-zA-Z0-9_]+"></div></div>',
    '',
    content,
    flags=re.DOTALL
)

# 2. Update <input list="..." ...><datalist></datalist> to the new structure
def replace_datalist(match):
    full_input = match.group(0)
    # Extract id
    id_match = re.search(r'id="([^"]+)"', full_input)
    if not id_match:
        return full_input
    
    input_id = id_match.group(1)
    
    if "rule34TagInput" in input_id:
        return full_input # Rule34 already uses its own styled input
        
    if "eshuushuuTag" in input_id or "nekosapiTag" in input_id or "nekosiaTag" in input_id:
        return full_input # Already styled

    # Remove list attribute and datalist element, and inline oninput
    cleaned_input = re.sub(r'list="[^"]+"\s*', '', match.group(1))
    cleaned_input = re.sub(r'oninput="[^"]+"\s*', '', cleaned_input)
    
    # Add width and autocomplete
    if 'style="' in cleaned_input:
        cleaned_input = re.sub(r'style="([^"]*)"', r'style="\1; width: 100%;" autocomplete="off"', cleaned_input)
    else:
        cleaned_input = cleaned_input.replace('<input ', '<input style="width: 100%;" autocomplete="off" ')
        
    autosuggest_id = input_id.replace('Tag', 'Autosuggest').replace('Dl', 'Dl')
    if "animeDl" in input_id: autosuggest_id = "animeDlAutosuggest"
    if "gelbooru" in input_id: autosuggest_id = "gelbooruAutosuggest"
    if "safe" in input_id: autosuggest_id = "safeAutosuggest"
    if "sankaku" in input_id: autosuggest_id = "sankakuAutosuggest"
    if "dan" in input_id: autosuggest_id = "danAutosuggest"
    if "kona" in input_id: autosuggest_id = "konaAutosuggest"
    if "yande" in input_id: autosuggest_id = "yandeAutosuggest"
    if "zero" in input_id: autosuggest_id = "zeroAutosuggest"

    return f'<div style="flex:1; position: relative;">\n                        {cleaned_input}\n                        <div id="{autosuggest_id}" class="autosuggest-dropdown" style="display:none; right: 0;"></div>\n                    </div>'

content = re.sub(r'(<input type="text" id="[^"]+" list="[^"]+"[^>]+>)\s*<datalist id="[^"]+"></datalist>', replace_datalist, content)

with open('E:/RemGodCatcher new/web/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated index.html")
