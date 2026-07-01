#!/usr/bin/env python3
"""
AIscan Downloader - All-in-One Download Tool for Windows

Features:
  - Download stories from Wattpad -> EPUB/PDF
  - Download videos from YouTube, Facebook, Twitter, TikTok, etc.
  - Download from streaming sites (via yt-dlp)

Usage:
  python app.py          # Launch GUI
  python app.py --cli    # CLI mode (coming soon)

Build EXE:
  python build_exe.py
"""

import sys
import os
import platform


def main():
    # Ensure we're on Windows (or at least not blocking other platforms)
    if platform.system() != "Windows":
        print(f"Note: Running on {platform.system()}. Some features may need ffmpeg.")

    # Check dependencies
    missing = []
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp (pip install yt-dlp)")
    try:
        import requests
    except ImportError:
        missing.append("requests (pip install requests)")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        missing.append("beautifulsoup4 (pip install beautifulsoup4)")

    if missing:
        print("Missing dependencies:")
        for m in missing:
            print(f"  - {m}")
        print("\nInstall all: pip install -r requirements.txt")
        input("\nPress Enter to exit...")
        sys.exit(1)

    # Launch GUI
    from downloader.gui import DownloaderApp
    app = DownloaderApp()
    app.run()


if __name__ == "__main__":
    main()
