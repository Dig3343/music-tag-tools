# musictools

Tidy up an **mp3 / flac** library from the command line: consistent tags, covers, lyrics, and covers that show up in Windows.
No code editing: everything is a command or an option. **Every command only previews until you add `--apply`.**

> Back up your music before using `--apply`.

**Intended use:** personal organization of your own music collection. The online services it talks to (AcoustID, MusicBrainz, LRCLIB, Cover Art Archive) are meant for personal use, and AcoustID is free for non-commercial use only.

## Install (3 steps)

1. Install [Python 3.8+](https://www.python.org/downloads/) (on Windows tick "Add Python to PATH").
2. Open a terminal and run `pip install mutagen customtkinter` (customtkinter is only for the window).
3. Unzip this project and, inside its folder, run `python main.py` (on Windows `py main.py`).

Run it with no arguments to get a short menu that asks what to do and which folder.

## Graphical window (no typing)

```
pip install customtkinter
python main.py gui
```
On Windows you can also double-click `musictools_gui.pyw`, or use the ready-made `musictools.exe` (below).

The window has one tab per step (**Start, Tags, Online, Covers, Windows covers**), with a short explanation next to every option. Choose your music folder, pick a tab and press **Preview**; nothing changes until you press **Apply changes** and confirm. The log shows what is happening live, **Stop** cancels, and **Open reports folder** opens the CSV reports.

- **Right side** (drag the divider to resize it; tables scroll sideways): *Results* shows a table of every change (file, field, before, after, reason) after a Preview or Apply; *Tracks* lists all the tracks of your folder with a small cover, number, title, artist, album, album artist, lyrics and format (ID3 version), with search, filters (no cover / no lyrics / no album artist) and sortable columns; *Log* has the raw text.
- **Instructions** button: explains every tab and option inside the program.
- **IT / EN** button: switches the window between Italian and English (the log of the commands stays in English). The first time it follows your Windows language.
- Without `customtkinter` the program falls back to a simpler English-only window.

The window remembers your folder, rules file, AcoustID key, fpcalc path, email and language in a plain-text file, `.musictools_gui.json` in your home folder. Delete it to forget them.

## Windows program (no terminal)

Download `musictools.exe` from the [latest release](../../releases/latest) and double-click it: it opens the window described above. Nothing to install.

- Windows may show "Windows protected your PC" because the program is not code-signed. Click **More info**, then **Run anyway**. Some antivirus programs also warn about programs made with PyInstaller; if in doubt, use the Python version.
- For `--match audio` you still need `fpcalc.exe` (see below) and your free AcoustID key; the window has a field for each.

## Commands

| Command | What it does |
|---|---|
| `tags` | Fixes artist / album artist / album names, moves guests into the title, marks compilations, finds duplicates |
| `online` | Fills in missing info (MusicBrainz), missing covers (Cover Art Archive) and lyrics (LRCLIB) |
| `covers` | Finds missing or broken covers and copies the right one from the same album (disc by disc) |
| `id3v23` | Converts mp3 tags to ID3v2.3 so Windows Explorer / Media Player show the covers |

Suggested order: `tags` -> `online` -> `covers` -> `id3v23`.

```
python main.py tags "D:/Music"             # preview: changes nothing
python main.py tags "D:/Music" --apply     # really changes the files
python main.py tags --help                 # every option of a command
```

Every command prints what it is going to do (PREVIEW or APPLY), asks "did you back up?" before changing files, and ends with a summary. The CSV reports (before/after of every change; open them with Excel) are saved in a `_reports` folder created inside your music folder. Duplicates are moved, never deleted, to `_duplicates`. If a report is open in Excel when a command ends, the new one is saved under a different name (with the time) instead of failing.

Options common to all commands: `--apply`, `--yes` (skip the confirmation), `--out-dir FOLDER` (where to save reports).

## `tags`

| Option | Effect |
|---|---|
| `--rules FILE.json` | your own per-album rules (see below) |
| `--no-auto` | no automatic decisions, only rules and unified album titles |
| `--main-artist-ratio 0.6` | share of tracks by one artist for the album to count as "by that artist"; below it, it's a compilation |
| `--split-comma` | also treat `,` and `&` as artist separators |
| `--no-feat-in-title` | don't move guests into the title |
| `--keep-compilation-artists` | in compilations keep each track's artist |
| `--move-dupes` | with `--apply`, move exact duplicates to `_duplicates` |
| `--verbose` | print the decision for every album |

**Rules file** – for cases the automatic logic can't guess (`rules.example.json`):

```json
{ "rules": [ {
    "album_regex": "^greatest hits of the 80s$",
    "set": { "artist": "Various Artists" },
    "compilation": true,
    "artist_in_title": true
} ] }
```
`album_regex` is a regular expression on the album title (lowercase, without `:`); the first matching rule wins. `set` can contain `artist`, `albumartist`, `album`, `discnumber`. Name your personal file anything (`my_rules.json` is in `.gitignore`).

## `covers`

| Option | Effect |
|---|---|
| *(none)* | add/repair missing or invalid covers from other tracks of the album; list albums with different covers |
| `--unify` | make valid-but-different covers identical **within the same disc** |
| `--export` | save the different covers to `_reports/cover_compare` to compare them by eye |
| `--inspect` | change nothing, show what's inside each file (use on one album folder) |
| `--set-cover IMG [--from N] [--to N] [--disc N]` | put the chosen image on the selected tracks (one album folder) |

## `online`

```
python main.py online "D:/Music" --contact you@example.com --apply
```

| Option | Effect |
|---|---|
| `--metadata` / `--covers` / `--lyrics` | choose what to do (none = all three) |
| `--match tags\|audio\|both` | how tracks are identified (below) |
| `--acoustid-key KEY`, `--fpcalc PATH` | needed for `audio` / `both` |
| `--lrc` | also save synced lyrics as a `.lrc` file next to each track |
| `--overwrite` | replace existing title/date/genre/numbers/lyrics (artist and album artist are never overwritten) |
| `--cover-size 250\|500\|1200` | cover size to download (default 500) |
| `--contact EMAIL` | identifies you to MusicBrainz (or set `MUSICTOOLS_CONTACT`) |
| `--no-cache`, `--verbose` | ignore saved answers / print every decision |

How albums are matched: an album is the set of files in one folder with the same album title. A MusicBrainz release is accepted only if its title and artist agree and it has at least as many tracks as you do. If most of your tracks don't fit the release (probably another edition) the album is skipped and listed, never guessed. Add `--verbose` to see why a release was rejected.

What it fills in, **only where empty** unless you use `--overwrite`:
- **metadata** (MusicBrainz): date, original date, genre, track/disc numbers, missing titles and artists, MusicBrainz IDs. The album must match by title, artist and track count, otherwise it is skipped and listed.
- **covers** (Cover Art Archive): only for albums where *no* track has a usable cover (use `covers` to spread an existing one).
- **lyrics** (LRCLIB): embedded in the file (ID3 `USLT` / FLAC `LYRICS`). Check that your player shows embedded lyrics or `.lrc` files.

### Choosing how tracks are identified (`--match`)

| Value | Speed | Reliability |
|---|---|---|
| `tags` *(default)* | fast, nothing to set up | depends on how clean your tags are |
| `audio` | slow (about a second per track) | safest: audio fingerprint; unrecognized tracks are left untouched |
| `both` | slow | fingerprint first, tags as fallback |

`audio` and `both` are newer and less tested than `tags`: always preview first. They also pair every file with the right track, flag tracks whose tags disagree with the audio (`check` rows in the report; titles aren't changed without `--overwrite`) and look up lyrics with the identified title/artist.

One-time setup for `audio` / `both`:
1. Download `fpcalc` from <https://acoustid.org/chromaprint> (Windows: `chromaprint-fpcalc-1.6.1-windows-x86_64.zip`, 64-bit only), extract it, and put `fpcalc.exe` next to `main.py` and pass `--fpcalc .\fpcalc.exe` (or put it in your PATH, or pass its full path).
2. Get a free key at <https://acoustid.org/new-application> and pass it with `--acoustid-key` (or set `ACOUSTID_API_KEY`).

AcoustID is free for **non-commercial use only** and limited to 3 requests per second. Chromaprint is MIT-licensed but, as a whole, LGPL 2.1 because it includes parts of FFmpeg; musictools only runs it as a separate program and doesn't include it.

Notes: the services are rate-limited and answers are cached in `_reports/online_cache`, so the `--apply` run after a preview is quick. The preview does contact the internet but never writes to your files. Cover art and lyrics are usually copyrighted by their owners; the services provide them for personal use.

## Troubleshooting

- **Covers still missing in Windows Explorer** -> run `id3v23 --apply`, then reopen the folder.
- **`python` / `py` not found** -> reinstall Python with "Add Python to PATH" ticked.
- **Online commands stop with "can't reach the online services"** -> check your connection and run again; finished answers are cached.
- **`PermissionError` on a report** -> the .csv was open in Excel. Close it (recent versions save under a new name instead).
- **`Folder not found`** -> check the path in quotes; run the command from the project folder (the one containing `main.py`).
- **"found a release, but your tracks don't fit it"** -> MusicBrainz has that edition with different tracks; nothing was changed.
- **An album wasn't matched** -> it is listed at the end of the `online` run; fix its tags with `tags` or use `--match audio`.

## Tests

```
python -m unittest discover -s tests -t .
```
The online tests use fake service answers; no network is needed.

## License

musictools is free software under the **GNU General Public License, version 3 or (at your option) any later version** (GPL-3.0-or-later); see `LICENSE`. You can use, study, change and share it, but if you distribute a modified version it must stay under the same license, with its source code.

The license does not restrict commercial use. The *intended* use is personal (organizing your own music), and the online services it uses have their own rules: for example AcoustID is free for non-commercial use only.

| Component | License | How it is used |
|---|---|---|
| [mutagen](https://github.com/quodlibet/mutagen) | GPL-2.0-or-later | read/write tags; bundled in `musictools.exe` |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | the window; bundled in `musictools.exe` |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | small covers in the window; bundled in `musictools.exe` |
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later with a bootloader exception | builds `musictools.exe` |
| [Chromaprint / fpcalc](https://acoustid.org/chromaprint) | LGPL-2.1 (as a whole) | optional separate program, not included |

The source code that corresponds to every `musictools.exe` is the tag of the same version in this repository. See `THIRD_PARTY.md` for details.
