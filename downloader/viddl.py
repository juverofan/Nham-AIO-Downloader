import os
import re
import sys
import json
import shutil
import subprocess
import threading
from typing import Optional, Callable


FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
FFMPEG_DIR = None


def _get_ffmpeg_path() -> Optional[str]:
    """Find ffmpeg, download if needed."""
    global FFMPEG_DIR

    # Check PATH first
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    # Check bundled
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(base, "ffmpeg", "ffmpeg.exe"),
        os.path.join(base, "..", "ffmpeg.exe"),
        os.path.join(os.path.dirname(base), "ffmpeg", "ffmpeg.exe"),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c

    # Check known directories
    for p in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\ffmpeg\ffmpeg.exe"),
    ]:
        if os.path.exists(p):
            return p

    return None


def _download_ffmpeg() -> Optional[str]:
    """Download ffmpeg to app directory."""
    global FFMPEG_DIR
    base = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_dir = os.path.join(base, "ffmpeg")
    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")

    if os.path.exists(ffmpeg_exe):
        FFMPEG_DIR = ffmpeg_dir
        return ffmpeg_exe

    try:
        import requests
        import zipfile
        import io

        os.makedirs(ffmpeg_dir, exist_ok=True)
        print(f"Downloading ffmpeg from {FFMPEG_URL}...")
        resp = requests.get(FFMPEG_URL, timeout=120, stream=True)
        resp.raise_for_status()

        z = zipfile.ZipFile(io.BytesIO(resp.content))
        for name in z.namelist():
            if name.endswith("ffmpeg.exe"):
                z.extract(name, ffmpeg_dir)
                extracted = os.path.join(ffmpeg_dir, name)
                target = os.path.join(ffmpeg_dir, "ffmpeg.exe")
                if extracted != target:
                    os.rename(extracted, target)
                break

        if os.path.exists(ffmpeg_exe):
            FFMPEG_DIR = ffmpeg_dir
            return ffmpeg_exe
    except Exception as e:
        print(f"Failed to download ffmpeg: {e}")
    return None


def ensure_ffmpeg() -> Optional[str]:
    ffmpeg = _get_ffmpeg_path()
    if ffmpeg:
        return ffmpeg
    return _download_ffmpeg()


class VideoDownloader:
    SUPPORTED_SITES = [
        "youtube.com", "youtu.be",
        "facebook.com", "fb.watch", "fb.com",
        "twitter.com", "x.com",
        "instagram.com",
        "tiktok.com",
        "vimeo.com",
        "dailymotion.com",
        "twitch.tv",
        "bilibili.com",
        "reddit.com",
        "pinterest.com",
        "linkedin.com",
        "tumblr.com",
        "vine.co",
        "wsj.com", "bloomberg.com", "cnn.com", "bbc.com",
        "nytimes.com",
        "soundcloud.com",
        "spotify.com",
        "mixcloud.com",
        "rumble.com",
        "odysee.com",
        "9gag.com",
        "ifunny.co",
    ]

    PRESETS = [
        ("Best Quality (recommended)", "bv*+ba/b"),
        ("4K (2160p)", "bestvideo[height<=2160]+bestaudio/best[height<=2160]"),
        ("1440p (2K)", "bestvideo[height<=1440]+bestaudio/best[height<=1440]"),
        ("1080p (Full HD)", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"),
        ("720p (HD)", "bestvideo[height<=720]+bestaudio/best[height<=720]"),
        ("480p", "bestvideo[height<=480]+bestaudio/best[height<=480]"),
        ("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]"),
        ("Audio only (MP3)", "bestaudio/best"),
    ]

    def __init__(self):
        self.ffmpeg_path = ensure_ffmpeg()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def reset_cancel(self):
        self._cancel = False

    @property
    def has_ffmpeg(self) -> bool:
        return self.ffmpeg_path is not None and os.path.exists(self.ffmpeg_path)

    @staticmethod
    def is_supported(url: str) -> bool:
        url_lower = url.lower()
        for site in VideoDownloader.SUPPORTED_SITES:
            if site in url_lower:
                return True
        return False

    @staticmethod
    def detect_site(url: str) -> str:
        url_lower = url.lower()
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "YouTube"
        if "facebook.com" in url_lower or "fb.watch" in url_lower:
            return "Facebook"
        if "twitter.com" in url_lower or "x.com" in url_lower:
            return "Twitter/X"
        if "instagram.com" in url_lower:
            return "Instagram"
        if "tiktok.com" in url_lower:
            return "TikTok"
        if "vimeo.com" in url_lower:
            return "Vimeo"
        if "dailymotion.com" in url_lower:
            return "Dailymotion"
        if "twitch.tv" in url_lower:
            return "Twitch"
        if "bilibili.com" in url_lower:
            return "Bilibili"
        if "reddit.com" in url_lower:
            return "Reddit"
        if "rumble.com" in url_lower:
            return "Rumble"
        if "odysee.com" in url_lower:
            return "Odysee"
        return "Unknown"

    def _make_ydl_opts(self, output_dir: str, format_spec: str = None,
                       progress_hook: Callable = None) -> dict:
        opts = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "extract_flat": False,
        }
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        # Format: use best with proper audio if not specified
        if format_spec:
            opts["format"] = format_spec
        else:
            opts["format"] = "bv*+ba/b"

        # If ffmpeg is available, merge to mp4
        if self.has_ffmpeg:
            opts["merge_output_format"] = "mp4"
            opts["ffmpeg_location"] = self.ffmpeg_path
            opts["postprocessor_args"] = ["-c", "copy"]  # no re-encode
        else:
            # No ffmpeg: prefer formats with both video+audio combined
            opts["format"] = "best[height<=1080]/best"
            opts["merge_output_format"] = None

        # Sort: prefer higher res, better codec
        opts["format_sort"] = [
            "res", "codec:av01", "codec:vp9", "codec:h264",
            "vbr", "filesize", "tbr"
        ]
        return opts

    def get_video_info(self, url: str) -> dict:
        try:
            import yt_dlp
            ydl_opts = self._make_ydl_opts(os.path.dirname(os.path.abspath(__file__)))
            ydl_opts["format"] = "bv*+ba/b"  # get all formats for listing
            ydl_opts["progress_hooks"] = None
            ydl_opts.pop("outtmpl", None)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                req = info.get("requested_formats", formats)

                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", info.get("channel", "Unknown")),
                    "view_count": info.get("view_count", 0),
                    "description": (info.get("description") or "")[:500],
                    "thumbnail": info.get("thumbnail", ""),
                    "webpage_url": info.get("webpage_url", url),
                    "formats": formats,
                    "requested_formats": req,
                }
        except ImportError:
            return {"error": "yt-dlp not installed. Run: pip install yt-dlp"}
        except Exception as e:
            return {"error": str(e)}

    def get_available_qualities(self, url: str) -> list:
        """Return list of available quality presets for the given URL."""
        try:
            import yt_dlp
            ydl_opts = {"quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                fmts = info.get("formats", [])

            max_height = 0
            has_audio_only = False
            for f in fmts:
                h = f.get("height") or 0
                if h > max_height:
                    max_height = h
                if f.get("vcodec") == "none" and f.get("acodec") != "none":
                    has_audio_only = True

            available = []
            if has_audio_only:
                available.append("Audio only (MP3)")
            if max_height >= 2160:
                available.append("Best Quality (recommended)")
                available.append("4K (2160p)")
            if max_height >= 1440:
                available.append("1440p (2K)")
            if max_height >= 1080:
                available.append("1080p (Full HD)")
            if max_height >= 720:
                available.append("720p (HD)")
            available.append("480p")
            available.append("360p")
            return available
        except Exception:
            return [p[0] for p in self.PRESETS]

    def download(self, url: str, output_dir: str, format_spec: str = None,
                 on_progress: Callable = None, on_complete: Callable = None) -> bool:
        self._cancel = False

        try:
            import yt_dlp

            def progress_hook(d):
                if self._cancel:
                    raise Exception("CANCELLED")
                status = d.get("status", "")
                if status == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    pct = (downloaded / total * 100) if total > 0 else 0
                    speed = d.get("speed", 0) or 0
                    if on_progress:
                        on_progress({
                            "percent": pct,
                            "downloaded": downloaded,
                            "total": total,
                            "speed": speed,
                            "eta": d.get("eta", 0),
                        })
                elif status == "finished":
                    if on_progress:
                        on_progress({"percent": 100, "status": "merging"})

            ydl_opts = self._make_ydl_opts(output_dir, format_spec, progress_hook)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                actual_file = self._find_output_file(filename, info)
                if on_complete:
                    on_complete({"file": actual_file or filename, "title": info.get("title", "")})
                return True

        except ImportError:
            if on_complete:
                on_complete({"error": "yt-dlp not installed"})
            return False
        except Exception as e:
            if str(e) == "CANCELLED":
                return False
            if on_complete:
                on_complete({"error": str(e)})
            return False

    def _find_output_file(self, guessed: str, info: dict) -> str:
        if os.path.exists(guessed):
            return guessed
        # Try common extensions
        base = os.path.splitext(guessed)[0]
        for ext in [".mp4", ".mkv", ".webm", ".m4a", ".mp3"]:
            p = base + ext
            if os.path.exists(p):
                return p
        # Check output directory for any recent file
        outdir = os.path.dirname(guessed)
        title = info.get("title", "")
        if title and os.path.isdir(outdir):
            for f in os.listdir(outdir):
                if title[:30] in f:
                    return os.path.join(outdir, f)
        return guessed

    def _map_preset_to_format(self, preset: str) -> Optional[str]:
        for name, fmt in self.PRESETS:
            if name == preset:
                return fmt
        return None


def preset_to_format(preset: str) -> str:
    """Map a display preset name to yt-dlp format string."""
    mapping = {
        "Best Quality (recommended)": "bv*+ba/b",
        "4K (2160p)": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p (2K)": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p (Full HD)": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p (HD)": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "Audio only (MP3)": "bestaudio/best",
        "bestvideo+bestaudio/best": "bv*+ba/b",
        "best": "bv*+ba/b",
    }
    return mapping.get(preset, preset)
