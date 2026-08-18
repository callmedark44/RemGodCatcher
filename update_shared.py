import re

with open('E:/RemGodCatcher new/shared.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add self.failed_count to __init__
content = re.sub(
    r'self\.downloaded_count = 0\s*self\.downloaded_bytes = 0',
    'self.downloaded_count = 0\n        self.failed_count = 0\n        self.downloaded_bytes = 0',
    content
)

# Increment failed_count on error
content = re.sub(
    r'self\.log\(f"\[FAILED\] \{filename\}: \{err_msg\}"\)\s*return False',
    'self.log(f"[FAILED] {filename}: {err_msg}")\n                    self.failed_count += 1\n        return False',
    content
)

# Update the success message at the end
content = re.sub(
    r'self\.log\(f"--- All \{self\.downloaded_count\} downloads completed successfully! ---"\)',
    'if self.failed_count > 0:\n                    self.log(f"--- Task finished: {self.downloaded_count} downloaded successfully, {self.failed_count} failed to download! ---")\n                else:\n                    self.log(f"--- All {self.downloaded_count} downloads completed successfully! ---")',
    content
)

with open('E:/RemGodCatcher new/shared.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated shared.py")
