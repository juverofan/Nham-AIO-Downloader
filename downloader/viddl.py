import os
import shutil
import subprocess
import sys
import threading
from typing import Optional, Callable

FFMPEG_ZIP_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _get_ffmpeg_path() -> Optional[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(base, "ffmpeg", "ffmpeg.exe"),
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(os.path.dirname(base), "ffmpeg", "bin", "ffmpeg.exe"),
        os.path.join(os.path.dirname(base), "ffmpeg", "ffmpeg.exe"),
        os.path.join(os.path.dirname(base), "ffmpeg.exe"),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c

    for p in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\ffmpeg\ffmpeg.exe"),
    ]:
        if os.path.exists(p):
            return p
    return None


def _download_ffmpeg(log: Optional[Callable] = None) -> Optional[str]:
    base = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_dir = os.path.join(base, "ffmpeg")
    ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")

    if os.path.exists(ffmpeg_exe):
        return ffmpeg_exe

    try:
        import requests
        import zipfile
        import io

        os.makedirs(ffmpeg_dir, exist_ok=True)
        if log:
            log(f"Downloading ffmpeg from {FFMPEG_ZIP_URL} ...")
        resp = requests.get(FFMPEG_ZIP_URL, timeout=180, stream=True)
        resp.raise_for_status()

        z = zipfile.ZipFile(io.BytesIO(resp.content))
        for name in z.namelist():
            if name.endswith(("ffmpeg.exe", "ffprobe.exe")):
                z.extract(name, ffmpeg_dir)
                extracted = os.path.join(ffmpeg_dir, name)
                target = os.path.join(ffmpeg_dir, os.path.basename(name))
                if extracted != target:
                    if os.path.exists(target):
                        os.remove(target)
                    os.rename(extracted, target)

        if os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
        if log:
            log("ffmpeg.exe not found inside downloaded archive.")
    except Exception as e:
        if log:
            log(f"Failed to download ffmpeg: {e}")
    return None


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
        self.ffmpeg_path = _get_ffmpeg_path()
        self._ffmpeg_lock = threading.Lock()
        self._cancel = False
        self.proxy = ""
        self.cookies_file = ""
        self.player_clients = "tv,web,android"

    def configure(self, proxy: str = "", cookies_file: str = "", player_clients: str = ""):
        self.proxy = (proxy or "").strip()
        self.cookies_file = (cookies_file or "").strip()
        self.player_clients = (player_clients or "").strip()

    def cancel(self):
        self._cancel = True

    def reset_cancel(self):
        self._cancel = False

    @property
    def has_ffmpeg(self) -> bool:
        return bool(self.ffmpeg_path) and os.path.exists(self.ffmpeg_path)

    def ensure_ffmpeg(self, log: Optional[Callable] = None) -> Optional[str]:
        if self.has_ffmpeg:
            return self.ffmpeg_path
        with self._ffmpeg_lock:
            if self.has_ffmpeg:
                return self.ffmpeg_path
            if log:
                log("ffmpeg not found — downloading once (~80 MB), please wait...")
            path = _download_ffmpeg(log=log)
            if path:
                self.ffmpeg_path = path
                if log:
                    log(f"ffmpeg ready: {path}")
            elif log:
                log("ffmpeg unavailable — HD merge and MP3 conversion will not work.")
            return self.ffmpeg_path

    @staticmethod
    def is_supported(url: str) -> bool:
        url_lower = url.lower()
        return any(site in url_lower for site in VideoDownloader.SUPPORTED_SITES)

    @staticmethod
    def detect_site(url: str) -> str:
        url_lower = url.lower()
        checks = [
            ("youtube.com", "YouTube"), ("youtu.be", "YouTube"),
            ("facebook.com", "Facebook"), ("fb.watch", "Facebook"), ("fb.com", "Facebook"),
            ("twitter.com", "Twitter/X"), ("x.com", "Twitter/X"),
            ("instagram.com", "Instagram"),
            ("tiktok.com", "TikTok"),
            ("vimeo.com", "Vimeo"),
            ("dailymotion.com", "Dailymotion"),
            ("twitch.tv", "Twitch"),
            ("bilibili.com", "Bilibili"),
            ("reddit.com", "Reddit"),
            ("soundcloud.com", "SoundCloud"),
            ("rumble.com", "Rumble"),
            ("odysee.com", "Odysee"),
        ]
        for needle, name in checks:
            if needle in url_lower:
                return name
        return "Unknown"

    def _make_ydl_opts(self, output_dir: str, format_spec: str = None,
                       progress_hook: Callable = None, for_audio: bool = False,
                       playlist: bool = False) -> dict:
        if playlist:
            outtmpl = os.path.join(output_dir, "%(playlist_index)03d - %(title)s.%(ext)s")
        else:
            outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

        opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": not playlist,
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            "concurrent_fragment_downloads": 4,
            "http_headers": {"User-Agent": BROWSER_UA},
            "format_sort": [
                "res", "ext:mp4:m4a", "codec:h264", "codec:avc1",
                "codec:av01", "codec:vp9", "vbr", "filesize", "tbr",
            ],
        }
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        if self.proxy:
            opts["proxy"] = self.proxy
        if self.cookies_file and os.path.exists(self.cookies_file):
            opts["cookiefile"] = self.cookies_file

        clients = [c.strip() for c in self.player_clients.split(",") if c.strip()]
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}

        if for_audio:
            opts["format"] = "bestaudio/best"
            if self.has_ffmpeg:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }]
        else:
            opts["format"] = format_spec or "bv*+ba/b"

        if self.has_ffmpeg:
            opts["ffmpeg_location"] = self.ffmpeg_path
            opts["merge_output_format"] = "mp4"
        elif not for_audio:
            # Without ffmpeg only single-file formats work.
            opts["format"] = "best[ext=mp4][height<=1080]/best[ext=mp4]/best"
        return opts

    def get_video_info(self, url: str) -> dict:
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "socket_timeout": 30,
                "http_headers": {"User-Agent": BROWSER_UA},
            }
            if self.proxy:
                ydl_opts["proxy"] = self.proxy
            if self.cookies_file and os.path.exists(self.cookies_file):
                ydl_opts["cookiefile"] = self.cookies_file
            clients = [c.strip() for c in self.player_clients.split(",") if c.strip()]
            if clients:
                ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return {"error": "No info returned (video unavailable or region-blocked)."}
                if info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                    return {
                        "title": info.get("title", "Playlist"),
                        "duration": 0,
                        "uploader": info.get("uploader", info.get("channel", "Unknown")),
                        "playlist": True,
                        "count": len(entries),
                        "webpage_url": info.get("webpage_url", url),
                        "thumbnail": info.get("thumbnail", ""),
                    }
                formats = info.get("formats", [])
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", info.get("channel", "Unknown")),
                    "view_count": info.get("view_count", 0),
                    "description": (info.get("description") or "")[:500],
                    "thumbnail": info.get("thumbnail", ""),
                    "webpage_url": info.get("webpage_url", url),
                    "formats": formats,
                }
        except ImportError:
            return {"error": "yt-dlp not installed. Run: pip install yt-dlp"}
        except Exception as e:
            return {"error": str(e)}

    def get_available_qualities(self, url: str) -> list:
        try:
            import yt_dlp
            ydl_opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30,
                        "http_headers": {"User-Agent": BROWSER_UA}}
            if self.proxy:
                ydl_opts["proxy"] = self.proxy
            if self.cookies_file and os.path.exists(self.cookies_file):
                ydl_opts["cookiefile"] = self.cookies_file
            clients = [c.strip() for c in self.player_clients.split(",") if c.strip()]
            if clients:
                ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                fmts = (info or {}).get("formats", [])

            max_height = 0
            has_audio_only = False
            for f in fmts:
                h = f.get("height") or 0
                if h > max_height:
                    max_height = h
                if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none"):
                    has_audio_only = True

            available = []
            if has_audio_only:
                available.append("Audio only (MP3)")
            available.append("Best Quality (recommended)")
            if max_height >= 2160:
                available.append("4K (2160p)")
            if max_height >= 1440:
                available.append("1440p (2K)")
            if max_height >= 1080:
                available.append("1080p (Full HD)")
            if max_height >= 720:
                available.append("720p (HD)")
            available.append("480p")
            available.append("360p")
            # dedupe preserving order
            seen = set()
            return [x for x in available if not (x in seen or seen.add(x))]
        except Exception:
            return [p[0] for p in self.PRESETS]

    def download(self, url: str, output_dir: str, format_spec: str = None,
                 on_progress: Callable = None, on_complete: Callable = None,
                 playlist: bool = False, log: Callable = None) -> bool:
        self._cancel = False

        try:
            import yt_dlp
        except ImportError:
            if on_complete:
                on_complete({"error": "yt-dlp not installed. Run: pip install yt-dlp"})
            return False

        os.makedirs(output_dir, exist_ok=True)
        self.ensure_ffmpeg(log=log)
        if not self.has_ffmpeg and log:
            log("Tip: without ffmpeg only formats with built-in audio can be downloaded.")

        is_audio = format_spec == "bestaudio/best"

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
                        "filename": d.get("filename", ""),
                    })
            elif status == "finished":
                if on_progress:
                    on_progress({"percent": 100, "status": "processing",
                                 "filename": d.get("filename", "")})

        ydl_opts = self._make_ydl_opts(output_dir, format_spec, progress_hook,
                                       for_audio=is_audio, playlist=playlist)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if self._cancel:
                    if on_complete:
                        on_complete({"cancelled": True})
                    return False
                if info is None:
                    if on_complete:
                        on_complete({"error": "No info returned (video unavailable or region-blocked)."})
                    return False

                if info.get("_type") == "playlist":
                    files = []
                    for entry in info.get("entries") or []:
                        if not entry:
                            continue
                        try:
                            f = self._find_output_file(ydl.prepare_filename(entry), entry, audio=is_audio)
                        except Exception:
                            f = None
                        if f and os.path.exists(f):
                            files.append(f)
                    if on_complete:
                        on_complete({
                            "file": files[-1] if files else "",
                            "files": files,
                            "title": info.get("title", ""),
                            "playlist": True,
                            "count": len(files),
                        })
                    return True

                filename = ydl.prepare_filename(info)
                actual_file = self._find_output_file(filename, info, audio=is_audio)
                if on_complete:
                    on_complete({"file": actual_file or filename, "title": info.get("title", "")})
                return True

        except Exception as e:
            msg = str(e)
            if msg == "CANCELLED":
                if on_complete:
                    on_complete({"cancelled": True})
                return False
            if on_complete:
                on_complete({"error": msg + self._error_hint(msg)})
            return False

    @staticmethod
    def _error_hint(msg: str) -> str:
        low = msg.lower()
        if ("confirm you" in low and "not a bot" in low) or "sign in to confirm" in low:
            return (" — YouTube asks to confirm you are not a bot. Fix: Settings → set a "
                    "cookies file (export cookies.txt from your browser) and/or change "
                    "YouTube player clients.")
        if "requested format is not available" in low:
            return " — Selected quality not available for this video. Try 'Best Quality'."
        if "private video" in low or "members-only" in low or "join this channel" in low:
            return " — Video requires login/membership. Set a cookies file in Settings."
        if "http error 403" in low or "403" in msg:
            return " — Server refused access (403). Update yt-dlp (Settings → Update yt-dlp) or set cookies."
        if "getaddrinfo failed" in low or "timed out" in low or "network" in low:
            return " — Network problem. Check connection/proxy in Settings, then retry."
        if "live event" in low or "is live" in low:
            return " — Live streams must finish before the full video can be downloaded."
        return ""

    def _find_output_file(self, guessed: str, info: dict, audio: bool = False) -> str:
        if os.path.exists(guessed):
            return guessed
        base = os.path.splitext(guessed)[0]
        exts = [".mp3", ".m4a"] if audio else [".mp4", ".mkv", ".webm", ".m4a", ".mp3"]
        for ext in exts:
            p = base + ext
            if os.path.exists(p):
                return p
        outdir = os.path.dirname(guessed)
        title = (info.get("title") or "")[:30]
        if title and os.path.isdir(outdir):
            for f in sorted(os.listdir(outdir), key=lambda x: os.path.getmtime(os.path.join(outdir, x)), reverse=True):
                if title in f:
                    return os.path.join(outdir, f)
        return guessed

    @staticmethod
    def update_yt_dlp() -> str:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                capture_output=True, text=True, timeout=600,
            )
            if r.returncode == 0:
                return "yt-dlp updated successfully."
            return f"Update failed:\n{(r.stderr or r.stdout or '')[-600:]}"
        except Exception as e:
            return f"Update failed: {e}"


def preset_to_format(preset: str) -> str:
    mapping = {
        "Best Quality (recommended)": "bv*+ba/b",
        "4K (2160p)": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1440p (2K)": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
        "1080p (Full HD)": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p (HD)": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "Audio only (MP3)": "bestaudio/best",
    }
    return mapping.get(preset, preset)
