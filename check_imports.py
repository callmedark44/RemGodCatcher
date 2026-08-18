import sys
import os

# Add the current directory to the path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import Rem_catcher
    import database
    import shared
    import multi_agent
    import workers
    from workers import pinterest_worker
    from workers import anime_dl
    from workers import zerochan
    from workers import sankaku
    from workers import konachan
    from workers import yande
    from workers import waifu_im
    from workers import nekos_life
    from workers import nekos_best
    from workers import safebooru
    from workers import rule34
    from workers import gelbooru
    from workers import danbooru
    print("All imports successful!")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)