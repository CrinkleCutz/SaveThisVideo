# Decisions

## DEC-001 — Single-file architecture (app.py, one class)
**Date**: 2026-04-12  
**Decision**: All UI and download logic lives in `app.py` as a single `App(ctk.CTk)` class.  
**Why**: The app is small enough that splitting files adds indirection without benefit.

## DEC-002 — Background thread + `self.after(0, fn)` for thread safety
**Date**: 2026-04-12  
**Decision**: Downloads run on a daemon `threading.Thread`. All UI mutations go through `self.after(0, fn)` to marshal back to the main thread.  
**Why**: tkinter is not thread-safe. Direct UI calls from the worker thread cause crashes or silent corruption.

## DEC-003 — Cancel via `_Cancelled` sentinel exception raised in hook
**Date**: 2026-04-12 (updated from string-based approach)  
**Decision**: `_cancel` is a `threading.Event`. The `_hook` callback checks it and raises `_Cancelled()` (a dedicated exception class) if set. The worker catches `_Cancelled` separately from `Exception`.  
**Why**: Using a dedicated exception class instead of `Exception("cancelled")` makes the cancel/error distinction explicit and unambiguous — no string matching required.

## DEC-004 — Two-line status area (filename + meta)
**Date**: 2026-04-12  
**Decision**: Status area is split into two dedicated labels: `_filename_lbl` (wraps via `wraplength=WRAP`) and `_meta_lbl` (single short line for speed/ETA/state).  
**Why**: Long filenames stomped on speed/ETA text when combined. Separating them keeps the layout stable.  
**Constants**: `WINDOW_W=580`, `SIDE_PAD=20`, `CTK_LABEL_PAD=8`, `WRAP=532` — derived explicitly.

## DEC-005 — `static-ffmpeg` for PyInstaller bundling
**Date**: 2026-04-12  
**Decision**: The `static-ffmpeg` pip package provides a pre-built static ffmpeg binary bundled into the `.app`. Dev mode falls back to system ffmpeg (brew).  
**Why**: Shipping a standalone `.app` that requires brew + ffmpeg installed is a bad UX.  
**Implementation**: `_bundled_ffmpeg()` detects `sys.frozen` and returns `sys._MEIPASS/bin/ffmpeg`.

## DEC-006 — Merge output format forced to mp4
**Date**: 2026-04-12  
**Decision**: `merge_output_format` is `"mp4"` for all video qualities, `None` for audio-only.  
**Why**: yt-dlp's default varies by source (often mkv). Forcing mp4 ensures files open in QuickTime and iOS predictably.

## DEC-007 — Audio Only at 192kbps MP3
**Date**: 2026-04-12  
**Decision**: Audio Only mode uses `FFmpegExtractAudio` postprocessor with `preferredcodec="mp3"` and `preferredquality="192"`.  
**Why**: 192kbps is transparent for most listeners and universally compatible.

## DEC-008 — Default save location is Desktop
**Date**: 2026-04-12  
**Decision**: `_save_dir` initializes to `Path.home() / "Desktop"`.  
**Why**: Most users want downloaded videos immediately visible. Desktop is the lowest-friction default.

## DEC-009 — Path truncation at 46 chars with leading ellipsis
**Date**: 2026-04-12  
**Decision**: `_trunc_path(path, n=46)` truncates long paths to "…" + last 45 chars.  
**Why**: The save-to label has limited horizontal space. Showing the tail of the path is more useful than the head.

## DEC-010 — PyInstaller `--windowed --onedir` build
**Date**: 2026-04-12  
**Decision**: App is packaged as `--windowed` (no terminal) and `--onedir` (folder, not single executable).  
**Why**: `--onedir` starts faster than `--onefile` (no temp extraction on launch).

## DEC-011 — Cancel button uses red colour during download
**Date**: 2026-04-12  
**Decision**: While downloading, the Download button changes text to "Cancel" and turns red. On cancel, it changes to "Cancelling…" and is disabled until the worker exits.  
**Why**: Clear visual feedback prevents double-clicks and communicates state unambiguously.

## DEC-012 — Code signing + notarization pipeline in build.sh (D1 resolution)
**Date**: 2026-04-12  
**Decision**: `build.sh` now includes `codesign --deep --force --options runtime`, `notarytool submit --wait`, `stapler staple`, and `spctl -a -v` verification steps after PyInstaller. Distribution zip uses `ditto` (preserves macOS metadata) instead of plain `zip`.  
**Why**: All modern Macs run Gatekeeper. An unsigned/unnotarized app is hard-blocked on double-click. Apple distribution requires both signing and notarization.  
**Developer setup required**: Apple Developer ID Application certificate in keychain; `notarytool store-credentials` configured with App Store Connect API key.

## DEC-013 — Playlist detection via extract_flat probe before download
**Date**: 2026-04-12  
**Decision**: Before downloading, `_probe_playlist()` runs `extract_flat` to check if the URL resolves to a playlist. If > 1 entry, `_ask_playlist()` shows a native confirmation dialog via `tkinter.messagebox.askyesno`.  
**Why**: Silent playlist downloads can fill a user's disk without consent. Explicit confirmation is required.  
**Implementation**: Worker thread blocks on `threading.Event.wait(timeout=120)` while the dialog runs on the main thread via `self.after(0, _show)`.

## DEC-014 — Rotating file logger at ~/Library/Logs/SaveThisVideo/app.log
**Date**: 2026-04-12
**Decision**: `_setup_logging()` configures a `RotatingFileHandler` (2 MB max, 3 backups). Called inside `__main__` guard only. Module-level `log = logging.getLogger("savethisvideo")` is harmless on import (no handlers attached until startup).
**Why**: Production apps need diagnostic logs. Without them, support tickets cannot be investigated.
**Privacy note**: Full URLs are not logged — only the host portion and quality selection.

## DEC-015 — `*.spec` excluded from repo via .gitignore
**Date**: 2026-04-12  
**Decision**: `SaveThisVideo.spec` removed from tracked files. `.gitignore` added covering `.venv/`, `build/`, `dist/`, `*.spec`, `__pycache__/`, `.DS_Store`.  
**Why**: The spec is regenerated by `build.sh` on every build and contains machine-specific absolute paths. Committing it is misleading and non-portable.

## DEC-016 — Dependencies pinned in requirements.txt
**Date**: 2026-04-12  
**Decision**: All three dependencies pinned to exact tested versions: `yt-dlp==2026.3.17`, `customtkinter==5.2.2`, `static-ffmpeg==3.0`.  
**Why**: yt-dlp releases breaking changes regularly as platforms change their APIs. Unpinned = non-reproducible builds.  
**Maintenance**: Run `.venv/bin/pip install --upgrade yt-dlp` when a site breaks, test, then update the pin.

## DEC-017 — Cookies from browser dropdown
**Date**: 2026-04-13  
**Decision**: New `Cookies from browser` option menu on the cookie row (`None`, `Safari`, `Chrome`, `Firefox`). When not `None`, yt-dlp's `cookiesfrombrowser` option is set to `(browser_name.lower(),)` on both the playlist probe and the main download.  
**Why**: Sites that gate content behind login (age-restricted, paywalled, region-locked) fail without cookies. Browser cookies is the lowest-friction way to authenticate — no file wrangling.  
**Error handling**: Friendly error messages added for "Unable to load cookies" and general "cookies" substrings, directing the user to close the browser or set Cookies to None.

## DEC-018 — macOS completion notification via osascript
**Date**: 2026-04-13  
**Decision**: `_on_done()` calls `_notify(title, message)` which shells out to `osascript -e 'display notification ... with title ...'`. Runs with a 3-second timeout and swallows all exceptions.  
**Why**: Users often start a long download and switch away. A Notification Center banner surfaces completion without needing to bring the app forward. Using `osascript` avoids adding a dependency (no `pyobjc`).  
**Permissions**: The first notification triggers macOS's permission prompt for "Script Editor" / the bundled app; subsequent notifications are silent if denied.  
**Safety**: Notification failure never interrupts the download — all exceptions logged at `debug` level and swallowed.

## DEC-019 — "Prefer H.264" checkbox for broader device compatibility
**Date**: 2026-04-13  
**Decision**: New checkbox in the cookie/options row. When checked, `QUALITY_OPTIONS_H264` (parallel format-string map) is used instead of the default `QUALITY_OPTIONS`. Each H.264 format string has a three-tier fallback: `bestvideo[vcodec~=avc]+bestaudio / bestvideo+bestaudio / best`. Audio-only mode is unaffected.  
**Why**: VP9 and AV1 (default on YouTube for higher resolutions) don't play natively on older iPhones, iPads, Apple TVs, and many TV OSs. H.264/AVC is universally compatible but may fall back to a lower resolution when AVC isn't available at the requested height.  
**Tradeoff**: Users may get a lower-resolution file than requested if AVC isn't available at the target height. The fallback chain ensures the download never fails purely because AVC is missing.

## DEC-020 — Clip section: Start/End time fields with download_ranges
**Date**: 2026-04-13  
**Decision**: New "Clip section" checkbox reveals two `CTkEntry` fields (`Start`, `End`). Both are optional — at least one must be non-empty when the toggle is on. Times parse `SS`, `MM:SS`, or `HH:MM:SS`. Maps to yt-dlp's `download_ranges=download_range_func(None, [(start, end)])` plus `force_keyframes_at_cuts=True`.  
**Why**: Users often want a specific segment (a clip from a long video, a single scene). Downloading the full video then trimming locally is slow and wastes disk.  
**Validation**: Empty + empty → inline error. End ≤ Start → inline error. Invalid format → inline error quoting the offending token.  
**Implementation note**: `_toggle_clip()` clears the Start/End fields when the toggle is turned off, so stale values don't leak into the next download.

## DEC-021 — Avoid overwriting existing files by appending " (N)" suffix
**Date**: 2026-04-13  
**Decision**: Before the main download, the worker probes the URL's info dict (reusing the playlist-detection call — no extra network round-trip). For single videos, `_unique_outtmpl` computes `<sanitized-title>.<mp4|mp3>` via `yt_dlp.utils.sanitize_filename`, walks ` (1)`, ` (2)`, … until a free slot is found, and passes that literal path as `outtmpl` (with `%` → `%%` to defuse yt-dlp's template syntax).  
**Why**: Re-downloading the same video would silently overwrite the previous copy. Users expect macOS Finder–style behavior where duplicates get a numbered suffix instead.  
**Scope**: Only single-video downloads are deduped. Playlists keep the default `%(title)s.%(ext)s` template — per-entry dedup is complex and playlist downloads rarely overlap across sessions.  
**Refactor**: `_probe_playlist` (returned just the count) replaced with `_probe_info` (returns the full info dict) since both features need the same probe result.
