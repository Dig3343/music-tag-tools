# Music-tag-Tools

Tidy up an **mp3 / flac** library from the command line: consistent tags, covers, lyrics, and covers that show up in Windows.
No code editing: everything is a command or an option. **Every command only previews until you add `--apply`.**

> Back up your music before using `--apply`.

**Intended use:** personal, non-commercial organization of your own music collection. The online services it talks to (AcoustID, MusicBrainz, LRCLIB, Cover Art Archive) are meant for personal use, and AcoustID is free for non-commercial use only.

## Install (3 steps)

1. Install [Python 3.8+](https://www.python.org/downloads/) (on Windows tick "Add Python to PATH").
2. Open a terminal and run `pip install mutagen`.
3. Unzip this project and, inside its folder, run `python main.py` (on Windows `py main.py`).

Run it with no arguments to get a short menu that asks what to do and which folder.

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

Every command prints what it is going to do (PREVIEW or APPLY), asks "did you back up?" before changing files, and ends with a summary. The CSV reports (before/after of every change; open them with Excel) are saved in a `_reports` folder created inside your music folder. Duplicates are moved, never deleted, to `_duplicates`.

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

`audio` and `both` also pair every file with the right track, flag tracks whose tags disagree with the audio (`check` rows in the report; titles aren't changed without `--overwrite`) and look up lyrics with the identified title/artist.

One-time setup for `audio` / `both`:
1. Download `fpcalc` from <https://acoustid.org/chromaprint> (Windows: `chromaprint-fpcalc-1.6.1-windows-x86_64.zip`, 64-bit only), extract it, and put `fpcalc.exe` in your PATH or pass `--fpcalc "C:\path\fpcalc.exe"`.
2. Get a free key at <https://acoustid.org/new-application> and pass it with `--acoustid-key` (or set `ACOUSTID_API_KEY`).

AcoustID is free for **non-commercial use only** and limited to 3 requests per second. Chromaprint is MIT-licensed but, as a whole, LGPL 2.1 because it includes parts of FFmpeg; musictools only runs it as a separate program and doesn't include it.

Notes: the services are rate-limited and answers are cached in `_reports/online_cache`, so the `--apply` run after a preview is quick. The preview does contact the internet but never writes to your files. Cover art and lyrics are usually copyrighted by their owners; the services provide them for personal use.

## Troubleshooting

- **Covers still missing in Windows Explorer** -> run `id3v23 --apply`, then reopen the folder.
- **`python` / `py` not found** -> reinstall Python with "Add Python to PATH" ticked.
- **Online commands stop with "can't reach the online services"** -> check your connection and run again; finished answers are cached.
- **An album wasn't matched** -> it is listed at the end of the `online` run; fix its tags with `tags` or use `--match audio`.

## Tests

```
python -m unittest discover -s tests -t .
```
The online tests use fake service answers; no network is needed.

## License

MIT, see `LICENSE`.

This project uses [mutagen](https://github.com/quodlibet/mutagen) (GPL-2.0-or-later) to read and write tags. It is installed separately (`pip install mutagen`) and is **not** included in this repository, the same arrangement used by other MIT projects such as [beets](https://github.com/beetbox/beets) and [MediaFile](https://github.com/beetbox/mediafile). Whether that makes a combined work subject to the GPL is debated; a bundle that includes mutagen itself (e.g. a frozen `.exe`) must comply with the GPL.
