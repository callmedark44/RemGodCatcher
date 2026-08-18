import glob, re

for fp in glob.glob('E:/RemGodCatcher new/workers/*.py'):
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
        
    new_content = re.sub(
        r'self\.log\(f"✅ Finished scanning API\. Total valid items found: \{actual\}"\)',
        'self.check_amount_warning(actual)',
        content
    )
    
    if new_content != content:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Patched {fp}")
