#!/usr/bin/env python3
"""
Standalone CLI script for high-performance Meta Reels Auto Post.
Usage:
    python3 scripts/meta_autopost.py --main-folder "/path/to/folder" --subfolders "1-5" --prefix "combined" --start-hour 18
"""
import sys
from pathlib import Path

# Ensure root dir is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.meta_autopost import main

if __name__ == "__main__":
    main()
