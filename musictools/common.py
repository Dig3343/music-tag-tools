"""Helpers shared by all commands."""

import csv
import re
from pathlib import Path

AUDIO_EXTS = {".mp3", ".flac"}
DUPES_DIRNAME = "_duplicates"      # folder where --move-dupes puts duplicates
REPORTS_DIRNAME = "_reports"      # created inside the music folder for CSV logs and comparison images


def find_audio_files(root):
    """List audio files under 'root' (or the file itself), skipping the duplicates folder."""
    root = Path(root)
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise SystemExit(f"Folder not found: {root}")
    files = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTS:
            if DUPES_DIRNAME not in path.relative_to(root).parts:
                files.append(path)
    return sorted(files)


def first(audio, key):
    """First value of tag 'key' (empty string if missing)."""
    value = audio.get(key) if audio else None
    return str(value[0]).strip() if value else ""


def first_number(text):
    """First number in a string like '3/12' (0 if none)."""
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else 0


def norm(text):
    """Lowercase, without ':' and with single spaces (used to compare album titles)."""
    return re.sub(r"\s+", " ", text.replace(":", " ")).strip().lower()


def key_text(text):
    """Comparison key: letters and digits only, lowercase."""
    return re.sub(r"\W+", "", text.lower())


def safe_name(name):
    """Valid folder/file name on Windows (no forbidden characters, no trailing space or dot)."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:80].strip(" .") or "album"


def write_csv(out_dir, name, header, rows):
    """Write an Excel-friendly CSV into the output folder and return its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def add_common_arguments(parser):
    parser.add_argument("folder", help="music folder (or a single file)")
    parser.add_argument("--apply", action="store_true",
                        help="really write the changes (without it, everything is a preview)")
    parser.add_argument("--yes", action="store_true",
                        help="with --apply: don't ask for confirmation")
    parser.add_argument("--out-dir", default=None, metavar="FOLDER",
                        help="where to save the CSV reports and comparison images "
                             f"(default: a '{REPORTS_DIRNAME}' folder created inside the music folder)")


def default_out_dir(folder):
    """'<music folder>/_reports' (next to the file if a single file was given)."""
    folder = Path(folder)
    return (folder.parent if folder.is_file() else folder) / REPORTS_DIRNAME
