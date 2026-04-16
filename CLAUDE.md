# SaveThisVideo

macOS GUI wrapper around yt-dlp. Single-window app: paste URL, pick quality, download.
Version: **1.2** — header displays `APP_TITLE = "SAVE THIS VIDEO!"`

## Stack
- Python 3.10+
- customtkinter 5.2.2 — modern Tk UI (system appearance, dark/light mode)
- yt-dlp 2026.3.17 — download engine
- static-ffmpeg 3.0 — bundled static ffmpeg binary for the distributed `.app`
- ffmpeg (brew) — used in dev/run mode when not packaged

## Project Location
`/Users/goralski/Desktop/CLAUDE_PROJECTS/SaveThisVideo/`

## Commands
```bash
./setup.sh       # First-time setup (creates venv, installs deps, checks ffmpeg)
./run.sh         # Launch the app (dev mode)
./build.sh       # Package as signed, notarized dist/SaveThisVideo.app
```

## Architecture
Single file: `app.py`. One class: `App(ctk.CTk)`.

- UI runs on the main thread (tkinter requirement)
- Downloads run on a daemon `threading.Thread`
- All UI state (quality, save_dir) is captured on the main thread **before** the worker starts — the worker receives them as arguments and never accesses tkinter state directly
- All UI updates from the worker go through `self.after(0, fn)` to marshal back to the main thread
- Cancel: sets `threading.Event`; `_hook` raises `_Cancelled` sentinel exception; worker catches it and routes to `_on_cancelled`
- Window close: `WM_DELETE_WINDOW` → `_on_close()` → sets cancel → polls via `_wait_and_close()` (100ms × max 30 = 3 s) → `destroy()`

## UI Layout (Spotify-inspired dark — DEC-022, DEC-023)
```
┌──────────────────────────────────────────────────────────┐
│  SaveThisVideo                                   v1.0.0  │  Header strip
│                                                          │
│  PASTE A LINK                                            │  Uppercase muted section labels
│  [⌕ Paste a link ──────────────────────────] [ PASTE  ]  │  Pill entry + outlined pill
│                                                          │
│  QUALITY                                                 │
│  [BEST][4K][1080p][720p][480p][360p][AUDIO]              │  Segmented pills — active = green
│                                                          │
│  SAVE TO                                                 │
│  ~/Desktop                                   [ BROWSE ]  │
│                                                          │
│  OPTIONS                                                 │
│  ☐ Prefer H.264                                          │
│     Forces AVC video for compatibility with older …      │  Stacked option rows —
│  ☐ Clip section                                          │  each control gets a
│     Download only a portion — leave blank to run to …    │  one-line description
│     Start [1:23]   End [2:45]                            │  (revealed by Clip toggle)
│  Cookies [None ▾]                                        │
│     Use your browser's login to reach private, …         │
│                                                          │
├──────────────────────────────────────────────────────────┤  #272727 hairline divider
│  filename.mp4                                    ┌───┐   │  Dock (#181818 surface)
│  ▓▓▓▓▓░░░░░░ 45 % • 2.1 MB/s • ETA 0:23          │ ▶ │   │  48×48 circular CTA
│                                                  └───┘   │
└──────────────────────────────────────────────────────────┘
```

Window: 640×660, fixed size. Layout constants at module top: `WINDOW_W`, `WINDOW_H`, `SIDE_PAD`, `CTK_LABEL_PAD`, `WRAP`, `CAPTION_WRAP`, `DOCK_H`. Visual tokens in a dedicated block: `COLOR_BG` `#121212`, `COLOR_SURFACE` `#181818`, `COLOR_INTERACT` `#575757`, `COLOR_HOVER` `#616161`, `COLOR_ACCENT` `#539df5` (blue), `COLOR_ACCENT_HOV` `#3d8ae0`, `COLOR_DANGER` `#f3727f`, `COLOR_DANGER_HOV` `#e26570`, `COLOR_TEXT` `#ffffff`, `COLOR_DIVIDER` `#272727`, `COLOR_BORDER_HI` `#7c7c7c`. All text is pure white — hierarchy comes from weight/size contrast, not color. Inactive pills at `#575757` are deliberately much lighter than the page background for clear separation.

### Circle CTA states (dock_btn)
| State       | Text | fg_color          | hover_color         | state      |
|-------------|------|-------------------|---------------------|------------|
| Idle        | ▶    | `COLOR_ACCENT`    | `COLOR_ACCENT_HOV`  | normal     |
| Downloading | ■    | `COLOR_DANGER`    | `COLOR_DANGER_HOV`  | normal     |
| Cancelling  | ■    | (prev)            | (prev)              | disabled   |
| Closing     | ■    | (prev)            | (prev)              | disabled   |

### Segmented quality pill row
`self._quality_btns: dict[str, CTkButton]` — one button per `QUALITY_OPTIONS` key. `_select_quality(key)` updates `self._quality_var` and recolors all seven buttons (active = green fill + black text, inactive = `#1f1f1f` fill + silver text). Short labels in `QUALITY_SHORT` map.

## Quality Options

| Label             | yt-dlp format string                                      |
|-------------------|-----------------------------------------------------------|
| Best Available    | `bestvideo+bestaudio/best`                                |
| 4K (2160p)        | `bestvideo[height<=2160]+bestaudio/best[height<=2160]`    |
| 1080p             | `bestvideo[height<=1080]+bestaudio/best[height<=1080]`    |
| 720p              | `bestvideo[height<=720]+bestaudio/best[height<=720]`      |
| 480p              | `bestvideo[height<=480]+bestaudio/best[height<=480]`      |
| 360p              | `bestvideo[height<=360]+bestaudio/best[height<=360]`      |
| Audio Only (MP3)  | `bestaudio/best` + FFmpegExtractAudio @ 192kbps           |

Video formats merged to mp4. Audio-only skips the merge step.

When **Prefer H.264** is checked, a parallel `QUALITY_OPTIONS_H264` map is used. Each entry has the form `bestvideo[vcodec~=avc][height<=N]+bestaudio/bestvideo[height<=N]+bestaudio/best[height<=N]` — H.264 first, falls back to any codec at the same height, then to a single best file. Audio-only mode is not affected by the checkbox.

## Optional Features (all opt-in)

| Control              | Behavior                                                                 |
|----------------------|--------------------------------------------------------------------------|
| Cookies from browser | yt-dlp `cookiesfrombrowser=(browser.lower(),)` on probe + download       |
| Prefer H.264         | Swap `QUALITY_OPTIONS` → `QUALITY_OPTIONS_H264` (no-op for audio)        |
| Clip section         | `download_ranges=download_range_func(None, [(start, end)])` + `force_keyframes_at_cuts=True` |

### Clip time parsing
`_parse_time()` accepts `SS`, `MM:SS`, or `HH:MM:SS` (decimals allowed). Empty → `None`. Validation in `_start_download`: empty+empty → error; End ≤ Start → error; malformed → error quoting the bad token.

### Filename collision handling
`_unique_outtmpl()` runs after `_probe_info()` and before the main download. For single videos, it sanitizes the title (`yt_dlp.utils.sanitize_filename`), adds `.mp4` or `.mp3`, and walks ` (1)`, ` (2)`, … until a free path exists in `save_dir`. The literal path is then used as `outtmpl` with `%` → `%%` escaping. Playlists keep the default `%(title)s.%(ext)s` template.

### macOS notification
`_notify(title, message)` shells out to `osascript -e 'display notification …'` with a 3-second timeout. Called from `_on_done()` only. All exceptions are swallowed and logged at debug level — notification failure can never interrupt the app.

## Key Implementation Details

### Thread Safety (D2)
`quality_key` and `save_dir` are captured on the main thread in `_start_download()` before the daemon thread starts. They are passed as function arguments. The worker **never** calls `self._quality_var.get()` or reads `self._save_dir`.

### URL Validation (D4)
`_validate_url()` rejects anything that doesn't match `^https?://` before dispatch. Friendly error shown inline.

### Error Messages (S1)
`_friendly_error()` maps 12 known yt-dlp error substrings to plain-English copy via `_ERROR_MAP`. The `[extractor] id:` prefix is stripped from unmatched errors via regex.

### Playlist Detection (D5, D7 fix)
`_probe_info()` runs `extract_flat` (with `socket_timeout=15`) in the worker thread before downloading. If count > 1, `_ask_playlist()` shows a native `tkinter.messagebox.askyesno` dialog. Worker polls `_playlist_done` in a 0.5s loop checking `_cancel.is_set()` — window close sets both `_cancel` and `_playlist_done` to prevent deadlock.

### Disk Space (S8)
`shutil.disk_usage(save_dir).free` checked before download starts. Blocked with friendly message if < 500 MB (`DISK_WARN_BYTES`). `OSError` silently swallowed (unmounted/inaccessible path).

### Completion Message (S2, D1 fix)
The progress hook (closure in `_worker`) captures `d["filename"]` into a thread-local `saved_path[0]`. `_on_done(saved_path, save_dir)` receives both as arguments (no shared state). Shows filename on line 1 and the **captured** save directory on line 2 (S5 fix).

### Logging (S6)
`_setup_logging()` configures `RotatingFileHandler` at `~/Library/Logs/SaveThisVideo/app.log` (2 MB, 3 backups). Called inside `__main__` guard only. Full URLs are **not** logged (privacy).

## ffmpeg Handling
- **Dev mode** (`./run.sh`): `_bundled_ffmpeg()` returns `None` → uses system ffmpeg (brew)
- **Packaged** (`.app`): detects `sys.frozen` → returns `sys._MEIPASS/bin/ffmpeg`

## Distribution (Build)
`build.sh` produces an **unsigned** `.app` bundle (D10 fix — no codesign/notarize steps):
1. `make_icon.py` → regenerates `icon.icns` from `app_icon.png`
2. `static-ffmpeg` → fetches the static ffmpeg binary
3. PyInstaller `--windowed --onedir` with `customtkinter` + `yt_dlp` + `curl_cffi` collected, ffmpeg + `app_icon.png` bundled, `--icon=icon.icns`
4. `ditto -c -k --keepParent` → `dist/SaveThisVideo.zip`

Recipients right-click → Open the first time to bypass Gatekeeper.
For signed + notarized distribution, add codesign/notarytool steps to `build.sh` or create a separate `build_signed.sh`.

## Repo Hygiene
`.gitignore` excludes: `.venv/`, `build/`, `dist/`, `*.spec`, `__pycache__/`, `.DS_Store`  
The `.spec` file is **not** committed — it is regenerated by `build.sh` on every run and contains machine-specific absolute paths.

## Dependencies
Pinned in `requirements.txt`. To upgrade yt-dlp when a site breaks:
```bash
.venv/bin/pip install --upgrade yt-dlp
# test, then update the pin in requirements.txt
```

## NOTES
See `NOTES/` for project history:
- `decisions.md` — DEC-001 through DEC-025
- `fixes.md` — FIX-001 through FIX-032
- `errors.md` — ERR-001 through ERR-005

## App Icon
- **Source**: `app_icon.png` (user-supplied; 1073×1091, padded to square at build time)
- **Runtime window icon**: `App._set_window_icon()` calls `iconphoto(True, tk.PhotoImage(file=...))`. Best-effort, never raises. On macOS this affects titlebar/minimized icon only — the live Dock icon during dev still shows Python.
- **Bundle icon**: `make_icon.py` loads `app_icon.png`, pads to square, resamples at all 10 required sizes, and runs `iconutil` to produce `icon.icns`. `build.sh` calls `make_icon.py` then passes `--icon=icon.icns` to PyInstaller. `app_icon.png` itself is bundled via `--add-data="app_icon.png:."` so the runtime iconphoto works in the packaged `.app` too.
- **Resolver**: `_resource_path(name)` returns `sys._MEIPASS/name` when frozen, `Path(__file__).parent/name` otherwise.

## Design System Reference
`DESIGN.md` documents the Spotify-inspired dark design vocabulary (colors, typography, pill geometry, elevation, do/don'ts). The CTk implementation is a faithful-as-possible translation within tkinter's capabilities — CircularSp fonts, CSS shadows, and uppercase letter-spacing are not available and are accepted as lost. See DEC-022 for the full translation table.

## CRITICAL Workflow Rule
NEVER implement code changes before receiving explicit user approval. Generate plan → present → wait → implement.
