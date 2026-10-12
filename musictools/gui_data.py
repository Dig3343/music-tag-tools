# SPDX-License-Identifier: GPL-3.0-or-later
"""Data behind the window's result tables (no tkinter here, so it can be tested).

- read_track / scan_library: what is inside the audio files (for the "Tracks" table).
- load_report / summarize: the CSV report of the last run (for the "Results" table).
"""

import csv
import hashlib
import time
from pathlib import Path

from .common import find_audio_files, first_number

REPORT_COLUMNS = {
    "tags": ("file", "field", "before", "after", "reason"),
    "online": ("file", "kind", "field", "before", "after", "source"),
    "covers": ("file", "album artist", "album", "action", "source", "problem"),
    "id3v23": ("file", "version before", "version after"),
}
REPORT_STEMS = {"tags": "tags", "online": "online", "covers": "covers", "id3v23": "id3v23"}


# ------------------------------------------------------------------- tracks ---

def _text(frame):
    try:
        return str(frame.text[0]).strip()
    except (AttributeError, IndexError):
        return str(frame).strip()


def read_track(path):
    """Return a dict with title/artist/album/albumartist/track/lyrics/cover/format for one file,
    or None if it cannot be read."""
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3

    path = Path(path)
    info = {"path": str(path), "title": "", "artist": "", "album": "", "albumartist": "", "track": 0,
            "lyrics": "", "cover": None, "format": ""}
    try:
        if path.suffix.lower() == ".flac":
            audio = FLAC(path)
            info["format"] = "FLAC"

            def get(key):
                return str(audio[key][0]).strip() if audio.get(key) else ""
            info.update(title=get("title"), artist=get("artist"), album=get("album"),
                        albumartist=get("albumartist"), track=first_number(get("tracknumber")),
                        lyrics=get("lyrics") or get("unsyncedlyrics"))
            if audio.pictures:
                info["cover"] = bytes(audio.pictures[0].data)
        else:
            audio = MP3(path)
            tags = audio.tags
            if tags is None:
                info["format"] = "mp3 (no tags)"
                return info
            info["format"] = "ID3v%d.%d" % tuple(tags.version[:2])

            def get(frame_id):
                frame = tags.get(frame_id)
                return _text(frame) if frame else ""
            lyrics_frames = tags.getall("USLT")
            info.update(title=get("TIT2"), artist=get("TPE1"), album=get("TALB"), albumartist=get("TPE2"),
                        track=first_number(get("TRCK")),
                        lyrics=str(lyrics_frames[0].text).strip() if lyrics_frames else "")
            pictures = tags.getall("APIC")
            if pictures:
                info["cover"] = bytes(pictures[0].data)
    except Exception:
        return None
    return info


def cover_key(data):
    return hashlib.md5(data).hexdigest() if data else ""


def scan_library(folder, make_thumb=None, should_stop=lambda: False):
    """Yield (index, total, track_dict) for every audio file under 'folder'.
    With make_thumb(bytes) one thumbnail is built per distinct cover (track_dict['thumb'])."""
    files = find_audio_files(folder)
    total = len(files)
    cache = {}
    for index, path in enumerate(files, 1):
        if should_stop():
            return
        info = read_track(path)
        if info is None:
            continue
        data = info.pop("cover")
        key = cover_key(data)
        info["cover_key"] = key
        if key and make_thumb and key not in cache:
            try:
                cache[key] = make_thumb(data)
            except Exception:
                cache[key] = None
        info["thumb"] = cache.get(key)
        yield index, total, info


def track_issues(track):
    """Names of the things a track is missing (used for the filter)."""
    issues = []
    if not track.get("cover_key"):
        issues.append("cover")
    if not track.get("lyrics"):
        issues.append("lyrics")
    if not track.get("albumartist"):
        issues.append("albumartist")
    return issues


def filter_tracks(tracks, text="", only=""):
    """Tracks whose title/artist/album/album artist/file contain 'text' (case-insensitive) and,
    if 'only' is "cover", "lyrics" or "albumartist", that miss that thing."""
    text = text.strip().lower()
    result = []
    for track in tracks:
        if only and only not in track_issues(track):
            continue
        if text:
            haystack = " ".join((track["title"], track["artist"], track["album"], track["albumartist"],
                                 Path(track["path"]).name)).lower()
            if text not in haystack:
                continue
        result.append(track)
    return result


def library_summary(tracks):
    return {"tracks": len(tracks),
            "no_cover": sum(1 for t in tracks if not t.get("cover_key")),
            "no_lyrics": sum(1 for t in tracks if not t.get("lyrics")),
            "no_albumartist": sum(1 for t in tracks if not t.get("albumartist"))}


# ------------------------------------------------------------------ reports ---

def find_report(out_dir, command, apply, since):
    """Newest CSV report written by this run (the program may add a time suffix if the file was open)."""
    out_dir = Path(out_dir)
    stem = f"{REPORT_STEMS[command]}_{'applied' if apply else 'preview'}"
    candidates = [p for p in out_dir.glob(stem + "*.csv") if p.stat().st_mtime >= since - 2]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def load_report(path):
    """Rows of a report as a list of lists (without the 'sep=,' line and the header), plus the header."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        lines = fh.read().splitlines()
    if lines and lines[0].lower().startswith("sep="):
        lines = lines[1:]
    rows = list(csv.reader(lines))
    return (rows[0], rows[1:]) if rows else ([], [])


def summarize(command, header, rows):
    """Small summary for the cards: number of changes, number of files, and the most common kinds."""
    files = {row[0] for row in rows if row}
    counts = {}
    if command in ("tags", "online"):
        index = header.index("field") if "field" in header else 1
        for row in rows:
            if len(row) > index:
                counts[row[index]] = counts.get(row[index], 0) + 1
    elif command == "covers":
        index = header.index("action") if "action" in header else 3
        for row in rows:
            if len(row) > index:
                counts[row[index]] = counts.get(row[index], 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"changes": len(rows), "files": len(files), "kinds": ordered[:6]}


def display_name(file_value, root):
    """File path as shown in the tables: relative to the music folder when possible."""
    try:
        return str(Path(file_value).resolve().relative_to(Path(root).resolve()))
    except (ValueError, OSError):
        return str(file_value)


def now():
    return time.time()
