# Errors

## ERR-001 — tkinter thread-safety crashes
**Date**: 2026-04-12  
**Symptom**: Intermittent crash / "main thread is not in main loop" when updating UI from download thread.  
**Root cause**: tkinter requires all widget calls on the main thread.  
**Resolution**: All UI updates dispatched via `self.after(0, fn)`. Worker thread never touches widgets directly.  
**Status**: Resolved (by design).

## ERR-002 — yt-dlp raises generic `Exception` on cancel
**Date**: 2026-04-12  
**Symptom**: `_on_error` was firing with "cancelled" text after a user cancel instead of `_on_cancelled`.  
**Root cause**: The hook previously raised `Exception("cancelled")`, caught by the same `except Exception` block as real errors.  
**Resolution**: Replaced with a dedicated `_Cancelled` exception class. Worker catches `_Cancelled` separately and always routes to `_on_cancelled`, regardless of the yt-dlp exception path.  
**File**: `app.py:52, _worker except blocks`  
**Status**: Resolved.

## ERR-003 — Module-level Tk initialisation crash on import
**Date**: 2026-04-12  
**Symptom**: `_tkinter.TclError: no display name and no $DISPLAY environment variable` when importing app.py in a headless environment (CI, test runner).  
**Root cause**: `ctk.set_appearance_mode()` called at module level, triggering Tk initialisation on import.  
**Resolution**: Moved inside `if __name__ == "__main__"` guard. Module is now safely importable without a display.  
**File**: `app.py:306–309`  
**Status**: Resolved.

## ERR-004 — Playlist download fills disk without user consent
**Date**: 2026-04-12  
**Symptom**: Pasting a YouTube playlist URL silently began downloading all videos in the playlist.  
**Root cause**: No playlist detection or confirmation step existed before calling `ydl.download()`.  
**Resolution**: `_probe_playlist()` runs `extract_flat` before download. Count > 1 triggers `_ask_playlist()` confirmation dialog. User must explicitly confirm.  
**File**: `app.py:212–248`  
**Status**: Resolved.

## ERR-005 — App hangs on exit mid-download
**Date**: 2026-04-12  
**Symptom**: Clicking the red close button mid-download caused the window to disappear but the process to hang.  
**Root cause**: No `WM_DELETE_WINDOW` handler; daemon thread kept running and Python waited for it on exit.  
**Resolution**: `_on_close()` sets cancel event and polls via `_wait_and_close()` (100ms × max 30 = 3 s timeout) until the worker exits, then destroys the window.  
**File**: `app.py:148–164`  
**Status**: Resolved.
