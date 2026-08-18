import os, glob

# Let's check rule34, gelbooru, safebooru, yande, konachan, danbooru

def patch_worker(filepath, count_var, insert_after):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "Total valid items found:" in content:
        return # Already patched or has it

    # This is a bit tricky to generalize, so I will just write custom patches
    pass
