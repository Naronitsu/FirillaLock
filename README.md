# Firilla Voice Lock

Say **"Firilla lock"** and your Windows PC locks, but only if it's *your* voice.

- Your voice: the PC says **"Yes master"** and locks.
- Someone else's voice: it says **"Firilla denied."** and does nothing.

Everything runs locally. No audio ever leaves your computer.

> **Security note:** voice matching is a convenience, not strong security. A recording of your voice could fool it. Don't rely on it as your only lock.

## Requirements

- Windows 10/11
- Python 3.10 or newer. Don't have it? `Setup.bat` offers to install Python 3.11 for you (see below)
- A microphone
- Internet on first setup only (packages, plus a ~140 MB speech model)

## Setup

1. Put the folder anywhere you like.
2. Double-click **`Setup.bat`**.

If Python 3.10+ isn't found, Setup asks **"Install Python now?"**. Say yes and it installs Python 3.11 for your user account only (no admin rights), using `winget` if available or the official installer from python.org otherwise. Say no and it points you to python.org.

Setup creates a virtual environment, installs the packages, downloads the speech model into `models/`, draws the icon, adds a **Firilla Voice Lock** shortcut to your desktop and launches the app. If the `models/` folder is already present, nothing is downloaded.

## First run

1. Pick your microphone and check that the level bar moves when you talk.
2. Click **Enroll voice** and say "Firilla lock" six times when prompted. Each sample is checked, and anything that doesn't sound like the phrase is rejected.
3. Click **Test** a few times. The diary shows what it heard and your voice score, and says whether it would lock.
4. Turn on **Practice mode**, press **Start**, and try the real phrase. When you're happy, turn Practice mode off.

## Using it day to day

| Task | How |
| --- | --- |
| Open the app | Desktop shortcut **Firilla Voice Lock**, or `Firilla.bat` |
| Start / stop listening | **Start** / **Stop** button, or the tray menu |
| Hide the window | Close it (X). It keeps running in the system tray |
| Reopen the window | Double-click the tray icon (check the ^ overflow arrow) or right-click, then **Open** |
| Quit completely | Right-click the tray icon, then **Quit** |
| Start at login | Tick **Wake up automatically when I log in**. It starts hidden and listens if you've enrolled |

### Settings

- **Voice strictness** (default 0.75): the voice-match score you need. Lower is easier to get in, but others might too. Higher is pickier, so you might get denied. Use **Test** to see your own scores and leave some margin.
- **Practice mode:** it answers as usual but never locks.
- **Microphone:** if you change mics, re-enroll.

## Moving to another PC

1. Run **`Make-Portable-Zip.bat`**. It writes `Firilla-portable.zip` to your desktop (app and speech model; no `.venv`, no voiceprint).
2. Copy and unzip it on the other PC.
3. Double-click **`Setup.bat`** there, then enroll your voice again (about 30 seconds).

To keep your voiceprint and settings, also copy `voiceprint.npy` and `config.json`. The `.venv` folder cannot be copied between PCs, because Setup rebuilds it.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Level bar doesn't move | Pick another microphone in the dropdown. Check Windows' mic privacy setting |
| It keeps denying you | Lower the strictness slider, or re-enroll in a quiet spot with the mic you'll actually use |
| It doesn't react to the phrase | Check the diary for what it heard. Speak clearly, closer to the mic |
| Model download fails | Check your internet and restart the app, or copy the `models/` folder from another PC |
| Python was installed but Setup can't find it | Close the window and run `Setup.bat` again, or install Python manually from python.org with **Add python.exe to PATH** ticked |
| Shortcut is gone | Run `make_shortcut.ps1` (right-click, **Run with PowerShell**) |

## What's in the folder

| Path | Purpose |
| --- | --- |
| `app.py` | The window and tray icon |
| `firilla.py` | Engine: listening, speech recognition, voice check, locking |
| `icon.py` | Draws the eggplant-with-padlock icon |
| `Setup.bat` | One-click installer |
| `Firilla.bat` | Launches the app |
| `Make-Portable-Zip.bat` | Packs the app for another PC |
| `make_shortcut.ps1` | Creates the desktop shortcut |
| `requirements.txt` | Python packages (PyTorch and resemblyzer are installed separately by `Setup.bat`) |
| `models/` | Speech model (downloaded once; git-ignored) |
| `voiceprint.npy`, `config.json` | Your voice and settings (git-ignored) |

## How it works

1. A voice-activity detector cuts the mic stream into utterances and ignores steady background noise.
2. [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base.en`) transcribes each utterance and a fuzzy match looks for "Firilla lock".
3. [Resemblyzer](https://github.com/resemble-ai/Resemblyzer) turns the utterance into a voice embedding, which is compared with your enrolled voiceprint by cosine similarity.
4. If the score clears the threshold, Windows' speech voice says "Yes master" and `LockWorkStation` locks the PC. Otherwise it says "Firilla denied."
