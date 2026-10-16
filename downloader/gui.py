import os
import sys
import re
import subprocess
import webbrowser
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

from .wattpad import WattpadStory, format_as_markdown
from .viddl import VideoDownloader, preset_to_format
from .converter import text_to_pdf, text_to_epub
from .history import DownloadHistory, load_config, save_config

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def open_path(path: str) -> bool:
    """Open a file with the default application, or open a folder."""
    if not path:
        return False
    path = os.path.normpath(path)
    try:
        if not os.path.exists(path):
            return False
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def reveal_path(path: str) -> bool:
    """Open the containing folder and select the file in Explorer."""
    if not path:
        return False
    path = os.path.normpath(path)
    try:
        if os.name == "nt":
            if os.path.isfile(path):
                # IMPORTANT: pass this as a single raw command string. If passed as
                # a list, Python wraps the whole "/select,..." token in quotes and
                # Explorer fails to parse it, silently opening Documents instead.
                subprocess.Popen('explorer /select,"%s"' % path)
                return True
            if os.path.isdir(path):
                os.startfile(path)
                return True
            folder = os.path.dirname(path)
            if os.path.isdir(folder):
                os.startfile(folder)
                return True
            return False
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if os.path.isdir(folder):
            if sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            return True
    except Exception:
        pass
    return False


class DownloaderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Nhảm AIO Downloader - All-in-One Download Tool")
        self.root.geometry("960x720")
        self.root.minsize(760, 560)

        self.config = load_config()
        self.history = DownloadHistory()

        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "NhamAIO")
        self.output_dir = self.config.get("output_dir") or default_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.video_dl = VideoDownloader()
        self.video_dl.configure(
            proxy=self.config.get("proxy", ""),
            cookies_file=self.config.get("cookies_file", ""),
            player_clients=self.config.get("player_clients", "tv,web,android"),
        )

        self._last_video_file = ""
        self._last_story_file = ""
        self._batch_running = False

        self._build_ui()
        self._refresh_history()

    # ── UI scaffolding ────────────────────────────
    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self._tab_story = ttk.Frame(self.notebook)
        self._tab_video = ttk.Frame(self.notebook)
        self._tab_batch = ttk.Frame(self.notebook)
        self._tab_history = ttk.Frame(self.notebook)
        self._tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self._tab_story, text="  Story  ")
        self.notebook.add(self._tab_video, text="  Streaming  ")
        self.notebook.add(self._tab_batch, text="  Batch  ")
        self.notebook.add(self._tab_history, text="  History  ")
        self.notebook.add(self._tab_settings, text="  Settings  ")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_story_tab()
        self._build_video_tab()
        self._build_batch_tab()
        self._build_history_tab()
        self._build_settings_tab()

        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom", padx=2, pady=2)

    def _on_tab_changed(self, _event=None):
        if self.notebook.index("current") == self.notebook.index(self._tab_history):
            self._refresh_history()

    def _set_status(self, msg):
        self.status_var.set(msg)

    def _widget_log(self, widget, msg):
        def _do():
            try:
                widget.configure(state="normal")
                widget.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
                widget.see("end")
                widget.configure(state="disabled")
            except Exception:
                pass
        try:
            self.root.after(0, _do)
        except Exception:
            pass

    # ── Story Tab ─────────────────────────────────
    def _build_story_tab(self):
        frame = self._tab_story
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Wattpad URL:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(15, 5))
        self.story_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.story_url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=(15, 5))
        self.fetch_btn = ttk.Button(frame, text="Fetch Story Info", command=self._fetch_story)
        self.fetch_btn.grid(row=0, column=2, padx=10, pady=(15, 5))

        info_frame = ttk.LabelFrame(frame, text="Story Info", padding=5)
        info_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="Title:").grid(row=0, column=0, sticky="w", padx=5)
        self.story_title_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.story_title_var, font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")

        ttk.Label(info_frame, text="Author:").grid(row=1, column=0, sticky="w", padx=5)
        self.story_author_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.story_author_var).grid(row=1, column=1, sticky="w")

        ttk.Label(info_frame, text="Chapters:").grid(row=2, column=0, sticky="w", padx=5)
        self.story_chapters_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.story_chapters_var).grid(row=2, column=1, sticky="w")

        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=5)
        ttk.Label(fmt_frame, text="Output Format:").pack(side="left", padx=5)
        self.story_format_var = tk.StringVar(value="EPUB")
        ttk.Radiobutton(fmt_frame, text="EPUB (Recommended)", variable=self.story_format_var, value="EPUB").pack(side="left", padx=5)
        ttk.Radiobutton(fmt_frame, text="PDF", variable=self.story_format_var, value="PDF").pack(side="left", padx=5)
        ttk.Button(fmt_frame, text="Download Story", command=self._download_story).pack(side="left", padx=20)
        self.story_open_file_btn = ttk.Button(fmt_frame, text="Open File", command=lambda: self._open_last_story(False), state="disabled")
        self.story_open_file_btn.pack(side="left", padx=2)
        self.story_open_folder_btn = ttk.Button(fmt_frame, text="Open Folder", command=lambda: self._open_last_story(True), state="disabled")
        self.story_open_folder_btn.pack(side="left", padx=2)

        self.story_progress = ttk.Progressbar(frame, mode="determinate")
        self.story_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(5, 0))
        self.story_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.story_status_var, foreground="blue").grid(row=4, column=0, columnspan=3, sticky="w", padx=15)

        self.story_log = scrolledtext.ScrolledText(frame, height=10, state="disabled", font=("Consolas", 9))
        self.story_log.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=10, pady=(5, 10))

    def _log_story(self, msg):
        self._widget_log(self.story_log, msg)

    def _open_last_story(self, folder: bool):
        if not self._last_story_file:
            return
        ok = reveal_path(self._last_story_file) if folder else open_path(self._last_story_file)
        if not ok:
            messagebox.showerror("Error", f"File not found:\n{self._last_story_file}")

    def _fetch_story(self):
        url = self.story_url_var.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a Wattpad URL")
            return
        self.fetch_btn.configure(state="disabled")
        self.story_title_var.set("")
        self.story_author_var.set("")
        self.story_chapters_var.set("")
        self._log_story(f"Fetching story info from: {url}")

        def task():
            try:
                story = WattpadStory(url)
                info = story.fetch_info()
                self.root.after(0, lambda: self.story_title_var.set(info["title"]))
                self.root.after(0, lambda: self.story_author_var.set(info["author"]))
                self.root.after(0, lambda: self.story_chapters_var.set(f"{info['chapters']} chapters"))
                self.root.after(0, lambda: self._log_story(f"Found: {info['title']} by {info['author']} ({info['chapters']} chapters)"))
                self.root.after(0, lambda: setattr(self, "_current_story", story))
            except Exception as e:
                self.root.after(0, lambda: self._log_story(f"Error: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.fetch_btn.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _download_story(self):
        if not hasattr(self, "_current_story"):
            messagebox.showwarning("No Data", "Please fetch a story first")
            return
        story = self._current_story
        fmt = self.story_format_var.get()
        self.story_progress["value"] = 0
        self.story_open_file_btn.configure(state="disabled")
        self.story_open_folder_btn.configure(state="disabled")

        def on_progress(idx, t, title):
            pct = (idx / t) * 50
            self.root.after(0, lambda: self.story_progress.configure(value=pct))
            self.root.after(0, lambda: self._log_story(f"Chapter {idx+1}/{t}: {title[:50]}"))

        def task():
            try:
                self.root.after(0, lambda: self.story_status_var.set("Downloading chapters..."))
                ch_texts = story.fetch_all_chapters(progress_callback=on_progress)

                md_text = format_as_markdown(story, ch_texts)
                base_name = re.sub(r'[\\/*?:"<>|]', "_", story.title)[:60]
                self.root.after(0, lambda: self.story_progress.configure(value=75))

                if fmt == "PDF":
                    ext = ".pdf"
                    self.root.after(0, lambda: self.story_status_var.set("Generating PDF..."))
                    path = os.path.join(self.output_dir, base_name + ext)
                    text_to_pdf(md_text, path, title=story.title, author=story.author, cover_url=story.cover_url)
                else:
                    ext = ".epub"
                    self.root.after(0, lambda: self.story_status_var.set("Generating EPUB..."))
                    path = os.path.join(self.output_dir, base_name + ext)
                    text_to_epub(md_text, path, title=story.title, author=story.author, cover_url=story.cover_url)

                self._last_story_file = path
                self.history.add(title=story.title, file_path=path, url=story.url,
                                 source="Wattpad " + fmt, status="Success", kind="Story")

                def done():
                    self.story_progress.configure(value=100)
                    self.story_status_var.set(f"Saved: {path}")
                    self._log_story(f"Saved to: {path}")
                    self.story_open_file_btn.configure(state="normal")
                    self.story_open_folder_btn.configure(state="normal")
                    self._refresh_history()
                    messagebox.showinfo("Complete", f"Story saved to:\n{path}")
                self.root.after(0, done)
            except Exception as e:
                self.root.after(0, lambda: self._log_story(f"Download error: {e}"))
                self.root.after(0, lambda: self.story_status_var.set("Failed"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=task, daemon=True).start()

    # ── Video Tab ─────────────────────────────────
    def _build_video_tab(self):
        frame = self._tab_video
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        ttk.Label(frame, text="Video URL:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(15, 5))
        self.video_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.video_url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=(15, 5))
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=2, padx=5, pady=(15, 5))
        self.info_btn = ttk.Button(btn_frame, text="Get Info", command=self._video_info)
        self.info_btn.pack(side="left", padx=2)
        self.dl_btn = ttk.Button(btn_frame, text="Download", command=self._download_video)
        self.dl_btn.pack(side="left", padx=2)

        info_frame = ttk.LabelFrame(frame, text="Video Info", padding=5)
        info_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        info_frame.columnconfigure(1, weight=1)

        ttk.Label(info_frame, text="Title:").grid(row=0, column=0, sticky="w", padx=5)
        self.vid_title_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.vid_title_var, font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")

        ttk.Label(info_frame, text="Site:").grid(row=1, column=0, sticky="w", padx=5)
        self.vid_site_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.vid_site_var).grid(row=1, column=1, sticky="w")

        ttk.Label(info_frame, text="Duration:").grid(row=2, column=0, sticky="w", padx=5)
        self.vid_dur_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.vid_dur_var).grid(row=2, column=1, sticky="w")

        ttk.Label(info_frame, text="Uploader:").grid(row=0, column=2, sticky="w", padx=20)
        self.vid_uploader_var = tk.StringVar()
        ttk.Label(info_frame, textvariable=self.vid_uploader_var).grid(row=0, column=3, sticky="w")

        ttk.Label(info_frame, text="Quality:").grid(row=3, column=0, sticky="w", padx=5)
        self.vid_format_var = tk.StringVar(value="Best Quality (recommended)")
        self.vid_format_combo = ttk.Combobox(info_frame, textvariable=self.vid_format_var, width=50, state="readonly")
        self.vid_format_combo.grid(row=3, column=1, columnspan=3, sticky="ew", padx=5, pady=5)
        self.vid_format_combo["values"] = [p[0] for p in VideoDownloader.PRESETS]
        self.vid_format_combo.current(0)

        self.vid_playlist_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(info_frame, text="Download whole playlist (if URL is a playlist)",
                        variable=self.vid_playlist_var).grid(row=4, column=0, columnspan=4, sticky="w", padx=5)

        ffmpeg_ok = self.video_dl.has_ffmpeg
        ffmpeg_text = "ffmpeg: Ready" if ffmpeg_ok else "ffmpeg: Not found (auto-download on first download)"
        self.vid_ffmpeg_var = tk.StringVar(value=ffmpeg_text)
        ttk.Label(info_frame, textvariable=self.vid_ffmpeg_var,
                  foreground="green" if ffmpeg_ok else "orange",
                  font=("Segoe UI", 8)).grid(row=5, column=0, columnspan=4, sticky="w", padx=5)

        self.vid_progress = ttk.Progressbar(frame, mode="determinate")
        self.vid_progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        self.vid_speed_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.vid_speed_var, foreground="gray").grid(row=2, column=0, columnspan=3, sticky="e", padx=15)
        self.vid_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.vid_status_var, foreground="blue").grid(row=3, column=0, columnspan=2, sticky="w", padx=15)

        action_frame = ttk.Frame(frame)
        action_frame.grid(row=3, column=2, sticky="e", padx=10)
        self.vid_open_file_btn = ttk.Button(action_frame, text="Open File", command=lambda: self._open_last_video(False), state="disabled")
        self.vid_open_file_btn.pack(side="left", padx=2)
        self.vid_open_folder_btn = ttk.Button(action_frame, text="Open Folder", command=lambda: self._open_last_video(True), state="disabled")
        self.vid_open_folder_btn.pack(side="left", padx=2)
        self.cancel_vid_btn = ttk.Button(action_frame, text="Cancel", command=self.video_dl.cancel, state="disabled")
        self.cancel_vid_btn.pack(side="left", padx=2)

        self.vid_log = scrolledtext.ScrolledText(frame, height=10, state="disabled", font=("Consolas", 9))
        self.vid_log.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=10, pady=(5, 10))

    def _log_video(self, msg):
        self._widget_log(self.vid_log, msg)

    def _open_last_video(self, folder: bool):
        if not self._last_video_file:
            return
        ok = reveal_path(self._last_video_file) if folder else open_path(self._last_video_file)
        if not ok:
            messagebox.showerror("Error", f"File not found:\n{self._last_video_file}")

    def _video_info(self):
        url = self.video_url_var.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a video URL")
            return
        site = VideoDownloader.detect_site(url)
        self.vid_site_var.set(site)
        self._log_video(f"Fetching info: {url}")
        self.info_btn.configure(state="disabled")

        def task():
            try:
                info = self.video_dl.get_video_info(url)
                if "error" in info:
                    self.root.after(0, lambda: self._log_video(f"Error: {info['error']}"))
                    self.root.after(0, lambda: messagebox.showerror("Error", info["error"]))
                    return
                self.root.after(0, lambda: self.vid_title_var.set(info.get("title", "")[:80]))
                if info.get("playlist"):
                    self.root.after(0, lambda: self.vid_dur_var.set(f"Playlist: {info.get('count', 0)} items"))
                    self.root.after(0, lambda: self.vid_uploader_var.set(info.get("uploader", "")))
                    self.root.after(0, lambda: self._log_video(f"Found playlist: {info.get('title', '')[:60]}"))
                    return
                dur = info.get("duration", 0)
                dur_str = f"{dur // 60}m {dur % 60}s" if dur else "Unknown"
                self.root.after(0, lambda: self.vid_dur_var.set(dur_str))
                self.root.after(0, lambda: self.vid_uploader_var.set(info.get("uploader", "")))

                avail = self.video_dl.get_available_qualities(url)
                self.root.after(0, lambda: self._update_format_combo(avail))
                self.root.after(0, lambda: self._log_video(f"Found: {info.get('title', '')[:60]}"))
            except Exception as e:
                self.root.after(0, lambda: self._log_video(f"Error: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.info_btn.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _update_format_combo(self, options):
        self.vid_format_combo["values"] = options
        if options:
            self.vid_format_combo.current(0)

    def _download_video(self):
        url = self.video_url_var.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a video URL")
            return

        fmt_raw = self.vid_format_var.get()
        fmt_id = preset_to_format(fmt_raw)
        playlist = bool(self.vid_playlist_var.get())

        self.dl_btn.configure(state="disabled")
        self.cancel_vid_btn.configure(state="normal")
        self.vid_open_file_btn.configure(state="disabled")
        self.vid_open_folder_btn.configure(state="disabled")
        self.video_dl.reset_cancel()
        self._log_video(f"Starting download: {url}")
        self._log_video(f"Format: {fmt_id}{' (playlist)' if playlist else ''}")

        def on_progress(data):
            pct = data.get("percent", 0)
            speed = data.get("speed", 0)
            self.root.after(0, lambda: self.vid_progress.configure(value=pct))
            if speed:
                speed_mb = speed / 1024 / 1024
                self.root.after(0, lambda: self.vid_speed_var.set(f"{speed_mb:.1f} MB/s"))

        def on_complete(data):
            if data.get("cancelled"):
                self.root.after(0, lambda: self.dl_btn.configure(state="normal"))
                self.root.after(0, lambda: self.cancel_vid_btn.configure(state="disabled"))
                self.root.after(0, lambda: self._log_video("Download cancelled."))
                return

            self.root.after(0, lambda: self.dl_btn.configure(state="normal"))
            self.root.after(0, lambda: self.cancel_vid_btn.configure(state="disabled"))

            if "error" in data:
                self.root.after(0, lambda: self._log_video(f"Download failed: {data['error']}"))
                self.root.after(0, lambda: messagebox.showerror("Error", data["error"]))
                self.history.add(title="(failed)", file_path="", url=url,
                                 source=VideoDownloader.detect_site(url), status="Failed", kind="Video")
                self.root.after(0, self._refresh_history)
                return

            if data.get("playlist"):
                files = data.get("files", [])
                count = data.get("count", len(files))
                last = data.get("file", "")
                self._last_video_file = last
                self.history.add(title=f"{data.get('title', 'Playlist')} ({count} videos)",
                                 file_path=last, url=url, source=VideoDownloader.detect_site(url),
                                 status=f"Success ({count})", kind="Playlist")
                for f in files:
                    self.history.add(title=os.path.basename(f), file_path=f, url=url,
                                     source=VideoDownloader.detect_site(url), status="Success", kind="Video")

                def done_pl():
                    self.vid_progress.configure(value=100)
                    self.vid_status_var.set(f"Playlist complete: {count} videos")
                    self._log_video(f"Playlist downloaded: {count} videos -> {os.path.dirname(last)}")
                    self.vid_open_folder_btn.configure(state="normal")
                    self._refresh_history()
                    messagebox.showinfo("Complete", f"Playlist downloaded ({count} videos).\nFolder:\n{os.path.dirname(last)}")
                self.root.after(0, done_pl)
                return

            f = data.get("file", "")
            self._last_video_file = f
            self.history.add(title=data.get("title", os.path.basename(f)), file_path=f, url=url,
                             source=VideoDownloader.detect_site(url), status="Success", kind="Video")

            def done():
                self.vid_progress.configure(value=100)
                self.vid_status_var.set("Complete!")
                self._log_video(f"Downloaded: {f}")
                if f:
                    self.vid_open_file_btn.configure(state="normal")
                self.vid_open_folder_btn.configure(state="normal")
                self._refresh_history()
                messagebox.showinfo("Complete", f"Saved to:\n{f}")
            self.root.after(0, done)

        def task():
            self.video_dl.download(
                url=url,
                output_dir=self.output_dir,
                format_spec=fmt_id,
                on_progress=on_progress,
                on_complete=on_complete,
                playlist=playlist,
                log=self._log_video,
            )

        threading.Thread(target=task, daemon=True).start()

    # ── Batch Tab ─────────────────────────────────
    def _build_batch_tab(self):
        frame = self._tab_batch
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(7, weight=1)

        ttk.Label(frame, text="Batch Download — one URL per line (lines starting with # are ignored)",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=(12, 2))

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=1, column=0, sticky="ew", padx=10)
        ttk.Button(toolbar, text="Load from .txt file", command=self._batch_load_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear list", command=self._batch_clear).pack(side="left", padx=2)

        urls_frame = ttk.LabelFrame(frame, text="URLs", padding=4)
        urls_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        urls_frame.columnconfigure(0, weight=1)
        urls_frame.rowconfigure(0, weight=1)
        self.batch_text = scrolledtext.ScrolledText(urls_frame, height=8, font=("Consolas", 9))
        self.batch_text.grid(row=0, column=0, sticky="nsew")

        opt_frame = ttk.Frame(frame)
        opt_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        ttk.Label(opt_frame, text="Quality:").pack(side="left", padx=5)
        self.batch_format_var = tk.StringVar(value="Best Quality (recommended)")
        self.batch_format_combo = ttk.Combobox(opt_frame, textvariable=self.batch_format_var,
                                               width=30, state="readonly",
                                               values=[p[0] for p in VideoDownloader.PRESETS])
        self.batch_format_combo.current(0)
        self.batch_format_combo.pack(side="left", padx=5)
        self.batch_start_btn = ttk.Button(opt_frame, text="Download All", command=self._start_batch)
        self.batch_start_btn.pack(side="left", padx=15)
        self.batch_cancel_btn = ttk.Button(opt_frame, text="Cancel", command=self.video_dl.cancel, state="disabled")
        self.batch_cancel_btn.pack(side="left", padx=2)
        self.batch_open_folder_btn = ttk.Button(opt_frame, text="Open Output Folder",
                                                command=lambda: reveal_path(self.output_dir))
        self.batch_open_folder_btn.pack(side="right", padx=2)

        self.batch_progress = ttk.Progressbar(frame, mode="determinate")
        self.batch_progress.grid(row=5, column=0, sticky="ew", padx=10, pady=2)
        self.batch_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.batch_status_var, foreground="blue").grid(row=6, column=0, sticky="w", padx=15)

        self.batch_log = scrolledtext.ScrolledText(frame, height=8, state="disabled", font=("Consolas", 9))
        self.batch_log.grid(row=7, column=0, sticky="nsew", padx=10, pady=(5, 10))

    def _log_batch(self, msg):
        self._widget_log(self.batch_log, msg)

    def _batch_load_file(self):
        path = filedialog.askopenfilename(
            title="Select a text file with URLs",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot read file:\n{e}")
            return
        self.batch_text.delete("1.0", "end")
        self.batch_text.insert("1.0", content)
        self._set_status(f"Loaded URLs from {path}")

    def _batch_clear(self):
        self.batch_text.delete("1.0", "end")
        self.batch_status_var.set("")

    def _batch_urls(self):
        raw = self.batch_text.get("1.0", "end")
        urls = []
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
        return urls

    def _start_batch(self):
        if self._batch_running:
            return
        urls = self._batch_urls()
        if not urls:
            messagebox.showwarning("No URLs", "Please enter at least one URL (one per line) or load a .txt file.")
            return

        fmt = preset_to_format(self.batch_format_var.get())
        self._batch_running = True
        self.video_dl.reset_cancel()
        self.batch_start_btn.configure(state="disabled")
        self.batch_cancel_btn.configure(state="normal")
        self.batch_progress["value"] = 0
        total = len(urls)
        self._log_batch(f"Starting batch download: {total} URL(s)")

        def task():
            ok = fail = 0
            for i, url in enumerate(urls):
                if self.video_dl._cancel:
                    self.root.after(0, lambda: self._log_batch("Batch cancelled."))
                    break
                self.root.after(0, lambda i=i, url=url:
                                self.batch_status_var.set(f"[{i + 1}/{total}] {url[:70]}"))
                self.root.after(0, lambda i=i: self._log_batch(f"[{i + 1}/{total}] starting..."))

                result = {}

                def on_progress(data, i=i):
                    pct = data.get("percent", 0)
                    base = (i / total) * 100
                    overall = base + (pct / total)
                    self.root.after(0, lambda: self.batch_progress.configure(value=overall))
                    self.root.after(0, lambda: self.batch_status_var.set(
                        f"[{i + 1}/{total}] {pct:.1f}%  —  {url[:55]}"))

                def on_complete(data):
                    result.update(data)

                self.video_dl.download(
                    url=url,
                    output_dir=self.output_dir,
                    format_spec=fmt,
                    on_progress=on_progress,
                    on_complete=on_complete,
                    log=self._log_batch,
                )

                if result.get("cancelled"):
                    self.root.after(0, lambda: self._log_batch("Cancelled by user."))
                    break
                if result.get("error"):
                    fail += 1
                    self.root.after(0, lambda u=url, e=result["error"]:
                                    self._log_batch(f"FAILED: {u}\n    {e}"))
                    self.history.add(title="(failed)", file_path="", url=url,
                                     source=VideoDownloader.detect_site(url),
                                     status="Failed", kind="Video")
                else:
                    ok += 1
                    f = result.get("file", "")
                    self._last_video_file = f
                    self.history.add(title=result.get("title", os.path.basename(f)), file_path=f,
                                     url=url, source=VideoDownloader.detect_site(url),
                                     status="Success", kind="Video")
                    self.root.after(0, lambda f=f: self._log_batch(f"OK: {f}"))

                self.root.after(0, lambda i=i: self.batch_progress.configure(
                    value=((i + 1) / total) * 100))
                self.root.after(0, self._refresh_history)

            def finish():
                self._batch_running = False
                self.batch_start_btn.configure(state="normal")
                self.batch_cancel_btn.configure(state="disabled")
                self.batch_status_var.set(f"Done. Success: {ok}, Failed: {fail}, Total: {total}")
                self._log_batch(f"Batch finished. Success: {ok}, Failed: {fail}, Total: {total}")
                messagebox.showinfo("Batch Complete", f"Success: {ok}\nFailed: {fail}\nTotal: {total}")
            self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    # ── History Tab ───────────────────────────────
    def _build_history_tab(self):
        frame = self._tab_history
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(frame)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(12, 4))
        ttk.Button(toolbar, text="Open File", command=self._history_open_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Open Folder", command=self._history_open_folder).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Copy Path", command=self._history_copy_path).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Copy URL", command=self._history_copy_url).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Remove Selected", command=self._history_remove).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Clear All", command=self._history_clear).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_history).pack(side="right", padx=2)

        columns = ("time", "title", "kind", "source", "status", "file")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "time": ("Time", 140),
            "title": ("Title", 240),
            "kind": ("Type", 80),
            "source": ("Source", 90),
            "status": ("Status", 90),
            "file": ("File", 460),
        }
        for col, (text, width) in headings.items():
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        self.history_tree.bind("<Double-1>", lambda e: self._history_open_file())

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.history_tree.yview)
        vsb.grid(row=1, column=1, sticky="ns", pady=(0, 5))
        self.history_tree.configure(yscrollcommand=vsb.set)

        ttk.Label(frame,
                  text="Double-click a row to open the file. Path: %APPDATA%\\NhamAIO\\history.json",
                  foreground="gray", font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        tree = self.history_tree
        for item in tree.get_children():
            tree.delete(item)
        entries = self.history.entries()
        # newest first
        for idx in range(len(entries) - 1, -1, -1):
            e = entries[idx]
            tree.insert("", "end", iid=str(idx), values=(
                e.get("time", ""),
                e.get("title", ""),
                e.get("kind", ""),
                e.get("source", ""),
                e.get("status", ""),
                e.get("file", ""),
            ))

    def _history_selected(self):
        sel = self.history_tree.selection()
        if not sel:
            return None
        return self.history.entries()[int(sel[0])]

    def _history_open_file(self):
        e = self._history_selected()
        if not e:
            messagebox.showinfo("History", "Select a row first.")
            return
        path = e.get("file", "")
        if not path:
            messagebox.showinfo("History", "This entry has no file (download may have failed).")
            return
        if not open_path(path):
            messagebox.showerror("Error", f"File not found:\n{path}")

    def _history_open_folder(self):
        e = self._history_selected()
        if not e:
            messagebox.showinfo("History", "Select a row first.")
            return
        path = e.get("file", "") or self.output_dir
        if not reveal_path(path):
            messagebox.showerror("Error", f"Folder not found:\n{path}")

    def _history_copy_path(self):
        e = self._history_selected()
        if not e:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(e.get("file", ""))
        self._set_status("Path copied to clipboard")

    def _history_copy_url(self):
        e = self._history_selected()
        if not e:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(e.get("url", ""))
        self._set_status("URL copied to clipboard")

    def _history_remove(self):
        sel = self.history_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.history.remove_at(idx)
        self._refresh_history()

    def _history_clear(self):
        if not self.history.entries():
            return
        if messagebox.askyesno("Clear History", "Delete the entire download history?\n(Files are NOT deleted.)"):
            self.history.clear()
            self._refresh_history()

    # ── Settings Tab ───────────────────────────────
    def _build_settings_tab(self):
        frame = self._tab_settings
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Settings", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(15, 10))

        ttk.Label(frame, text="Output Directory:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.settings_dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(dir_frame, textvariable=self.settings_dir_var, width=60).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse...", command=self._browse_output).pack(side="right", padx=5)

        ttk.Label(frame, text="Proxy (optional):").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.settings_proxy_var = tk.StringVar(value=self.config.get("proxy", ""))
        ttk.Entry(frame, textvariable=self.settings_proxy_var, width=60).grid(row=2, column=1, sticky="ew", padx=10, pady=5)

        ttk.Label(frame, text="Cookies file (optional):").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        cookie_frame = ttk.Frame(frame)
        cookie_frame.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.settings_cookies_var = tk.StringVar(value=self.config.get("cookies_file", ""))
        ttk.Entry(cookie_frame, textvariable=self.settings_cookies_var, width=60).pack(side="left", fill="x", expand=True)
        ttk.Button(cookie_frame, text="Browse...", command=self._browse_cookies).pack(side="right", padx=5)

        ttk.Label(frame, text="YouTube player clients:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        pf = ttk.Frame(frame)
        pf.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        self.settings_clients_var = tk.StringVar(value=self.config.get("player_clients", "tv,web,android"))
        ttk.Entry(pf, textvariable=self.settings_clients_var, width=40).pack(side="left", padx=(0, 8))
        ttk.Label(pf, text="(try 'tv,web,android' or 'web_safari,android' to bypass bot checks)",
                  foreground="gray", font=("Segoe UI", 8)).pack(side="left")

        ttk.Label(frame,
                  text="Cookies file: export cookies.txt from your browser (Netscape format) so YouTube/private videos work.\n"
                       "Proxy example: http://127.0.0.1:7890",
                  foreground="gray", font=("Segoe UI", 8), justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 5))

        action = ttk.Frame(frame)
        action.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=10)
        ttk.Button(action, text="Save Settings", command=self._save_settings).pack(side="left", padx=5)
        ttk.Button(action, text="Update yt-dlp now", command=self._update_ytdlp).pack(side="left", padx=5)
        self.update_status_var = tk.StringVar()
        ttk.Label(action, textvariable=self.update_status_var, foreground="green").pack(side="left", padx=10)

        about_frame = ttk.LabelFrame(frame, text="About", padding=10)
        about_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        about_frame.columnconfigure(0, weight=1)

        logo_path = self._find_logo()
        if HAS_PIL and logo_path and os.path.exists(logo_path):
            pil_img = Image.open(logo_path)
            display_w = min(pil_img.width, 360)
            ratio = display_w / pil_img.width
            display_h = int(pil_img.height * ratio)
            pil_img = pil_img.resize((display_w, display_h), Image.LANCZOS)
            self._logo_tk = ImageTk.PhotoImage(pil_img)
            ttk.Label(about_frame, image=self._logo_tk).grid(row=0, column=0, pady=(0, 8))

        info_frame = ttk.Frame(about_frame)
        info_frame.grid(row=1, column=0)
        ttk.Label(info_frame, text="Nhảm AIO Downloader", font=("Segoe UI", 12, "bold")).pack(anchor="center")
        ttk.Label(info_frame, text="Developer: NhảmStudio", font=("Segoe UI", 9)).pack(anchor="center", pady=2)
        ttk.Label(info_frame, text="Powered by yt-dlp, Wattpad, fpdf2, ebooklib",
                  font=("Segoe UI", 8), foreground="gray").pack(anchor="center")

        link_frame = ttk.Frame(about_frame)
        link_frame.grid(row=2, column=0, pady=(8, 0))
        weblink = ttk.Label(link_frame, text="Website: topvl.net", foreground="blue", cursor="hand2", font=("Segoe UI", 9))
        weblink.pack(side="left", padx=10)
        weblink.bind("<Button-1>", lambda e: webbrowser.open("https://topvl.net"))
        donate = ttk.Label(link_frame, text="Donate: paypal.me/topvl", foreground="blue", cursor="hand2", font=("Segoe UI", 9))
        donate.pack(side="left", padx=10)
        donate.bind("<Button-1>", lambda e: webbrowser.open("https://paypal.me/topvl"))

    @staticmethod
    def _find_logo():
        base = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            p = os.path.join(exe_dir, "logo.png")
            if os.path.exists(p):
                return p
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, "logo.png")
            if os.path.exists(p):
                return p
        p = os.path.join(os.path.dirname(base), "logo.png")
        if os.path.exists(p):
            return p
        return None

    def _browse_output(self):
        path = filedialog.askdirectory(initialdir=self.output_dir)
        if path:
            self.settings_dir_var.set(path)

    def _browse_cookies(self):
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Cookies file", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.settings_cookies_var.set(path)

    def _save_settings(self):
        self.output_dir = self.settings_dir_var.get().strip() or self.output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.config["output_dir"] = self.output_dir
        self.config["proxy"] = self.settings_proxy_var.get().strip()
        self.config["cookies_file"] = self.settings_cookies_var.get().strip()
        self.config["player_clients"] = self.settings_clients_var.get().strip() or "tv,web,android"
        save_config(self.config)

        self.video_dl.configure(
            proxy=self.config["proxy"],
            cookies_file=self.config["cookies_file"],
            player_clients=self.config["player_clients"],
        )
        self._set_status(f"Settings saved. Output: {self.output_dir}")
        messagebox.showinfo("Settings", f"Settings saved.\nOutput directory:\n{self.output_dir}")

    def _update_ytdlp(self):
        self.update_status_var.set("Updating yt-dlp...")
        self._set_status("Updating yt-dlp...")

        def task():
            result = VideoDownloader.update_yt_dlp()
            self.root.after(0, lambda: self.update_status_var.set(result.splitlines()[0]))
            self.root.after(0, lambda: self._set_status("yt-dlp update finished"))
            self.root.after(0, lambda: messagebox.showinfo("Update yt-dlp", result))

        threading.Thread(target=task, daemon=True).start()

    # ── Main Loop ──────────────────────────────────
    def run(self):
        self.root.mainloop()
