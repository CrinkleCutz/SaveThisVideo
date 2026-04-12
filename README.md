# SaveThisVideo

**An ultra lightweight video downloader that lets you easily save a video from any of your favorite social networking sites. Don't let that piece of media disappear! Save This Video!**

Paste a link. Pick your quality. Done. No command line, no subscriptions, no nonsense.

---

## What it does

SaveThisVideo is a clean, no-fuss macOS app that puts the power of [yt-dlp](https://github.com/yt-dlp/yt-dlp) — one of the most capable video download engines in the world — behind a simple point-and-click interface. If you've ever watched something and thought *"I need to keep this"*, SaveThisVideo is your answer.

**Supported sites include:**
YouTube · Instagram · Twitter/X · TikTok · Vimeo · Reddit · Facebook · Twitch · SoundCloud · Dailymotion · Rumble · Pinterest · and **1,000+ more**

---

## Features

- **Paste & go** — copy a link, hit Paste, hit Download
- **Quality picker** — Best Available, 4K, 1080p, 720p, 480p, 360p, or Audio Only (MP3)
- **Browser cookies** — log in to Safari, Chrome, or Firefox, then let SaveThisVideo borrow your session for members-only or age-restricted content
- **Playlist detection** — pastes a playlist URL? It asks before downloading 200 videos onto your Desktop
- **Live progress** — real-time speed, ETA, and progress bar
- **Disk space guard** — warns you before starting if your destination is running low
- **Saves anywhere** — defaults to your Desktop, or browse to any folder
- **Fully self-contained** — no Homebrew, no Python, no dependencies to install. ffmpeg is bundled right inside.

---

## Installation

1. Download `SaveThisVideo.zip`
2. Unzip it — you'll get `SaveThisVideo.app`
3. **First launch:** right-click the app → **Open** → click **Open** in the dialog
   *(This one-time step is needed because the app is unsigned. After that, it opens normally.)*

---

## Screenshot

```
┌─────────────────────────────────────────────────────────┐
│  Video URL                                               │
│  [ Paste a link from YouTube, Vimeo, TikTok… ] [Paste]  │
│  Quality ▼         Save to: ~/Desktop      [Browse…]     │
│  Cookies from browser: [None ▼]                          │
│  [          Download          ]                          │
│  ████████████████░░░░░░  2.3 MB/s  •  ETA 0:14           │
│  My Favorite Video.mp4                                   │
└─────────────────────────────────────────────────────────┘
```

---

## For developers

```bash
git clone https://github.com/CrinkleCutz/SaveThisVideo.git
cd SaveThisVideo
./setup.sh       # create venv, install dependencies, check ffmpeg
./run.sh         # launch in dev mode
```

To build the distributable `.app`:

```bash
./build.sh
# Output: dist/SaveThisVideo.zip
```

**Stack:** Python 3.10+ · customtkinter · yt-dlp · static-ffmpeg · curl_cffi · PyInstaller

---

## Upgrading yt-dlp

yt-dlp is the engine that talks to each website. Sites occasionally change their APIs and yt-dlp releases a fix. To update:

```bash
.venv/bin/pip install --upgrade yt-dlp
# test it, then pin the new version in requirements.txt
```

---

## Logs

App logs are written to `~/Library/Logs/SaveThisVideo/app.log` (2 MB rotating, 3 backups). Full URLs are never logged.

---

## License

Personal use. Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and [customtkinter](https://github.com/TomSchimansky/CustomTkinter) (MIT).
