# Changelog

## 1.2.0
- **License changed from MIT to GPL-3.0-or-later**, because `musictools.exe` bundles mutagen (GPL). Added `THIRD_PARTY.md`.
- New graphical window: `python main.py gui` (or double-click `musictools_gui.pyw` on Windows). Same commands and the same preview-first safety, with live log, Stop button and a confirmation before applying.
- The window (customtkinter, `pip install customtkinter`) has tabs per step with a hint next to every option, an **Instructions** button explaining everything, and an **IT / EN** language switch. Without customtkinter it falls back to a simple English tkinter window.
- The program now shows its own icon in the Windows taskbar too.
- New icon (`assets/`) and a Windows program, `musictools.exe`, built automatically by GitHub Actions and attached to each release (`.github/workflows/build-exe.yml`). Double-click to open the window; no Python needed.
- Settings on the left, views on the right (resizable divider, tables scroll sideways, larger cover thumbnails): a *Results* table of the changes, a *Tracks* browser (cover thumbnails, number, title, artist, album, album artist, lyrics, format/ID3 version; search, filters, sorting) and the *Log*.
- The window remembers your settings in `~/.musictools_gui.json` (plain text, includes the AcoustID key if you enter it).

## 1.1.0
- `online`: albums are grouped by folder and title, so guest artists or different capitalization of the artist no longer split an album.
- `online`: releases with fewer tracks than yours, or whose tracks don't fit yours (another edition), are skipped and listed instead of guessed; `--verbose` explains every rejection.
- `online`: new `--match tags|audio|both` switch (audio fingerprint through AcoustID; newer and less tested).
- `online`: warns when some online requests were refused.
- Reports: saved in a `_reports` folder inside your music folder; Excel opens the columns correctly; a report open in Excel no longer crashes the program.
- Start menu when run without arguments, clear PREVIEW / APPLY messages and a "did you back up?" confirmation.
- English documentation, plus `README.txt`.

## 1.0.0
- First release: `tags`, `covers`, `id3v23` and `online` (metadata, covers, lyrics).
