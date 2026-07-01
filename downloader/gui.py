import os
import sys
import re
import webbrowser
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
from urllib.parse import urlparse

from .wattpad import WattpadStory, format_as_markdown
from .viddl import VideoDownloader, preset_to_format
from .converter import text_to_pdf, text_to_epub
from PIL import Image, ImageTk


class DownloaderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AIscan Downloader - All-in-One Download Tool")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        if os.name == "nt":
            try:
                self.root.iconbitmap(default="")
            except Exception:
                pass

        self.output_dir = os.path.join(os.path.expanduser("~"), "Downloads", "AIscanDownloads")
        os.makedirs(self.output_dir, exist_ok=True)

        self.video_dl = VideoDownloader()
        self._build_ui()

    def _build_ui(self):
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self._tab_story = ttk.Frame(self.notebook)
        self._tab_video = ttk.Frame(self.notebook)
        self._tab_stream = ttk.Frame(self.notebook)
        self._tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self._tab_story, text="  Story  ")
        self.notebook.add(self._tab_video, text="  Video  ")
        self.notebook.add(self._tab_stream, text="  Streaming  ")
        self.notebook.add(self._tab_settings, text="  Settings  ")

        self._build_story_tab()
        self._build_video_tab()
        self._build_stream_tab()
        self._build_settings_tab()

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom", padx=2, pady=2)

    # ── Story Tab ─────────────────────────────────
    def _build_story_tab(self):
        frame = self._tab_story
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="Wattpad URL:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(15,5))
        self.story_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.story_url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=(15,5))
        self.fetch_btn = ttk.Button(frame, text="Fetch Story Info", command=self._fetch_story)
        self.fetch_btn.grid(row=0, column=2, padx=10, pady=(15,5))

        # Story info
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

        # Format selector
        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=5)
        ttk.Label(fmt_frame, text="Output Format:").pack(side="left", padx=5)
        self.story_format_var = tk.StringVar(value="EPUB")
        ttk.Radiobutton(fmt_frame, text="EPUB (Recommended)", variable=self.story_format_var, value="EPUB").pack(side="left", padx=5)
        ttk.Radiobutton(fmt_frame, text="PDF", variable=self.story_format_var, value="PDF").pack(side="left", padx=5)

        ttk.Button(fmt_frame, text="Download Story", command=self._download_story).pack(side="left", padx=20)

        # Progress
        self.story_progress = ttk.Progressbar(frame, mode="determinate")
        self.story_progress.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        self.story_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.story_status_var, foreground="gray").grid(row=3, column=0, columnspan=3, sticky="e", padx=15)

        # Log
        self.story_log = scrolledtext.ScrolledText(frame, height=10, state="disabled", font=("Consolas", 9))
        self.story_log.grid(row=4, column=0, columnspan=3, sticky="nsew", padx=10, pady=(5,10))

    def _log_story(self, msg):
        self.story_log.configure(state="normal")
        self.story_log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.story_log.see("end")
        self.story_log.configure(state="disabled")
        self.root.update_idletasks()

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

        def task():
            try:
                self.root.after(0, lambda: self.story_status_var.set("Downloading chapters..."))
                total = len(story.chapters)

                def on_progress(idx, t, title):
                    pct = (idx / t) * 50
                    self.root.after(0, lambda: self.story_progress.configure(value=pct))
                    self.root.after(0, lambda: self._log_story(f"Chapter {idx+1}/{t}: {title[:50]}"))

                ch_texts = story.fetch_all_chapters(progress_callback=on_progress)

                md_text = format_as_markdown(story, ch_texts)
                base_name = re.sub(r'[\\/*?:"<>|]', "_", story.title)[:60]

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

                self.root.after(0, lambda: self.story_progress.configure(value=100))
                self.root.after(0, lambda: self.story_status_var.set(f"Saved: {path}"))
                self.root.after(0, lambda: self._log_story(f"Saved to: {path}"))
                self.root.after(0, lambda: messagebox.showinfo("Complete", f"Story saved to:\n{path}"))
            except Exception as e:
                self.root.after(0, lambda: self._log_story(f"Download error: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.root.after(0, lambda: self.story_status_var.set(""))

        import time
        threading.Thread(target=task, daemon=True).start()

    # ── Video Tab ─────────────────────────────────
    def _build_video_tab(self):
        frame = self._tab_video
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Video URL:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(15,5))
        self.video_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.video_url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=(15,5))
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=0, column=2, padx=5, pady=(15,5))
        self.info_btn = ttk.Button(btn_frame, text="Get Info", command=self._video_info)
        self.info_btn.pack(side="left", padx=2)
        self.dl_btn = ttk.Button(btn_frame, text="Download", command=self._download_video)
        self.dl_btn.pack(side="left", padx=2)

        # Video info
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
        # Default quality options (refined after Get Info)
        self.vid_format_combo["values"] = [p[0] for p in VideoDownloader.PRESETS]
        self.vid_format_combo.current(0)

        # ffmpeg status
        ffmpeg_ok = self.video_dl.has_ffmpeg
        ffmpeg_text = "ffmpeg: Ready" if ffmpeg_ok else "ffmpeg: Not found (auto-download on download)"
        self.vid_ffmpeg_var = tk.StringVar(value=ffmpeg_text)
        ttk.Label(info_frame, textvariable=self.vid_ffmpeg_var,
                  foreground="green" if ffmpeg_ok else "orange",
                  font=("Segoe UI", 8)).grid(row=4, column=0, columnspan=4, sticky="w", padx=5)

        # Progress
        self.vid_progress = ttk.Progressbar(frame, mode="determinate")
        self.vid_progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        self.vid_speed_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.vid_speed_var, foreground="gray").grid(row=2, column=0, columnspan=3, sticky="e", padx=15)
        self.vid_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.vid_status_var, foreground="blue").grid(row=3, column=0, columnspan=3, sticky="w", padx=15)

        # Cancel button
        self.cancel_vid_btn = ttk.Button(frame, text="Cancel", command=self.video_dl.cancel)
        self.cancel_vid_btn.grid(row=3, column=2, sticky="e", padx=15)
        self.cancel_vid_btn.configure(state="disabled")

        # Log
        self.vid_log = scrolledtext.ScrolledText(frame, height=10, state="disabled", font=("Consolas", 9))
        self.vid_log.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=10, pady=(5,10))

    def _log_video(self, msg):
        self.vid_log.configure(state="normal")
        self.vid_log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.vid_log.see("end")
        self.vid_log.configure(state="disabled")
        self.root.update_idletasks()

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
                dur = info.get("duration", 0)
                dur_str = f"{dur//60}m {dur%60}s" if dur else "Unknown"
                self.root.after(0, lambda: self.vid_title_var.set(info.get("title", "")[:80]))
                self.root.after(0, lambda: self.vid_dur_var.set(dur_str))
                self.root.after(0, lambda: self.vid_uploader_var.set(info.get("uploader", "")))

                # Load quality presets available for this video
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

        # Resolve preset to format string
        fmt_raw = self.vid_format_var.get()
        fmt_id = preset_to_format(fmt_raw)

        self.dl_btn.configure(state="disabled")
        self.cancel_vid_btn.configure(state="normal")
        self.video_dl.reset_cancel()
        self._log_video(f"Starting download: {url}")
        self._log_video(f"Format: {fmt_id}")

        def on_progress(data):
            pct = data.get("percent", 0)
            speed = data.get("speed", 0)
            self.root.after(0, lambda: self.vid_progress.configure(value=pct))
            if speed:
                speed_mb = speed / 1024 / 1024
                self.root.after(0, lambda: self.vid_speed_var.set(f"{speed_mb:.1f} MB/s"))

        def on_complete(data):
            self.root.after(0, lambda: self.dl_btn.configure(state="normal"))
            self.root.after(0, lambda: self.cancel_vid_btn.configure(state="disabled"))
            if "error" in data:
                self.root.after(0, lambda: self._log_video(f"Download failed: {data['error']}"))
                self.root.after(0, lambda: messagebox.showerror("Error", data["error"]))
            else:
                self.root.after(0, lambda: self.vid_progress.configure(value=100))
                self.root.after(0, lambda: self.vid_status_var.set("Complete!"))
                f = data.get("file", "")
                self.root.after(0, lambda: self._log_video(f"Downloaded: {f}"))
                self.root.after(0, lambda: messagebox.showinfo("Complete", f"Saved to:\n{f}"))

        def task():
            self.video_dl.download(
                url=url,
                output_dir=self.output_dir,
                format_spec=fmt_id,
                on_progress=on_progress,
                on_complete=on_complete
            )

        threading.Thread(target=task, daemon=True).start()

    # ── Streaming Tab ─────────────────────────────
    def _build_stream_tab(self):
        frame = self._tab_stream
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Stream URL:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(15,5))
        self.stream_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.stream_url_var).grid(row=0, column=1, sticky="ew", padx=10, pady=(15,5))

        self.stream_dl_btn = ttk.Button(frame, text="Download Stream", command=self._download_stream)
        self.stream_dl_btn.grid(row=0, column=2, padx=10, pady=(15,5))

        # Supported sites list
        sites_frame = ttk.LabelFrame(frame, text="Supported Streaming Sites", padding=5)
        sites_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=5)

        sites_text = ", ".join(sorted(VideoDownloader.SUPPORTED_SITES))
        ttk.Label(sites_frame, text=sites_text, wraplength=800, font=("Segoe UI", 8)).pack(padx=5, pady=5)

        ttk.Label(frame, text="Tip: For DRM-protected streams (Netflix, Disney+, Hulu), additional tools required.",
                  foreground="gray", font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=3, sticky="w", padx=10)

        # Format options - reuse presets
        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        self.stream_format_var = tk.StringVar(value="Best Quality (recommended)")
        self.stream_format_combo = ttk.Combobox(fmt_frame, textvariable=self.stream_format_var, width=40, state="readonly")
        self.stream_format_combo["values"] = [p[0] for p in VideoDownloader.PRESETS]
        self.stream_format_combo.current(0)
        self.stream_format_combo.pack(side="left", padx=5)

        # Progress
        self.stream_progress = ttk.Progressbar(frame, mode="determinate")
        self.stream_progress.grid(row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        self.stream_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.stream_status_var, foreground="blue").grid(row=4, column=0, columnspan=3, sticky="e", padx=15)

        self.cancel_stream_btn = ttk.Button(frame, text="Cancel", command=self.video_dl.cancel)
        self.cancel_stream_btn.grid(row=4, column=2, sticky="e", padx=15)
        self.cancel_stream_btn.configure(state="disabled")

        # Log
        self.stream_log = scrolledtext.ScrolledText(frame, height=10, state="disabled", font=("Consolas", 9))
        self.stream_log.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=10, pady=(5,10))

    def _log_stream(self, msg):
        self.stream_log.configure(state="normal")
        self.stream_log.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.stream_log.see("end")
        self.stream_log.configure(state="disabled")
        self.root.update_idletasks()

    def _download_stream(self):
        url = self.stream_url_var.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a stream URL")
            return
        fmt = preset_to_format(self.stream_format_var.get())
        self.stream_dl_btn.configure(state="disabled")
        self.cancel_stream_btn.configure(state="normal")
        self.video_dl.reset_cancel()
        self._log_stream(f"Starting stream download: {url}")

        def on_progress(data):
            pct = data.get("percent", 0)
            self.root.after(0, lambda: self.stream_progress.configure(value=pct))
            if pct >= 0:
                self.root.after(0, lambda: self.stream_status_var.set(f"{pct:.1f}%"))

        def on_complete(data):
            self.root.after(0, lambda: self.stream_dl_btn.configure(state="normal"))
            self.root.after(0, lambda: self.cancel_stream_btn.configure(state="disabled"))
            if "error" in data:
                self.root.after(0, lambda: self._log_stream(f"Failed: {data['error']}"))
                self.root.after(0, lambda: messagebox.showerror("Error", data["error"]))
            else:
                self.root.after(0, lambda: self.stream_progress.configure(value=100))
                self.root.after(0, lambda: self.stream_status_var.set("Complete!"))
                f = data.get("file", "")
                self.root.after(0, lambda: self._log_stream(f"Saved: {f}"))
                self.root.after(0, lambda: messagebox.showinfo("Complete", f"Saved to:\n{f}"))

        def task():
            self.video_dl.download(
                url=url,
                output_dir=self.output_dir,
                format_spec=fmt,
                on_progress=on_progress,
                on_complete=on_complete,
            )

        threading.Thread(target=task, daemon=True).start()

    # ── Settings Tab ───────────────────────────────
    def _build_settings_tab(self):
        frame = self._tab_settings
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Settings", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(15,10))

        # Output directory
        ttk.Label(frame, text="Output Directory:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.settings_dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(dir_frame, textvariable=self.settings_dir_var, width=60).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse...", command=self._browse_output).pack(side="right", padx=5)

        ttk.Button(frame, text="Save Settings", command=self._save_settings).grid(row=2, column=0, columnspan=2, padx=10, pady=20)

        # About section with logo
        about_frame = ttk.LabelFrame(frame, text="About", padding=10)
        about_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        about_frame.columnconfigure(0, weight=1)

        # Logo - try multiple locations
        def _find_logo():
            base = os.path.dirname(os.path.abspath(__file__))
            # alongside EXE
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                p = os.path.join(exe_dir, "logo.png")
                if os.path.exists(p):
                    return p
            # PyInstaller temp dir
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                p = os.path.join(meipass, "logo.png")
                if os.path.exists(p):
                    return p
            # source tree
            p = os.path.join(os.path.dirname(base), "logo.png")
            if os.path.exists(p):
                return p
            return None
        logo_path = _find_logo()
        if logo_path and os.path.exists(logo_path):
            pil_img = Image.open(logo_path)
            display_w = min(pil_img.width, 400)
            ratio = display_w / pil_img.width
            display_h = int(pil_img.height * ratio)
            pil_img = pil_img.resize((display_w, display_h), Image.LANCZOS)
            self._logo_tk = ImageTk.PhotoImage(pil_img)
            logo_label = ttk.Label(about_frame, image=self._logo_tk)
            logo_label.grid(row=0, column=0, pady=(0, 8))

        # Brand info
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
        weblink.bind("<Button-1>", lambda e: self._open_url("https://topvl.net"))
        donate = ttk.Label(link_frame, text="Donate: paypal.me/topvl", foreground="blue", cursor="hand2", font=("Segoe UI", 9))
        donate.pack(side="left", padx=10)
        donate.bind("<Button-1>", lambda e: self._open_url("https://paypal.me/topvl"))

    def _browse_output(self):
        path = filedialog.askdirectory(initialdir=self.output_dir)
        if path:
            self.settings_dir_var.set(path)

    def _save_settings(self):
        self.output_dir = self.settings_dir_var.get()
        os.makedirs(self.output_dir, exist_ok=True)
        messagebox.showinfo("Settings", f"Output directory set to:\n{self.output_dir}")

    def _open_url(self, url):
        webbrowser.open(url)

    # ── Main Loop ──────────────────────────────────
    def run(self):
        self.root.mainloop()
