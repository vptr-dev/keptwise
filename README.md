# Keptwise

Turns your doomscrolls into productivity.

Keptwise is a free Windows app for the videos you've saved on TikTok, YouTube, Instagram and Facebook. It transcribes them, writes short notes with steps you can follow, and sorts them into collections you can search and ask questions about.

It runs on your PC. No account, no tracking, and it works offline with a free local AI. It never logs in to the platforms or changes anything there; it only reads the data export they give you.

## Features

- **Import** the data export from each platform (just drag the zip in). Importing again only adds new saves.
- **Transcripts** of each public video, made on your PC with Whisper.
- **Notes**: a summary, key details and next steps for every save.
- **Collections**, sorted by the AI or by hand. Anything it isn't sure about waits in Needs review.
- **Plans**: tick off a recipe's or a trip's steps as you go.
- **Search** by words or by idea, and **ask** questions that are answered only from your saves.
- **Unsave**: a list of saves whose notes are kept, so you can clear them out of the original app.

## Install

1. Download **Keptwise-Setup.exe** from the [latest release](https://github.com/vptr-dev/keptwise/releases/latest).
2. Run it. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed). No admin password is needed.
3. Open Keptwise from the Start menu.

On first start you pick your look and your AI:

- **Free, on this PC** with [Ollama](https://ollama.com/download). The app downloads the model for you (`gemma4:12b`, about 8 GB, or `gemma4:e4b` for slower PCs).
- **Cloud** with your own Claude, OpenAI, Gemini or OpenRouter key. The key is stored in Windows Credential Manager, and the app asks before any batch that costs money.

The speech model for transcripts (466 MB) downloads the first time you use it.

## Getting your saves

The Import screen has a guide for each platform. Ask for the **JSON** format where there's a choice:

- **TikTok**: Settings and privacy → Account → Download your data
- **YouTube**: [Google Takeout](https://takeout.google.com) → YouTube and YouTube Music
- **Instagram / Facebook**: Accounts Centre → Your information and permissions → Download your information

Your data lives in `%APPDATA%\Keptwise`. The app checks GitHub once a day for a new version and only shows a link; turn that off in Settings.

## Development

Needs Windows, Python 3.12 (from [uv](https://docs.astral.sh/uv/), whose builds have the newer OpenSSL that TikTok accepts), Node.js LTS and Git.

```powershell
.\scripts\dev.ps1        # set up and run the app
.\scripts\test.ps1       # backend (pytest) and frontend (Vitest) tests
.\packaging\build.ps1    # build dist\Keptwise-Setup.exe (needs Inno Setup 6)
```

`backend/` is FastAPI and SQLite, `frontend/` is React and Tailwind, `desktop/` is the pywebview window, and `packaging/` holds the installer scripts. Pushing a tag like `v1.2.0` builds a release on GitHub.
