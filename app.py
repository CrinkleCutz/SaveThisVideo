#!/usr/bin/env python3
"""SaveThisVideo — yt-dlp GUI wrapper for macOS"""

import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter.filedialog as fd
import tkinter.messagebox as mb
from pathlib import Path

import customtkinter as ctk
import yt_dlp
from yt_dlp.utils import download_range_func

APP_VERSION = "1.0.0"

# ── Layout constants ──────────────────────────────────────────────────────────
WINDOW_W      = 580
SIDE_PAD      = 20
CTK_LABEL_PAD = 8
WRAP          = WINDOW_W - SIDE_PAD * 2 - CTK_LABEL_PAD   # 532

DISK_WARN_BYTES = 500 * 1024 * 1024  # Warn when save destination has < 500 MB free

QUALITY_OPTIONS = {
    "Best Available":   "bestvideo+bestaudio/best",
    "4K (2160p)":       "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1080p":            "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":             "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":             "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":             "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "Audio Only (MP3)": "bestaudio/best",
}

# Parallel format strings that prefer H.264 (avc) video, with fallback to any codec.
# Audio-only is not listed here — it's always handled by the plain QUALITY_OPTIONS map.
QUALITY_OPTIONS_H264 = {
    "Best Available":   "bestvideo[vcodec~=avc]+bestaudio/bestvideo+bestaudio/best",
    "4K (2160p)":       "bestvideo[vcodec~=avc][height<=2160]+bestaudio/bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1080p":            "bestvideo[vcodec~=avc][height<=1080]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":             "bestvideo[vcodec~=avc][height<=720]+bestaudio/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":             "bestvideo[vcodec~=avc][height<=480]+bestaudio/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":             "bestvideo[vcodec~=avc][height<=360]+bestaudio/bestvideo[height<=360]+bestaudio/best[height<=360]",
}

# Known yt-dlp error fragments → user-facing copy
_ERROR_MAP = [
    ("Video unavailable",           "This video is unavailable."),
    ("Private video",               "This video is private."),
    ("age-restricted",              "This video is age-restricted and cannot be downloaded."),
    ("Sign in",                     "This video requires sign-in and cannot be downloaded."),
    ("members-only",                "This video is for channel members only."),
    ("This live event will begin",  "This stream has not started yet."),
    ("is not a valid URL",          "That doesn't look like a valid URL."),
    ("Unable to extract",           "Could not read this page. The URL may be unsupported."),
    ("HTTP Error 403",              "Access denied (HTTP 403). The site blocked this request."),
    ("HTTP Error 404",              "Video not found (HTTP 404). Check the link and try again."),
    ("HTTP Error 429",              "Too many requests (HTTP 429). Wait a moment and try again."),
    ("Unsupported URL",             "This URL is not supported by SaveThisVideo."),
    ("Unable to load cookies",      "Could not read browser cookies. Try closing the browser first, or set Cookies to None."),
    ("cookies",                     "Browser cookie error. Try closing the browser first, or set Cookies to None."),
]

COOKIE_BROWSERS = ["None", "Safari", "Chrome", "Firefox"]


class _Cancelled(Exception):
    """Raised inside the yt-dlp progress hook to abort an in-progress download."""


def _bundled_ffmpeg() -> str | None:
    """Return path to ffmpeg bundled by PyInstaller, or None to use system ffmpeg."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "bin", "ffmpeg")
    return None


def _friendly_error(raw: str) -> str:
    """Map a raw yt-dlp exception string to a user-facing message."""
    for fragment, message in _ERROR_MAP:
        if fragment.lower() in raw.lower():
            return message
    first = raw.split("\n")[0].strip()
    first = re.sub(r"^\[[\w:.]+\]\s+\S+:\s*", "", first)  # strip "[extractor] id: " prefix
    return first or "Download failed. Check the URL and try again."


def _parse_time(raw: str) -> float | None:
    """Parse 'SS', 'MM:SS', or 'HH:MM:SS' (decimals allowed) to seconds.
    Returns None for empty input. Raises ValueError on malformed input.
    """
    s = raw.strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) > 3:
        raise ValueError(raw)
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(raw)
    if any(n < 0 for n in nums):
        raise ValueError(raw)
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def _notify(title: str, message: str) -> None:
    """Post a macOS Notification Center notification via osascript. Never raises."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3, check=False,
        )
    except Exception as e:
        log.debug("Notification failed: %s", e)


def _setup_logging() -> None:
    """Attach a rotating file handler to the 'savethisvideo' logger.
    Logs are written to ~/Library/Logs/SaveThisVideo/app.log.
    """
    log_dir = Path.home() / "Library" / "Logs" / "SaveThisVideo"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger = logging.getLogger("savethisvideo")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)


# Module-level logger — handlers are added by _setup_logging() at startup.
log = logging.getLogger("savethisvideo")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"SaveThisVideo {APP_VERSION}")
        self.geometry(f"{WINDOW_W}x530")
        self.resizable(False, False)
        self._save_dir: Path = Path.home() / "Desktop"
        self._downloading = False
        self._cancel = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_saved_path: str = ""
        self._close_poll_count: int = 0
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        log.info("App started — version %s", APP_VERSION)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        pad = {"padx": SIDE_PAD}

        ctk.CTkLabel(self, text="Video URL", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(20, 4), **pad)

        url_row = ctk.CTkFrame(self, fg_color="transparent")
        url_row.grid(row=1, column=0, sticky="ew", pady=(0, 12), **pad)
        url_row.grid_columnconfigure(0, weight=1)

        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            url_row, textvariable=self._url_var, height=36,
            placeholder_text="Paste a link from YouTube, Vimeo, Twitter, and 1,000+ sites…")
        self._url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ctk.CTkButton(url_row, text="Paste", width=64, height=36,
                      command=self._paste).grid(row=0, column=1)

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=2, column=0, sticky="ew", pady=(0, 12), **pad)
        opts.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(opts, text="Quality", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(opts, text="Save to", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=1, sticky="w", padx=(16, 0), pady=(0, 4))

        self._quality_var = ctk.StringVar(value="Best Available")
        ctk.CTkOptionMenu(opts, variable=self._quality_var,
                          values=list(QUALITY_OPTIONS.keys()),
                          width=185, height=36).grid(row=1, column=0)

        h264_row = ctk.CTkFrame(opts, fg_color="transparent")
        h264_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._h264_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(h264_row, text="Prefer H.264",
                        variable=self._h264_var,
                        font=ctk.CTkFont(size=12),
                        checkbox_width=18, checkbox_height=18).grid(
            row=0, column=0, padx=(0, 6))
        ctk.CTkLabel(h264_row, text="(vs. site codec)",
                     font=ctk.CTkFont(size=11), text_color="gray").grid(
            row=0, column=1)

        save_row = ctk.CTkFrame(opts, fg_color="transparent")
        save_row.grid(row=1, column=1, sticky="ew", padx=(16, 0))
        save_row.grid_columnconfigure(0, weight=1)

        self._path_lbl = ctk.CTkLabel(
            save_row, text=self._trunc_path(self._save_dir),
            anchor="w", font=ctk.CTkFont(size=12), text_color="gray")
        self._path_lbl.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(save_row, text="Browse…", width=80, height=36,
                      command=self._browse).grid(row=0, column=1, padx=(8, 0))

        # ── Cookie row ────────────────────────────────────────────────────────
        cookie_row = ctk.CTkFrame(self, fg_color="transparent")
        cookie_row.grid(row=3, column=0, sticky="w", pady=(0, 2), **pad)

        ctk.CTkLabel(cookie_row, text="Cookies from browser:",
                     font=ctk.CTkFont(size=12), text_color="gray").grid(
            row=0, column=0, padx=(0, 8))

        self._cookies_var = ctk.StringVar(value="None")
        ctk.CTkOptionMenu(cookie_row, variable=self._cookies_var,
                          values=COOKIE_BROWSERS,
                          width=120, height=30).grid(row=0, column=1)

        ctk.CTkLabel(
            self,
            text="Use your browser's login to reach private, members-only, or age-restricted videos.",
            font=ctk.CTkFont(size=11), text_color="gray", anchor="w",
            wraplength=WRAP, justify="left"
        ).grid(row=4, column=0, sticky="w", pady=(0, 10), **pad)

        # ── Clip row ──────────────────────────────────────────────────────────
        clip_row = ctk.CTkFrame(self, fg_color="transparent")
        clip_row.grid(row=5, column=0, sticky="w", pady=(0, 2), **pad)

        self._clip_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(clip_row, text="Clip section",
                        variable=self._clip_var, command=self._toggle_clip,
                        font=ctk.CTkFont(size=12),
                        checkbox_width=18, checkbox_height=18).grid(
            row=0, column=0, padx=(0, 12))

        self._start_var = ctk.StringVar()
        self._start_entry = ctk.CTkEntry(
            clip_row, textvariable=self._start_var,
            placeholder_text="Start  e.g. 1:23", width=130, height=28)
        self._start_entry.grid(row=0, column=1, padx=(0, 8))

        self._end_var = ctk.StringVar()
        self._end_entry = ctk.CTkEntry(
            clip_row, textvariable=self._end_var,
            placeholder_text="End  e.g. 2:45", width=130, height=28)
        self._end_entry.grid(row=0, column=2)

        self._start_entry.grid_remove()
        self._end_entry.grid_remove()

        ctk.CTkLabel(
            self,
            text="Download only a portion of the video — leave a field blank to run to the start or end.",
            font=ctk.CTkFont(size=11), text_color="gray", anchor="w",
            wraplength=WRAP, justify="left"
        ).grid(row=6, column=0, sticky="w", pady=(0, 10), **pad)

        # ── Download button ───────────────────────────────────────────────────
        self._dl_btn = ctk.CTkButton(
            self, text="Download", height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._start_download)
        self._dl_btn.grid(row=7, column=0, sticky="ew", pady=(0, 10), **pad)
        self._btn_fg    = self._dl_btn.cget("fg_color")
        self._btn_hover = self._dl_btn.cget("hover_color")

        self._progress = ctk.CTkProgressBar(self, height=8, progress_color="#2ecc71")
        self._progress.set(0)
        self._progress.grid(row=8, column=0, sticky="ew", pady=(0, 10), **pad)

        # Line 1 — filename (wraps naturally at WRAP; no truncation)
        self._filename_var = ctk.StringVar(value="")
        self._filename_lbl = ctk.CTkLabel(
            self, textvariable=self._filename_var,
            font=ctk.CTkFont(size=12), text_color="gray",
            wraplength=WRAP, justify="center")
        self._filename_lbl.grid(row=9, column=0, padx=SIDE_PAD, pady=(0, 2))

        # Line 2 — speed / ETA / state (always a single short line)
        self._meta_var = ctk.StringVar(value="Ready")
        self._meta_lbl = ctk.CTkLabel(
            self, textvariable=self._meta_var,
            font=ctk.CTkFont(size=12), text_color="gray")
        self._meta_lbl.grid(row=10, column=0, padx=SIDE_PAD, pady=(0, 16))

    def _toggle_clip(self):
        """Show or hide the Start/End entry fields when Clip section is toggled."""
        if self._clip_var.get():
            self._start_entry.grid()
            self._end_entry.grid()
        else:
            self._start_entry.grid_remove()
            self._end_entry.grid_remove()
            self._start_var.set("")
            self._end_var.set("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _trunc_path(path: Path, n: int = 46) -> str:
        """Truncate a filesystem path for the save-to label."""
        s = str(path)
        return s if len(s) <= n else "…" + s[-(n - 1):]

    def _set_status(self, filename: str = "", meta: str = "", error: bool = False):
        """Update both status lines. Must be called on the main thread."""
        self._filename_var.set(filename)
        self._meta_var.set(meta)
        color = "#e74c3c" if error else "gray"
        self._filename_lbl.configure(text_color=color)
        self._meta_lbl.configure(text_color=color)

    @staticmethod
    def _validate_url(url: str) -> str | None:
        """Return a user-facing error string if url is not a valid http/https URL, else None."""
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return "Please paste an http or https video link."
        return None

    # ── Actions ───────────────────────────────────────────────────────────────

    def _paste(self):
        try:
            text = self.clipboard_get().strip()
        except Exception:
            self._set_status(meta="Nothing on clipboard to paste.")
            return
        if not text:
            self._set_status(meta="Nothing on clipboard to paste.")
            return
        self._url_var.set(text)

    def _browse(self):
        path = fd.askdirectory(initialdir=str(self._save_dir), title="Choose download folder")
        if path:
            self._save_dir = Path(path)
            self._path_lbl.configure(text=self._trunc_path(self._save_dir))

    def _on_close(self):
        """Handle window close: cancel any active download gracefully, then destroy."""
        if self._downloading:
            self._cancel.set()
            self._dl_btn.configure(text="Closing…", state="disabled")
            self._close_poll_count = 0
            self.after(100, self._wait_and_close)
        else:
            log.info("App closed.")
            self.destroy()

    def _wait_and_close(self):
        """Poll until the worker exits (max 30 × 100 ms = 3 s), then destroy."""
        self._close_poll_count += 1
        if self._worker_thread and self._worker_thread.is_alive() and self._close_poll_count < 30:
            self.after(100, self._wait_and_close)
        else:
            log.info("App closed.")
            self.destroy()

    def _start_download(self):
        if self._downloading:
            self._cancel.set()
            self._dl_btn.configure(text="Cancelling…", state="disabled")
            return

        url = self._url_var.get().strip()
        if not url:
            self._set_status(meta="Please paste a URL first.", error=True)
            return

        url_error = self._validate_url(url)
        if url_error:
            self._set_status(meta=url_error, error=True)
            return

        # Pre-flight disk space check
        try:
            free = shutil.disk_usage(self._save_dir).free
            if free < DISK_WARN_BYTES:
                free_mb = free // (1024 * 1024)
                self._set_status(
                    meta=f"Low disk space ({free_mb} MB free). Free up space and try again.",
                    error=True)
                return
        except OSError:
            pass  # Cannot determine — proceed; yt-dlp will surface the error if needed

        # Capture UI state on the main thread before the worker starts (D2)
        quality_key = self._quality_var.get()
        save_dir    = self._save_dir
        cookies_key = self._cookies_var.get()
        h264        = self._h264_var.get()

        # Clip section: parse Start/End times if toggle is on
        clip_range: tuple[float, float | None] | None = None
        if self._clip_var.get():
            try:
                start_sec = _parse_time(self._start_var.get())
                end_sec   = _parse_time(self._end_var.get())
            except ValueError as e:
                self._set_status(
                    meta=f"Invalid clip time: {e.args[0]!r}. Use SS, MM:SS, or HH:MM:SS.",
                    error=True)
                return
            if start_sec is None and end_sec is None:
                self._set_status(
                    meta="Clip section is on — enter a Start and/or End time.", error=True)
                return
            if start_sec is not None and end_sec is not None and end_sec <= start_sec:
                self._set_status(meta="Clip End must be after Start.", error=True)
                return
            clip_range = (start_sec or 0.0, end_sec)

        self._downloading = True
        self._last_saved_path = ""
        self._cancel.clear()
        self._dl_btn.configure(
            text="Cancel",
            fg_color=("#c0392b", "#922b21"),
            hover_color=("#a93226", "#7b241c"))
        self._progress.set(0)
        self._set_status(filename="", meta="Starting…")   # Clear previous filename (S3)

        log.info("Download started — quality=%s cookies=%s h264=%s clip=%s dest=%s",
                 quality_key, cookies_key, h264, clip_range, save_dir)

        self._worker_thread = threading.Thread(
            target=self._worker,
            args=(url, quality_key, save_dir, cookies_key, h264, clip_range),
            daemon=True)
        self._worker_thread.start()

    # ── Playlist detection ────────────────────────────────────────────────────

    def _probe_playlist(self, url: str, cookies_key: str) -> int | None:
        """Return entry count if url resolves to a playlist, else None.
        Runs synchronously on the worker thread.
        """
        opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        ffmpeg = _bundled_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        if cookies_key != "None":
            opts["cookiesfrombrowser"] = (cookies_key.lower(),)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info and info.get("_type") == "playlist":
                return len(info.get("entries") or [])
        except Exception:
            pass
        return None

    def _ask_playlist(self, count: int) -> bool:
        """Show a playlist confirmation dialog on the main thread; block the worker until answered.
        Returns True if the user confirms, False to cancel.
        """
        result = {"confirmed": False}
        done   = threading.Event()

        def _show():
            confirmed = mb.askyesno(
                title="Playlist Detected",
                message=f"This link contains {count} videos.\n\nDownload all of them?",
                detail="Choose No to cancel. Large playlists may take a long time.",
                icon="question",
            )
            result["confirmed"] = confirmed
            done.set()

        self.after(0, _show)
        done.wait(timeout=120)   # Treat no response within 2 min as cancel
        return result["confirmed"]

    # ── Download worker (background thread) ───────────────────────────────────

    def _worker(self, url: str, quality_key: str, save_dir: Path,
                cookies_key: str, h264: bool,
                clip_range: tuple[float, float | None] | None):
        is_audio = quality_key == "Audio Only (MP3)"
        if h264 and not is_audio:
            fmt = QUALITY_OPTIONS_H264[quality_key]
        else:
            fmt = QUALITY_OPTIONS[quality_key]

        # Playlist check — probe before committing to download
        count = self._probe_playlist(url, cookies_key)
        if count is not None and count > 1:
            if not self._ask_playlist(count):
                self.after(0, self._on_cancelled)
                return

        postprocessors = []
        if is_audio:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })

        ydl_opts = {
            "format":              fmt,
            "outtmpl":             str(save_dir / "%(title)s.%(ext)s"),
            "merge_output_format": None if is_audio else "mp4",
            "postprocessors":      postprocessors,
            "progress_hooks":      [self._hook],
            "quiet":               True,
            "no_warnings":         True,
            "retries":             10,
            "fragment_retries":    10,
            "file_access_retries": 5,
        }
        ffmpeg = _bundled_ffmpeg()
        if ffmpeg:
            ydl_opts["ffmpeg_location"] = ffmpeg
        if cookies_key != "None":
            ydl_opts["cookiesfrombrowser"] = (cookies_key.lower(),)
        if clip_range is not None:
            ydl_opts["download_ranges"] = download_range_func(None, [clip_range])
            ydl_opts["force_keyframes_at_cuts"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if self._cancel.is_set():
                self.after(0, self._on_cancelled)
            else:
                self.after(0, self._on_done)
        except _Cancelled:
            self.after(0, self._on_cancelled)
        except Exception as e:
            if self._cancel.is_set():
                self.after(0, self._on_cancelled)
            else:
                msg = _friendly_error(str(e))
                log.error("Download failed — %s", str(e).split("\n")[0])
                self.after(0, self._on_error, msg)

    def _hook(self, d: dict):
        """Progress callback — runs on background thread; all UI updates via after()."""
        if self._cancel.is_set():
            raise _Cancelled()

        status = d.get("status")

        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total      = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed      = d.get("speed") or 0
            eta        = d.get("eta")
            pct        = (downloaded / total) if total else 0

            if speed >= 1_048_576:
                speed_str = f"{speed / 1_048_576:.1f} MB/s"
            elif speed:
                speed_str = f"{speed / 1024:.0f} KB/s"
            else:
                speed_str = ""

            eta_str  = f"ETA {int(eta) // 60}:{int(eta) % 60:02d}" if eta else ""
            meta     = "  •  ".join(x for x in [speed_str, eta_str] if x)
            filename = os.path.basename(d.get("filename", ""))
            self.after(0, self._tick, pct, filename, meta)

        elif status == "finished":
            # Capture the final output path for the completion message (S2)
            self._last_saved_path = d.get("filename", "")
            self.after(0, self._tick, 1.0, "", "Processing…")

    def _tick(self, pct: float, filename: str, meta: str):
        self._progress.set(pct)
        self._set_status(filename=filename, meta=meta)

    # ── Completion handlers (always on main thread via after()) ───────────────

    def _on_done(self):
        saved_name = os.path.basename(self._last_saved_path)
        self._reset()
        self._progress.set(1.0)
        if saved_name:
            self._set_status(filename=saved_name, meta=f"✓  Saved to {self._save_dir}")
        else:
            self._set_status(meta=f"✓  Saved to {self._save_dir}")
        log.info("Download complete — file=%s", saved_name or "(unknown)")
        _notify("Download complete",
                saved_name if saved_name else f"Saved to {self._save_dir}")

    def _on_cancelled(self):
        self._reset()
        self._set_status(meta="Download cancelled.")
        log.info("Download cancelled.")

    def _on_error(self, msg: str):
        self._reset()
        self._set_status(meta=f"Error: {msg}", error=True)

    def _reset(self):
        self._downloading = False
        self._progress.set(0)   # Return bar to zero on every terminal state (S9)
        self._dl_btn.configure(
            text="Download", state="normal",
            fg_color=self._btn_fg,
            hover_color=self._btn_hover)


if __name__ == "__main__":
    ctk.set_appearance_mode("system")    # Inside __main__ guard — no side effect on import (D9)
    ctk.set_default_color_theme("blue")
    _setup_logging()
    App().mainloop()
