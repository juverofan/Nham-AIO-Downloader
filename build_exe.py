#!/usr/bin/env python3
"""
Build AIscan Downloader as a standalone Windows EXE.
Requires: pip install pyinstaller
Usage:     python build_exe.py
"""

import os
import sys
import shutil
import subprocess


APP_NAME = "AIscanDownloader"
BUILD_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BUILD_DIR, "dist")
ICON_FILE = os.path.join(BUILD_DIR, "icon.ico")


def check_pyinstaller():
    try:
        import PyInstaller
        return True
    except ImportError:
        return False


def create_icon():
    """Create a simple icon file if none exists."""
    if os.path.exists(ICON_FILE):
        return
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([20, 20, 236, 236], radius=40, fill=(0, 120, 212))
        draw.ellipse([80, 60, 176, 156], fill=(255, 255, 255))
        draw.polygon([(100, 160), (156, 160), (128, 210)], fill=(255, 255, 255))
        # Save as ICO
        img.save(ICON_FILE, format="ICO", sizes=[(256, 256)])
        print(f"  Created icon: {ICON_FILE}")
    except ImportError:
        print("  Warning: PIL not available, skipping icon creation")
        print("  Install: pip install Pillow")


def clean_build():
    for d in ["build", "dist", "__pycache__"]:
        path = os.path.join(BUILD_DIR, d)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            print(f"  Cleaned: {d}")
    for root, dirs, files in os.walk(BUILD_DIR):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)


def build():
    print("=" * 60)
    print(f"  Building {APP_NAME} as Windows EXE")
    print("=" * 60)

    if not check_pyinstaller():
        print("\n  ERROR: PyInstaller is not installed.")
        print("  Install with: pip install pyinstaller")
        return False

    create_icon()

    print("\n  Cleaning previous builds...")
    clean_build()

    print("\n  Building EXE (this may take a few minutes)...")
    print()

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", APP_NAME,
        "--distpath", DIST_DIR,
        "--add-data", f"downloader{os.pathsep}downloader",
        "--add-data", f"logo.png{os.pathsep}.",
        "--hidden-import", "yt_dlp",
        "--hidden-import", "yt_dlp.extractor",
        "--hidden-import", "requests",
        "--hidden-import", "bs4",
        "--hidden-import", "fpdf",
        "--hidden-import", "ebooklib",
        "--collect-all", "yt_dlp",
        "--collect-all", "charset_normalizer",
        "--noconfirm",
    ]

    if os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])

    cmd.append(os.path.join(BUILD_DIR, "app.py"))

    result = subprocess.run(cmd, cwd=BUILD_DIR)
    if result.returncode != 0:
        print(f"\n  BUILD FAILED (return code {result.returncode})")
        return False

    exe_path = os.path.join(DIST_DIR, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"\n  SUCCESS!")
        print(f"  EXE: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"\n  Build completed but EXE not found at: {exe_path}")
        return False

    print("\n" + "=" * 60)
    return True


if __name__ == "__main__":
    success = build()
    sys.exit(0 if success else 1)
