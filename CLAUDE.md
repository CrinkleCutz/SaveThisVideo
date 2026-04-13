# SaveThisVideo

macOS GUI wrapper around yt-dlp. Single-window app: paste URL, pick quality, download.
Version: **1.0.0**

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

## UI Layout
```
[Video URL label]
[URL entry field ──────────────────────────────] [Paste]
[Quality ▼]  [Save to: ~/Desktop ────────────] [Browse…]
[Cookies from browser: ▼]   [☐ Prefer H.264]
  "Use your browser's login to reach private, members-only, or age-restricted videos."
[☐ Clip section]   [Start  e.g. 1:23]   [End  e.g. 2:45]    (entries hidden until toggle is on)
  "Download only a portion of the video — leave a field blank to run to the start or end."
[Download / Cancel button (full width, 44px)]
[Progress bar]
[Filename label — wraps at WRAP=532px]
[Speed / ETA / state — single line]
```

Window: 580×500, fixed size. Layout constants defined at module top: `WINDOW_W`, `SIDE_PAD`, `CTK_LABEL_PAD`, `WRAP`.

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

### macOS notification
`_notify(title, message)` shells out to `osascript -e 'display notification …'` with a 3-second timeout. Called from `_on_done()` only. All exceptions are swallowed and logged at debug level — notification failure can never interrupt the app.

## Key Implementation Details

### Thread Safety (D2)
`quality_key` and `save_dir` are captured on the main thread in `_start_download()` before the daemon thread starts. They are passed as function arguments. The worker **never** calls `self._quality_var.get()` or reads `self._save_dir`.

### URL Validation (D4)
`_validate_url()` rejects anything that doesn't match `^https?://` before dispatch. Friendly error shown inline.

### Error Messages (S1)
`_friendly_error()` maps 12 known yt-dlp error substrings to plain-English copy via `_ERROR_MAP`. The `[extractor] id:` prefix is stripped from unmatched errors via regex.

### Playlist Detection (D5)
`_probe_playlist()` runs `extract_flat` in the worker thread before downloading. If count > 1, `_ask_playlist()` shows a native `tkinter.messagebox.askyesno` dialog. The worker blocks on `threading.Event.wait(timeout=120)` until the user responds.

### Disk Space (S8)
`shutil.disk_usage(save_dir).free` checked before download starts. Blocked with friendly message if < 500 MB (`DISK_WARN_BYTES`). `OSError` silently swallowed (unmounted/inaccessible path).

### Completion Message (S2)
`_hook` captures `d["filename"]` when `status == "finished"` into `self._last_saved_path`. `_on_done()` shows the filename on line 1 and save directory on line 2.

### Logging (S6)
`_setup_logging()` configures `RotatingFileHandler` at `~/Library/Logs/SaveThisVideo/app.log` (2 MB, 3 backups). Called inside `__main__` guard only. Full URLs are **not** logged (privacy).

## ffmpeg Handling
- **Dev mode** (`./run.sh`): `_bundled_ffmpeg()` returns `None` → uses system ffmpeg (brew)
- **Packaged** (`.app`): detects `sys.frozen` → returns `sys._MEIPASS/bin/ffmpeg`

## Distribution (Build)
`build.sh` performs the full pipeline:
1. PyInstaller `--windowed --onedir` with `customtkinter` + `yt_dlp` collected + ffmpeg binary bundled
2. `codesign --deep --force --options runtime --sign "Developer ID Application: ..."`
3. `xcrun notarytool submit --keychain-profile ... --wait`
4. `xcrun stapler staple` → `spctl -a -v` verification
5. `ditto -c -k --keepParent` → distribution zip

**Developer setup required before first build:**
- Apple Developer ID Application certificate in keychain
- `xcrun notarytool store-credentials "AC_PASSWORD" --apple-id ... --team-id ...`
- Fill in `DEVELOPER_ID` and `NOTARYTOOL_KEYCHAIN_PROFILE` at top of `build.sh`

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
- `decisions.md` — DEC-001 through DEC-020
- `fixes.md` — FIX-001 through FIX-024
- `errors.md` — ERR-001 through ERR-005

## CRITICAL Workflow Rule
NEVER implement code changes before receiving explicit user approval. Generate plan → present → wait → implement.
