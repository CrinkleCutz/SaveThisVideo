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
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
from pathlib import Path

import customtkinter as ctk
import yt_dlp
from yt_dlp.utils import download_range_func, sanitize_filename

APP_VERSION = "1.2"
APP_TITLE   = "SAVE THIS VIDEO!"

# ── Layout constants ──────────────────────────────────────────────────────────
WINDOW_W      = 640
WINDOW_H      = 660
SIDE_PAD      = 24
CTK_LABEL_PAD = 8
WRAP          = WINDOW_W - SIDE_PAD * 2 - CTK_LABEL_PAD   # 584
CAPTION_WRAP  = WRAP - 28                                 # Indented under checkbox
DOCK_H        = 92

DISK_WARN_BYTES = 500 * 1024 * 1024  # Warn when save destination has < 500 MB free

# ── Visual tokens (dark theme, blue accent) ───────────────────────────────────
COLOR_BG         = "#121212"  # Page background (deepest layer)
COLOR_SURFACE    = "#181818"  # Dock / elevated surfaces
COLOR_INTERACT   = "#575757"  # Inputs, inactive pills — lifted ~20% toward white for contrast
COLOR_HOVER      = "#616161"  # Hover-state fill
COLOR_ACCENT     = "#539df5"  # Blue accent (CTA, active pill, progress, checked)
COLOR_ACCENT_HOV = "#3d8ae0"
COLOR_DANGER     = "#f3727f"  # Negative / cancel
COLOR_DANGER_HOV = "#e26570"
COLOR_TEXT       = "#ffffff"  # All text is pure white — hierarchy comes from weight/size
COLOR_DIVIDER    = "#272727"  # Hairline divider
COLOR_BORDER_HI  = "#7c7c7c"  # Outlined-pill border

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

# Short labels for the segmented quality pill row — must cover every key in QUALITY_OPTIONS.
QUALITY_SHORT = {
    "Best Available":   "BEST",
    "4K (2160p)":       "4K",
    "1080p":            "1080p",
    "720p":             "720p",
    "480p":             "480p",
    "360p":             "360p",
    "Audio Only (MP3)": "AUDIO",
}


class _Cancelled(Exception):
    """Raised inside the yt-dlp progress hook to abort an in-progress download."""


def _bundled_ffmpeg() -> str | None:
    """Return path to ffmpeg bundled by PyInstaller, or None to use system ffmpeg."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "bin", "ffmpeg")
    return None


def _resource_path(name: str) -> Path:
    """Resolve a bundled resource both in dev and in the PyInstaller-packaged .app."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name


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
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        x = max(0, (self.winfo_screenwidth()  - WINDOW_W) // 2)
        y = max(0, (self.winfo_screenheight() - WINDOW_H) // 2)
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        self._save_dir: Path = Path.home() / "Desktop"
        self._downloading = False
        self._cancel = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_saved_path: str = ""
        self._close_poll_count: int = 0
        self._quality_btns: dict[str, ctk.CTkButton] = {}
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_window_icon()
        self._build_ui()
        log.info("App started — version %s", APP_VERSION)

    def _set_window_icon(self) -> None:
        """Attach app_icon.png to the Tk window. Best-effort — never raises.

        On macOS this sets the titlebar / minimized-window icon; the Dock icon
        in the distributed .app comes from icon.icns via PyInstaller --icon.
        """
        path = _resource_path("app_icon.png")
        if not path.exists():
            return
        try:
            self._app_icon = tk.PhotoImage(file=str(path))
            self.iconphoto(True, self._app_icon)
        except Exception as e:
            log.debug("Window icon failed: %s", e)

    # ── UI construction ────────────────────────────────────────────────────────

    def _section_label(self, text: str, row: int) -> None:
        """Uppercase, tracked muted label — Spotify's systematic section voice."""
        ctk.CTkLabel(
            self, text=text.upper(), anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT,
        ).grid(row=row, column=0, sticky="w", padx=SIDE_PAD, pady=(0, 6))

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(10, weight=1)  # Spacer row pushes dock to bottom

        # ── Header strip ──────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SIDE_PAD, pady=(18, 14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=APP_TITLE, anchor="w",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"v{APP_VERSION}", anchor="e",
                     font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT).grid(row=0, column=1, sticky="e")

        # ── Paste a link ──────────────────────────────────────────────────────
        self._section_label("Paste a link", row=1)

        url_row = ctk.CTkFrame(self, fg_color="transparent")
        url_row.grid(row=2, column=0, sticky="ew", padx=SIDE_PAD, pady=(0, 18))
        url_row.grid_columnconfigure(0, weight=1)

        self._url_var = ctk.StringVar()
        self._url_entry = ctk.CTkEntry(
            url_row, textvariable=self._url_var, height=40, corner_radius=20,
            fg_color=COLOR_INTERACT, border_color=COLOR_INTERACT,
            text_color=COLOR_TEXT, placeholder_text_color=COLOR_TEXT,
            font=ctk.CTkFont(size=13),
            placeholder_text="Paste a YouTube, Vimeo, Twitter link…")
        self._url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._url_entry.bind("<Return>", lambda _: self._start_download())

        ctk.CTkButton(url_row, text="PASTE", width=84, height=40, corner_radius=20,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      border_width=1, border_color=COLOR_BORDER_HI,
                      text_color=COLOR_TEXT,
                      font=ctk.CTkFont(size=11, weight="bold"),
                      command=self._paste).grid(row=0, column=1)

        # ── Quality (segmented pills) ─────────────────────────────────────────
        self._section_label("Quality", row=3)

        q_row = ctk.CTkFrame(self, fg_color="transparent")
        q_row.grid(row=4, column=0, sticky="ew", padx=SIDE_PAD, pady=(0, 18))
        for i in range(len(QUALITY_OPTIONS)):
            q_row.grid_columnconfigure(i, weight=1, uniform="qual")

        self._quality_var = ctk.StringVar(value="Best Available")
        for i, key in enumerate(QUALITY_OPTIONS.keys()):
            btn = ctk.CTkButton(
                q_row, text=QUALITY_SHORT[key], height=32, corner_radius=16,
                fg_color=COLOR_INTERACT, hover_color=COLOR_HOVER,
                text_color=COLOR_TEXT,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda k=key: self._select_quality(k))
            btn.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
            self._quality_btns[key] = btn
        self._select_quality("Best Available")

        # ── Save to ───────────────────────────────────────────────────────────
        self._section_label("Save to", row=5)

        save_row = ctk.CTkFrame(self, fg_color="transparent")
        save_row.grid(row=6, column=0, sticky="ew", padx=SIDE_PAD, pady=(0, 18))
        save_row.grid_columnconfigure(0, weight=1)

        self._path_lbl = ctk.CTkLabel(
            save_row, text=self._trunc_path(self._save_dir),
            anchor="w", font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT)
        self._path_lbl.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(save_row, text="BROWSE", width=92, height=34, corner_radius=17,
                      fg_color="transparent", hover_color=COLOR_HOVER,
                      border_width=1, border_color=COLOR_BORDER_HI,
                      text_color=COLOR_TEXT,
                      font=ctk.CTkFont(size=11, weight="bold"),
                      command=self._browse).grid(row=0, column=1, padx=(10, 0))

        # ── Options ───────────────────────────────────────────────────────────
        self._section_label("Options", row=7)

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=8, column=0, sticky="ew", padx=SIDE_PAD, pady=(0, 0))
        opts.grid_columnconfigure(0, weight=1)

        cap_font   = ctk.CTkFont(size=11)
        label_font = ctk.CTkFont(size=13, weight="bold")

        # Prefer H.264
        self._h264_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Prefer H.264",
                        variable=self._h264_var,
                        font=label_font, text_color=COLOR_TEXT,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOV,
                        border_color=COLOR_BORDER_HI,
                        checkbox_width=18, checkbox_height=18).grid(
            row=0, column=0, sticky="w")
        ctk.CTkLabel(opts,
            text="Forces AVC video for compatibility with older iPhones, Apple TVs, and smart TVs.",
            font=cap_font, text_color=COLOR_TEXT,
            anchor="w", wraplength=CAPTION_WRAP, justify="left").grid(
            row=1, column=0, sticky="w", padx=(28, 0), pady=(2, 12))

        # Clip section
        self._clip_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="Clip section",
                        variable=self._clip_var, command=self._toggle_clip,
                        font=label_font, text_color=COLOR_TEXT,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOV,
                        border_color=COLOR_BORDER_HI,
                        checkbox_width=18, checkbox_height=18).grid(
            row=2, column=0, sticky="w")
        ctk.CTkLabel(opts,
            text="Download only a portion of the video — leave a field blank to run to the start or end.",
            font=cap_font, text_color=COLOR_TEXT,
            anchor="w", wraplength=CAPTION_WRAP, justify="left").grid(
            row=3, column=0, sticky="w", padx=(28, 0), pady=(2, 6))

        # Clip range entries (revealed by the Clip section toggle)
        self._clip_row = ctk.CTkFrame(opts, fg_color="transparent")
        self._clip_row.grid(row=4, column=0, sticky="w", padx=(28, 0), pady=(0, 12))

        ctk.CTkLabel(self._clip_row, text="Start",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, padx=(0, 8))
        self._start_var = ctk.StringVar()
        self._start_entry = ctk.CTkEntry(
            self._clip_row, textvariable=self._start_var,
            placeholder_text="1:23", width=110, height=30, corner_radius=15,
            fg_color=COLOR_INTERACT, border_color=COLOR_INTERACT,
            text_color=COLOR_TEXT, placeholder_text_color=COLOR_TEXT,
            font=ctk.CTkFont(size=12))
        self._start_entry.grid(row=0, column=1, padx=(0, 20))

        ctk.CTkLabel(self._clip_row, text="End",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=2, padx=(0, 8))
        self._end_var = ctk.StringVar()
        self._end_entry = ctk.CTkEntry(
            self._clip_row, textvariable=self._end_var,
            placeholder_text="2:45", width=110, height=30, corner_radius=15,
            fg_color=COLOR_INTERACT, border_color=COLOR_INTERACT,
            text_color=COLOR_TEXT, placeholder_text_color=COLOR_TEXT,
            font=ctk.CTkFont(size=12))
        self._end_entry.grid(row=0, column=3)

        self._clip_row.grid_remove()

        # Cookies
        cookies_row = ctk.CTkFrame(opts, fg_color="transparent")
        cookies_row.grid(row=5, column=0, sticky="w")
        ctk.CTkLabel(cookies_row, text="Cookies",
                     font=label_font, text_color=COLOR_TEXT).grid(
            row=0, column=0, padx=(0, 12))

        self._cookies_var = ctk.StringVar(value="None")
        ctk.CTkOptionMenu(cookies_row, variable=self._cookies_var,
                          values=COOKIE_BROWSERS,
                          width=110, height=28, corner_radius=14,
                          fg_color=COLOR_INTERACT,
                          button_color=COLOR_INTERACT,
                          button_hover_color=COLOR_HOVER,
                          dropdown_fg_color=COLOR_SURFACE,
                          dropdown_hover_color=COLOR_HOVER,
                          text_color=COLOR_TEXT,
                          font=ctk.CTkFont(size=12)).grid(row=0, column=1)

        ctk.CTkLabel(opts,
            text="Use your browser's login to reach private, members-only, or age-restricted videos.",
            font=cap_font, text_color=COLOR_TEXT,
            anchor="w", wraplength=CAPTION_WRAP, justify="left").grid(
            row=6, column=0, sticky="w", padx=(28, 0), pady=(2, 0))

        # ── Bottom "Now Playing" dock ─────────────────────────────────────────
        ctk.CTkFrame(self, fg_color=COLOR_DIVIDER, height=1, corner_radius=0).grid(
            row=11, column=0, sticky="ew")

        dock = ctk.CTkFrame(self, fg_color=COLOR_SURFACE, corner_radius=0, height=DOCK_H)
        dock.grid(row=12, column=0, sticky="ew")
        dock.grid_propagate(False)
        dock.grid_columnconfigure(0, weight=1)

        dock_inner = ctk.CTkFrame(dock, fg_color="transparent")
        dock_inner.grid(row=0, column=0, sticky="nsew", padx=SIDE_PAD, pady=14)
        dock_inner.grid_columnconfigure(0, weight=1)

        self._filename_var = ctk.StringVar(value="Ready to download")
        self._filename_lbl = ctk.CTkLabel(
            dock_inner, textvariable=self._filename_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT, anchor="w", wraplength=WRAP - 80)
        self._filename_lbl.grid(row=0, column=0, sticky="ew")

        self._progress = ctk.CTkProgressBar(
            dock_inner, height=4, corner_radius=2,
            fg_color=COLOR_INTERACT, progress_color=COLOR_ACCENT)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew", pady=(6, 4))

        self._meta_var = ctk.StringVar(value="Paste a link to begin")
        self._meta_lbl = ctk.CTkLabel(
            dock_inner, textvariable=self._meta_var,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT, anchor="w")
        self._meta_lbl.grid(row=2, column=0, sticky="ew")

        self._dl_btn = ctk.CTkButton(
            dock_inner, text="▶", width=48, height=48, corner_radius=24,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOV,
            text_color="#000000",
            command=self._start_download)
        self._dl_btn.grid(row=0, column=1, rowspan=3, sticky="ns", padx=(16, 0))

    def _select_quality(self, key: str) -> None:
        """Update the segmented quality row: highlight the active pill in green."""
        self._quality_var.set(key)
        for k, btn in self._quality_btns.items():
            if k == key:
                btn.configure(fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOV,
                              text_color="#000000")
            else:
                btn.configure(fg_color=COLOR_INTERACT, hover_color=COLOR_HOVER,
                              text_color=COLOR_TEXT)

    def _toggle_clip(self):
        """Show or hide the Start/End entry row when Clip section is toggled."""
        if self._clip_var.get():
            self._clip_row.grid()
        else:
            self._clip_row.grid_remove()
            self._start_var.set("")
            self._end_var.set("")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _trunc_path(path: Path, n: int = 46) -> str:
        """Truncate a filesystem path for the save-to label."""
        s = str(path)
        return s if len(s) <= n else "…" + s[-(n - 1):]

    def _set_status(self, filename: str = "", meta: str = "", error: bool = False):
        """Update both dock status lines. Must be called on the main thread."""
        self._filename_var.set(filename)
        self._meta_var.set(meta)
        if error:
            self._filename_lbl.configure(text_color=COLOR_DANGER)
            self._meta_lbl.configure(text_color=COLOR_DANGER)
        else:
            self._filename_lbl.configure(text_color=COLOR_TEXT)
            self._meta_lbl.configure(text_color=COLOR_TEXT)

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
            self._dl_btn.configure(text="■", state="disabled")
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
            self._dl_btn.configure(text="■", state="disabled")
            self._set_status(filename=self._filename_var.get(), meta="Cancelling…")
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
            text="■", state="normal",
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOV)
        self._progress.set(0)
        self._set_status(filename="Preparing…", meta="Starting download")   # Clear previous filename (S3)

        log.info("Download started — quality=%s cookies=%s h264=%s clip=%s dest=%s",
                 quality_key, cookies_key, h264, clip_range, save_dir)

        self._worker_thread = threading.Thread(
            target=self._worker,
            args=(url, quality_key, save_dir, cookies_key, h264, clip_range),
            daemon=True)
        self._worker_thread.start()

    # ── URL probe (playlist detection + title lookup) ─────────────────────────

    def _probe_info(self, url: str, cookies_key: str) -> dict | None:
        """Extract URL metadata (no download). Used for both playlist detection and
        filename-collision checks. Runs synchronously on the worker thread.
        """
        opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        ffmpeg = _bundled_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        if cookies_key != "None":
            opts["cookiesfrombrowser"] = (cookies_key.lower(),)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

    @staticmethod
    def _unique_outtmpl(info: dict | None, save_dir: Path, is_audio: bool) -> str:
        """Return an outtmpl that won't overwrite an existing file.
        For a single video with a known title, returns a literal ' (N).ext' path
        (with '%' escaped). For playlists or unknown titles, returns the default
        '%(title)s.%(ext)s' template and lets yt-dlp handle naming.
        """
        default = str(save_dir / "%(title)s.%(ext)s")
        if not info or info.get("_type") == "playlist":
            return default
        title = info.get("title")
        if not title:
            return default
        ext = "mp3" if is_audio else "mp4"
        safe = sanitize_filename(title, restricted=False)
        candidate = save_dir / f"{safe}.{ext}"
        n = 1
        while candidate.exists():
            candidate = save_dir / f"{safe} ({n}).{ext}"
            n += 1
        # Escape '%' so yt-dlp does not treat literal title chars as field markers.
        return str(candidate).replace("%", "%%")

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

        # Probe URL info — used for both playlist detection and filename collision check
        info = self._probe_info(url, cookies_key)
        if info and info.get("_type") == "playlist":
            count = len(info.get("entries") or [])
            if count > 1 and not self._ask_playlist(count):
                self.after(0, self._on_cancelled)
                return

        outtmpl = self._unique_outtmpl(info, save_dir, is_audio)

        postprocessors = []
        if is_audio:
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })

        ydl_opts = {
            "format":              fmt,
            "outtmpl":             outtmpl,
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
            self._set_status(filename="Download complete",
                             meta=f"✓  Saved to {self._save_dir}")
        log.info("Download complete — file=%s", saved_name or "(unknown)")
        _notify("Download complete",
                saved_name if saved_name else f"Saved to {self._save_dir}")

    def _on_cancelled(self):
        self._reset()
        self._set_status(filename="Ready to download", meta="Download cancelled.")
        log.info("Download cancelled.")

    def _on_error(self, msg: str):
        self._reset()
        self._set_status(filename="Download failed", meta=msg, error=True)

    def _reset(self):
        self._downloading = False
        self._progress.set(0)   # Return bar to zero on every terminal state (S9)
        self._dl_btn.configure(
            text="▶", state="normal",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOV)


if __name__ == "__main__":
    # Pinned to dark — the Spotify-inspired palette only works in dark mode (DEC-022).
    ctk.set_appearance_mode("dark")      # Inside __main__ guard — no side effect on import (D9)
    _setup_logging()
    App().mainloop()
