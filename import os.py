import os
import re

# Patterns to search for
patterns = [
    r'api[_-]?key\s*=\s*[\'"].+[\'"]',
    r'supabase[_-]?key\s*=\s*[\'"].+[\'"]',
    r'GOOGLE_API_KEY\s*=\s*[\'"].+[\'"]',
    r'key\s*=\s*[\'"].+[\'"]',
    r'["\']AIza[0-9A-Za-z-_]{35}["\']',  # Google API key format
]

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            for pattern in patterns:
                if re.search(pattern, line):
                    print(f"Possible API key in {filepath} at line {i}: {line.strip()}")

def scan_repo(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.py') or filename.endswith('.env') or filename.endswith('.toml'):
                scan_file(os.path.join(dirpath, filename))

if __name__ == "__main__":
    scan_repo(os.getcwd())