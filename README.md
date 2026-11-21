# Keptwise

Turns your doomscrolls into productivity.

Keptwise is a free Windows app for the videos you've saved on TikTok, YouTube, Instagram and Facebook. It transcribes them, writes short notes with steps you can follow, and sorts them into collections you can search and ask questions about.

It runs on your PC with no Keptwise account or tracking. A free local AI can work offline once your saves have been processed. Keptwise uses the exports and video pages to build your library, and leaves your platform accounts and saves as they are.

## Features

- **Import** the data export from each platform (just drag the zip in). Importing again only adds new saves.
- **Transcripts** made on your PC with Whisper. In **Sort**, retry videos with no detected speech, retry failed downloads, or recheck videos marked unavailable. Open a save to retry it on its own.
- **Notes**: a summary, key details and next steps for every save.
- **Collections** organized by hand or with AI suggestions that you can review and approve.
- **Plans**: tick off a recipe's or a trip's steps as you go.
- **Search** captions, transcripts and notes by word or idea. Tag, file, plan, or archive saves directly from the results.
- **Assistant** chats about your library, asks for details when a request is unclear, and can find or organise saves. Undo the Assistant’s latest library edit from its reply.
- **Unsave**: a checklist for videos you want to unsave on their platforms. Clear the checklist whenever you want a fresh list.

## Install

1. Download **Keptwise-Setup.exe** from the [latest release](https://github.com/vptr-dev/keptwise/releases/latest).
2. Run it. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed). No admin password is needed.
3. Open Keptwise from the Start menu.

On first start you pick your look and AI. The guided tour highlights real controls across the app, from Import and Sort to Search and Unsave.

- **Free, on this PC** with [Ollama](https://ollama.com/download). The app downloads the model for you (`gemma4:12b`, about 8 GB, or `gemma4:e4b` for slower PCs).
- **Cloud** with your own Claude, OpenAI, Gemini or OpenRouter key. The key is stored in Windows Credential Manager, and the app asks before any batch that costs money.

The speech model for transcripts (466 MB) downloads the first time you use it. Short clips get a second pass when the first pass detects no speech.

If a video plays only when you're signed in, **Sort → TikTok access** can load a TikTok-only Netscape cookies.txt session from your signed-in browser. Keep the file private. Keptwise keeps the session in memory for TikTok requests until you disconnect or close the app. TikTok still decides which videos the account can see.

## Getting your saves

The Import screen has a guide for each platform. Ask for the **JSON** format where there's a choice:

- **TikTok**: Settings and privacy → Account → Download your data
- **YouTube**: [Google Takeout](https://takeout.google.com) → YouTube and YouTube Music
- **Instagram / Facebook**: Accounts Centre → Your information and permissions → Download your information

Your data lives in `%APPDATA%\Keptwise`. The app checks GitHub once a day. You can check sooner or install an update from **Settings → Updates**.

## Development

Needs Windows, Python 3.12 (from [uv](https://docs.astral.sh/uv/), whose builds have the newer OpenSSL that TikTok accepts), Node.js LTS and Git.

```powershell
.\scripts\dev.ps1        # set up and run the app
.\scripts\test.ps1       # backend (pytest) and frontend (Vitest) tests
.\packaging\build.ps1    # build dist\Keptwise-Setup.exe (needs Inno Setup 6)
```

`backend/` is FastAPI and SQLite, `frontend/` is React and Tailwind, `desktop/` is the pywebview window, and `packaging/` holds the installer scripts. Pushing a tag like `v1.2.0` builds a release on GitHub.
