#!/usr/bin/env python
import subprocess
import os
import sys

os.chdir('c:\\weeklyleadershipreports')

# Configure git to not use pager
subprocess.run(['git', 'config', 'core.pager', ''], check=False)

# Check status
print("=" * 50)
print("GIT STATUS")
print("=" * 50)
result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Add all changes
print("\n" + "=" * 50)
print("ADDING FILES")
print("=" * 50)
result = subprocess.run(['git', 'add', '.'], capture_output=True, text=True)
print("Added files")
if result.stderr:
    print("STDERR:", result.stderr)

# Check what's staged
print("\n" + "=" * 50)
print("STAGED CHANGES")
print("=" * 50)
result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True)
print(result.stdout)

# Commit
print("\n" + "=" * 50)
print("COMMITTING")
print("=" * 50)
result = subprocess.run(['git', 'commit', '-m', 'fix: Update monthly recognition page integration with app'], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("Return code:", result.returncode)
    if result.stderr:
        print("STDERR:", result.stderr)

# Push
print("\n" + "=" * 50)
print("PUSHING")
print("=" * 50)
result = subprocess.run(['git', 'push', 'upstream', 'main'], capture_output=True, text=True)
print(result.stdout)
if result.returncode == 0:
    print("✅ Push successful!")
else:
    print("Return code:", result.returncode)
    if result.stderr:
        print("STDERR:", result.stderr)
