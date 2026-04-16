#!/usr/bin/env python3
"""Generate the SaveThisVideo v1.2 Code Review PDF (DEC-025).

Uses the standard dark-themed template from:
    ~/.claude/templates/code_review_pdf_template.py
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/.claude/templates"))
from code_review_pdf_template import (
    canvas, letter, W, H, MARGIN, CONTENT_W, BG_DARK, BG_CARD, BG_CARD_LIGHT,
    TEXT_WHITE, TEXT_GRAY, TEXT_DIM, ACCENT_PINK, ACCENT_FILE, BORDER_SUBTLE,
    BADGE_CRITICAL, BADGE_HIGH, BADGE_MEDIUM, BADGE_LOW, BADGE_INFO,
    FONT_REGULAR, FONT_BOLD, FONT_MONO,
    HexColor, draw_bg, draw_gradient_line, draw_badge, draw_stat_boxes,
    draw_severity_bar, draw_section_header, draw_finding_bullet,
    draw_context_box, draw_item_card, draw_suggestion_card, draw_footer,
    draw_conclusion_box, draw_checklist, draw_risk_box, draw_step_card,
    draw_files_affected, build_cover_page, wrap_text,
)

OUTPUT = os.path.join(os.path.dirname(__file__), "SaveThisVideo_v1.2_Code_Review.pdf")
DOC_TITLE = "SaveThisVideo v1.2 Code Review"
DOC_ID = "DEC-025"
TOTAL_PAGES = 7

# ── DATA ─────────────────────────────────────────────────────────────────────

DEMANDS = [
    {
        "id": 1, "severity": "HIGH",
        "title": "_last_saved_path cross-thread write without sync",
        "desc": "In _hook() (worker thread), self._last_saved_path is assigned. In _on_done() (main thread via self.after()), it is read. Latent data race; becomes a real bug on free-threaded Python (PEP 703, 3.13+).",
        "fix": "Capture the path in the after() call: self.after(0, self._on_done, d.get('filename', '')).",
        "files": "app.py  _hook(), _on_done()",
    },
    {
        "id": 2, "severity": "HIGH",
        "title": "Partial files not cleaned up on cancel/error",
        "desc": "yt-dlp leaves .part files, temp merge files, or incomplete .mp4 files on cancel or error. Neither _on_cancelled nor _on_error attempts cleanup. Desktop accumulates junk over time.",
        "fix": "In _worker exception handlers, glob for and delete .part files matching the output template.",
        "files": "app.py  _worker() except blocks",
    },
    {
        "id": 3, "severity": "MEDIUM",
        "title": "_unique_outtmpl TOCTOU race condition",
        "desc": "candidate.exists() check and yt-dlp file creation are not atomic. Between check and write, another process or concurrent download could claim the filename.",
        "fix": "Add 'nooverwrites': True to ydl_opts as a safety net. Document the inherent TOCTOU limitation.",
        "files": "app.py  _unique_outtmpl()",
    },
    {
        "id": 4, "severity": "HIGH",
        "title": "Probe failure falls back to overwrite-unsafe template",
        "desc": "If _probe_info() returns None (network error), _unique_outtmpl() uses %(title)s.%(ext)s with no collision avoidance. Second download of same video silently overwrites first file.",
        "fix": "Add 'nooverwrites': True to ydl_opts unconditionally.",
        "files": "app.py  _probe_info() -> _unique_outtmpl()",
    },
    {
        "id": 5, "severity": "MEDIUM",
        "title": "osascript notification incomplete escaping",
        "desc": "esc() only handles backslash and double-quote. Video titles with newlines, tabs, curly quotes, or special Unicode break AppleScript parsing. Potential injection vector.",
        "fix": "Pipe AppleScript via stdin instead of -e, or sanitize to ASCII-safe chars before notification.",
        "files": "app.py  _notify()",
    },
    {
        "id": 6, "severity": "HIGH",
        "title": "No timeout or cancel check during _probe_info",
        "desc": "extract_info() blocks indefinitely on slow/hung DNS. User sees 'Preparing...' with no cancel path -- _cancel.set() is never checked. User is stuck until network times out.",
        "fix": "Add 'socket_timeout': 15 to probe opts. Check _cancel.is_set() after probe returns.",
        "files": "app.py  _probe_info()",
    },
    {
        "id": 7, "severity": "HIGH",
        "title": "_ask_playlist deadlock on window close during dialog",
        "desc": "If user closes the window while the playlist messagebox is showing, _on_close() sets cancel and polls _wait_and_close(). Worker is blocked on done.wait(120s). Window destroy before dialog callback causes TclError or 2-minute hang.",
        "fix": "Have _on_close also set the done event. Use short-timeout loop checking _cancel.is_set().",
        "files": "app.py  _ask_playlist(), _on_close()",
    },
    {
        "id": 8, "severity": "HIGH",
        "title": "Stale _tick callbacks overwrite completion message",
        "desc": "Multiple self.after(0, _tick, ...) calls queue during download. When finished, self.after(0, _on_done) queues too. Previously-queued _tick may execute AFTER _on_done, overwriting 'Download complete' with stale progress.",
        "fix": "Guard _tick: if not self._downloading: return. Trailing ticks become no-ops after _reset().",
        "files": "app.py  _tick(), _on_done()",
    },
    {
        "id": 9, "severity": "MEDIUM",
        "title": "_hook ignores status == 'error' from yt-dlp",
        "desc": "yt-dlp progress hooks can fire status='error' for DASH/HLS fragment failures without raising. Current _hook only handles 'downloading' and 'finished'. Progress bar freezes on unhandled error.",
        "fix": "Add elif status == 'error': branch to update UI with error indication.",
        "files": "app.py  _hook()",
    },
    {
        "id": 10, "severity": "MEDIUM",
        "title": "build.sh and CLAUDE.md contradict on code signing",
        "desc": "build.sh says 'unsigned macOS .app' and references non-existent build_signed.sh. CLAUDE.md documents codesign + notarytool steps as if they exist. Contradictory documentation.",
        "fix": "Either create build_signed.sh or update CLAUDE.md to describe the unsigned build accurately.",
        "files": "build.sh, CLAUDE.md",
    },
]

SUGGESTIONS = [
    {"id": 1, "title": "_parse_time accepts nonsensical values",
     "desc": "'99:99' parses to 6039s without complaint. Validate minute/second components are in [0, 60)."},
    {"id": 2, "title": "No input length limit on URL entry",
     "desc": "Malicious clipboard could paste megabytes. Truncate in _paste() to ~2048 chars."},
    {"id": 3, "title": "Clipboard paste doesn't auto-trigger download",
     "desc": "For a 'paste and go' app, auto-start or flash the download button after pasting a valid URL."},
    {"id": 4, "title": "Controls not disabled during download",
     "desc": "Quality pills, cookies, clip entries remain active mid-download. Misleading -- user may think changes affect the active download."},
    {"id": 5, "title": "_on_done shows current save_dir, not captured one",
     "desc": "If user browses to new directory mid-download, completion message shows wrong path."},
    {"id": 6, "title": "Infinite loop risk in _unique_outtmpl",
     "desc": "while candidate.exists() has no upper bound. FUSE mount where exists() always returns True loops forever. Cap at n > 9999."},
    {"id": 7, "title": "curl_cffi in requirements but never imported",
     "desc": "Optional yt-dlp dependency. --collect-all curl_cffi adds significant bundle size. Document or remove."},
    {"id": 8, "title": "static-ffmpeg only needed at build time",
     "desc": "Used only in build.sh. Move to requirements-build.txt or keep as build.sh-only install."},
    {"id": 9, "title": "Stale 'Video Downloader.spec' artifact",
     "desc": "Leftover from earlier project name. Not referenced anywhere. Delete it."},
    {"id": 10, "title": "No --restrict-filenames for cross-platform paths",
     "desc": "Unicode filenames may fail on SMB shares or exFAT drives. Consider a 'Restrict filenames' option."},
    {"id": 11, "title": "_browse doesn't validate writable directory",
     "desc": "User can browse to a read-only directory. Download fails with opaque yt-dlp error instead of friendly message."},
    {"id": 12, "title": "_wait_and_close force-destroys after 3s",
     "desc": "If worker is merging a large file, force-destroy leaves partial files. Log a warning on force-destroy with active worker."},
    {"id": 13, "title": "_probe_info swallows all exceptions silently",
     "desc": "except Exception: return None gives zero feedback. Log at warning level for diagnostics."},
    {"id": 14, "title": "Missing __all__ or module-level encapsulation",
     "desc": "All constants and functions at module scope with no __all__. Minor for single-file, but matters for testability."},
    {"id": 15, "title": "No keyboard shortcut for cancel",
     "desc": "Enter starts download but no Escape to cancel. Bind Escape when download is active."},
]


# ── PAGE BUILDERS ────────────────────────────────────────────────────────────

def page_cover(c):
    data = {
        "header_label": "CODE REVIEW REPORT",
        "title": "SaveThisVideo",
        "subtitle": "v1.2 Final Code Review",
        "metadata": f"{DOC_ID}  |  April 15, 2026  |  Head of Product Development",
        "footer_title": DOC_TITLE,
        "footer_id": DOC_ID,
        "badge": {
            "text": "NOT APPROVED FOR SHIP",
            "bg": HexColor("#5a2d2d"),
            "fg": HexColor("#ff4444"),
            "description": "10 demands must be resolved before green light",
        },
        "stats": [
            ("10", "DEMANDS"),
            ("15", "SUGGESTIONS"),
            ("7.0", "RATING"),
            ("0", "CRITICAL"),
        ],
        "severity_bar_title": "Severity Breakdown",
        "severity_bar": [
            (5, 5, "HIGH", BADGE_HIGH),
            (5, 5, "MEDIUM", BADGE_MEDIUM),
        ],
        "findings": [
            {
                "severity": "HIGH",
                "title": "Thread Safety & Race Conditions",
                "description": "Cross-thread write to _last_saved_path without synchronization. "
                               "Stale _tick callbacks can overwrite completion messages. "
                               "_ask_playlist can deadlock if window closes during dialog.",
            },
            {
                "severity": "HIGH",
                "title": "User-Hostile Failure Modes",
                "description": "Partial .part files litter Desktop on cancel/error. "
                               "Probe hangs block UI with no cancel path. "
                               "Silent file overwrite when probe fails.",
            },
            {
                "severity": "MEDIUM",
                "title": "Escaping & Documentation Gaps",
                "description": "osascript notification breaks on special chars in video titles. "
                               "build.sh and CLAUDE.md contradict each other on signing. "
                               "_hook ignores yt-dlp error status entirely.",
            },
        ],
        "context_note": {
            "title": "ARCHITECTURE ASSESSMENT",
            "text": "Thread safety discipline (capture-before-spawn + self.after() marshalling) "
                    "is textbook correct. Single-file architecture is appropriate for scope. "
                    "The Spotify-inspired redesign is clean with good token separation. "
                    "Issues are concentrated in edge-case handling and lifecycle robustness, "
                    "not fundamental architecture. This is a 7.0 codebase -- solid bones, "
                    "needs hardening for the last mile to production.",
        },
    }
    build_cover_page(c, data, TOTAL_PAGES)


def page_demands_1(c):
    """Demands D1-D5."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Demands (1 of 2)")
    y -= 4

    for d in DEMANDS[:5]:
        h = draw_item_card(
            c, MARGIN, y,
            d["id"], d["title"], d["severity"],
            d["desc"], d["files"], solution=d["fix"],
        )
        y -= h + 8
        if y < 60:
            break

    draw_footer(c, 2, TOTAL_PAGES, DOC_TITLE, DOC_ID)


def page_demands_2(c):
    """Demands D6-D10."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Demands (2 of 2)")
    y -= 4

    for d in DEMANDS[5:]:
        h = draw_item_card(
            c, MARGIN, y,
            d["id"], d["title"], d["severity"],
            d["desc"], d["files"], solution=d["fix"],
        )
        y -= h + 8
        if y < 60:
            break

    draw_footer(c, 3, TOTAL_PAGES, DOC_TITLE, DOC_ID)


def page_suggestions_1(c):
    """Suggestions S1-S10."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Suggestions (1 of 2)")
    y -= 4

    for s in SUGGESTIONS[:10]:
        h = draw_suggestion_card(c, y, s["id"], s["title"], s["desc"])
        y -= h + 5
        if y < 60:
            break

    draw_footer(c, 4, TOTAL_PAGES, DOC_TITLE, DOC_ID)


def page_suggestions_2(c):
    """Suggestions S11-S15."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Suggestions (2 of 2)")
    y -= 4

    for s in SUGGESTIONS[10:]:
        h = draw_suggestion_card(c, y, s["id"], s["title"], s["desc"])
        y -= h + 5

    # Files affected
    y -= 14
    y = draw_section_header(c, y, "Files Affected")
    y -= 4
    draw_files_affected(c, y, [
        ("app.py", "D1-D9, S1-S6, S10-S11, S13-S15 -- primary application"),
        ("build.sh", "D10 -- unsigned build documentation mismatch"),
        ("CLAUDE.md", "D10 -- contradicts build.sh on signing"),
        ("make_icon.py", "No issues found"),
        ("requirements.txt", "S7, S8 -- dependency hygiene"),
    ])

    draw_footer(c, 5, TOTAL_PAGES, DOC_TITLE, DOC_ID)


def page_impl_plan(c):
    """Implementation plan page."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Implementation Plan")
    y -= 4

    steps = [
        ("Thread Safety Pass",
         "D1 (pass path via after), D8 (guard _tick), D7 (short-timeout loop in _ask_playlist)",
         BADGE_HIGH),
        ("Resource Cleanup",
         "D2 (delete .part files on cancel/error), D4 (add nooverwrites to ydl_opts)",
         BADGE_HIGH),
        ("Network Resilience",
         "D6 (socket_timeout + cancel check after probe), D3 (nooverwrites safety net)",
         BADGE_HIGH),
        ("Escaping & Hooks",
         "D5 (pipe osascript via stdin), D9 (handle status == 'error' in _hook)",
         BADGE_MEDIUM),
        ("Documentation Alignment",
         "D10 (reconcile build.sh vs CLAUDE.md on signing)",
         BADGE_MEDIUM),
        ("Suggestion Pass",
         "S1-S15 — triage and implement in priority order after demands clear",
         BADGE_LOW),
    ]

    for i, (title, desc, color) in enumerate(steps, 1):
        h = draw_step_card(c, y, i, title, desc, color)
        y -= h

    # Risk assessment
    y -= 16
    draw_risk_box(c, y, "RISK ASSESSMENT", [
        ("Thread races (D1, D7, D8)", "Silent data corruption or UI confusion. Highest priority."),
        ("File litter (D2, D4)", "Cumulative user frustration. High visibility on Desktop default."),
        ("Probe hang (D6)", "App appears frozen. Users will force-quit and leave bad reviews."),
        ("osascript injection (D5)", "Low exploitability but violates Apple security standards."),
    ], border_color=BADGE_HIGH)

    draw_footer(c, 6, TOTAL_PAGES, DOC_TITLE, DOC_ID)


def page_verification(c):
    """Verification criteria + conclusion."""
    draw_bg(c)
    y = H - MARGIN
    y = draw_section_header(c, y, "Verification Criteria")
    y -= 4

    checks = [
        {"code": "_last_saved_path", "text": "passed via after() arg, not shared state"},
        {"code": "_tick()", "text": "returns immediately when not self._downloading"},
        {"code": "_ask_playlist()", "text": "checks _cancel in short-timeout loop"},
        {"code": "_worker()", "text": "deletes .part files on cancel/error"},
        {"code": "ydl_opts", "text": "includes 'nooverwrites': True unconditionally"},
        {"code": "_probe_info()", "text": "has socket_timeout: 15, cancel check after return"},
        {"code": "_notify()", "text": "pipes AppleScript via stdin or sanitizes to ASCII"},
        {"code": "_hook()", "text": "handles status == 'error' with UI update"},
        {"code": "build.sh", "text": "documentation matches CLAUDE.md on signing"},
        {"text": "All 10 demands verified green -- zero regressions in existing tests"},
    ]
    h = draw_checklist(c, y, checks)
    y -= h + 14

    # Score context
    y = draw_section_header(c, y, "Score Context")
    y -= 4
    y = draw_context_box(c, y, "RATING: 7.0 / 10", (
        "Solid architecture with good thread-safety discipline. The capture-before-spawn "
        "pattern, self.after() marshalling, and single-file simplicity are all correct choices. "
        "The Spotify-inspired redesign demonstrates attention to craft. Deductions: cross-thread "
        "shared state (D1), stale callback ordering (D8), resource leaks on cancel (D2), "
        "probe hang with no escape hatch (D6), and documentation inconsistencies (D10). "
        "All fixable without architectural changes. A passing score after demands are resolved "
        "would be 8.5-9.0 depending on suggestion uptake."
    ))

    # Conclusion
    y -= 8
    draw_conclusion_box(c, y, [
        "VERDICT:  NOT APPROVED FOR SHIP",
        "",
        "10 demands identified -- 5 HIGH, 5 MEDIUM. No CRITICAL issues.",
        "Thread safety, resource cleanup, and probe resilience are the top priorities.",
        "All demands are surgical fixes within the existing architecture.",
        "Estimated effort: 2-3 focused sessions to clear all 10 demands.",
        "",
        "Resolve all demands, verify against the checklist above, then resubmit.",
        "Expectation: 8.5+ on next review with a green light to ship.",
    ])

    draw_footer(c, 7, TOTAL_PAGES, DOC_TITLE, DOC_ID)


# ── BUILD ────────────────────────────────────────────────────────────────────

def main():
    c = canvas.Canvas(OUTPUT, pagesize=letter)
    c.setTitle(DOC_TITLE)

    page_cover(c)
    c.showPage()
    page_demands_1(c)
    c.showPage()
    page_demands_2(c)
    c.showPage()
    page_suggestions_1(c)
    c.showPage()
    page_suggestions_2(c)
    c.showPage()
    page_impl_plan(c)
    c.showPage()
    page_verification(c)
    c.showPage()

    c.save()
    size = os.path.getsize(OUTPUT)
    print(f"PDF generated: {OUTPUT}")
    print(f"Size: {size:,} bytes  ({size // 1024} KB)")
    print(f"Pages: {TOTAL_PAGES}")


if __name__ == "__main__":
    main()
