# SPDX-License-Identifier: GPL-3.0-or-later
"""'id3v23' command: convert mp3 tags to ID3v2.3.

Why: Windows Explorer and Windows Media Player often do NOT show the cover art when a file
carries an ID3v2.4 tag. ID3v2.3 is read correctly by Windows and by most portable players.
Contents (title, artist, cover...) do not change; files already in v2.3 are left untouched.
"""

from collections import Counter

from mutagen.id3 import ID3, ID3NoHeaderError

from .common import add_common_arguments, find_audio_files, write_csv


def add_arguments(parser):
    add_common_arguments(parser)


def run(args):
    files = [p for p in find_audio_files(args.folder) if p.suffix.lower() == ".mp3"]
    print(f"Found {len(files)} mp3 files.")

    stats = Counter()
    rows = []
    for path in files:
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            stats["no ID3v2 tag (skipped)"] += 1
            continue
        except Exception as exc:
            print(f"  [read error] {path}: {exc}")
            stats["read errors"] += 1
            continue

        minor = tags.version[1]
        if minor == 3:
            stats["already ID3v2.3"] += 1
            continue
        stats[f"ID3v2.{minor} (to convert)"] += 1
        if args.apply:
            try:
                tags.save(path, v2_version=3)
            except Exception as exc:
                print(f"  [write error] {path}: {exc}")
                stats["write errors"] += 1
                continue
            stats["converted"] += 1
        rows.append([str(path), f"ID3v2.{minor}", "ID3v2.3"])

    name = "id3v23_applied.csv" if args.apply else "id3v23_preview.csv"
    log = write_csv(args.out_dir, name, ["file", "version before", "version after"], rows)

    print("\n=== SUMMARY ===")
    for label, n in stats.items():
        print(f"  {label}: {n}")
    print(f"List saved to: {log}")
    if not args.apply:
        print("If it looks right, run again adding --apply")
    else:
        print("Done. Close and reopen the folder in Explorer to see the covers.")
