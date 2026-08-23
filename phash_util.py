#!/usr/bin/env python3
"""Standalone pHash computation — no side effects, safe for ProcessPoolExecutor workers."""
import os, json
import numpy as np
from PIL import Image

_DCT_N = 32
_DCT_COS = None

def _build_dct():
    global _DCT_COS
    N = _DCT_N
    C = np.zeros((N, N))
    for k in range(N):
        a = np.sqrt(1/N) if k == 0 else np.sqrt(2/N)
        for n in range(N):
            C[k, n] = a * np.cos(np.pi * k * (2*n + 1) / (2*N))
    _DCT_COS = C

def phash(path):
    if _DCT_COS is None:
        _build_dct()
    img = Image.open(path).convert('L').resize((_DCT_N, _DCT_N), Image.LANCZOS)
    pix = np.array(img, dtype=float)
    dct = _DCT_COS @ pix @ _DCT_COS.T
    top = dct[:8, :8]
    med = np.median(top)
    bits = (top > med).flatten()
    hv = 0
    for b in bits:
        hv = (hv << 1) | int(b)
    return format(hv, '016x')

# ==========================================
# === DUPLICATE DETECTION ===
# ==========================================
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
CACHE_NAME = ".phash_cache.json"

def find_duplicates(root):
    """Walk root, return {hash: [paths]} for images sharing a pHash.
    ponytail: mtime+size cache so only new/changed files get hashed each run."""
    cache_path = os.path.join(root, CACHE_NAME)
    try:
        cache = json.load(open(cache_path))
    except Exception:
        cache = {}
    groups = {}
    seen_keys = set()
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(IMAGE_EXTS):
                continue
            path = os.path.join(dirpath, fn)
            try:
                st = os.stat(path)
            except OSError:
                continue
            seen_keys.add(path)
            ent = cache.get(path)
            if ent and ent[0] == st.st_mtime and ent[1] == st.st_size:
                h = ent[2]
            else:
                try:
                    h = phash(path)
                except Exception:
                    continue
                cache[path] = [st.st_mtime, st.st_size, h]
            groups.setdefault(h, []).append(path)
    cache = {k: v for k, v in cache.items() if k in seen_keys}
    try:
        json.dump(cache, open(cache_path, "w"))
    except Exception:
        pass
    return {h: ps for h, ps in groups.items() if len(ps) > 1}

def pick_keeper(paths):
    """Of the duplicates, keep the one whose subfolder holds the most files."""
    def population(p):
        try:
            return len(os.listdir(os.path.dirname(p)))
        except OSError:
            return 0
    # tie-break: keep the oldest download
    return max(paths, key=lambda p: (population(p), -os.path.getmtime(p)))

def iter_images(root):
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(IMAGE_EXTS):
                yield os.path.join(dirpath, fn)

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "image_phashes.json")

def load_index():
    try:
        return json.load(open(INDEX_PATH))
    except Exception:
        return {}

def save_index(index):
    try:
        json.dump(index, open(INDEX_PATH, "w"))
    except Exception:
        pass
