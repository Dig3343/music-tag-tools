# SPDX-License-Identifier: GPL-3.0-or-later
"""The 'tags' tool: tidies up artist, album artist, album titles and duplicates.

For each album (= files in the same folder with the same album title) the tool:
  1. unifies album titles written in slightly different ways ("Album: X" / "Album X");
  2. applies YOUR rules, if you pass a file with --rules (see rules.example.json);
  3. for albums with no matching rule, decides on its own (unless --no-auto):
       - album by one main artist: artist and "album artist" are the same on every track,
         guests (feat.) go into the title;
       - compilation (many different artists): "Various Artists", compilation flag, and
         the original artist in parentheses in the title;
  4. reports exact duplicates (and moves them with --move-dupes).
Everything starts as a preview: files only change with --apply.
"""

import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import mutagen

from .common import (DUPES_DIRNAME, add_common_arguments, find_audio_files, first,
                     first_number, key_text, norm, write_csv)

FIELDS = ("artist", "albumartist", "album", "title", "discnumber", "compilation")
RULE_SET_KEYS = {"artist", "albumartist", "album", "discnumber"}
VARIOUS = "Various Artists"
MIN_COMPILATION_TRACKS = 3     # below this many tracks it won't decide on its own
FEAT_RE = re.compile(r"\b(?:feat|ft|featuring)\b\.?", re.IGNORECASE)


# ------------------------------------------------------------------ arguments ---

def add_arguments(parser):
    add_common_arguments(parser)
    parser.add_argument("--rules", metavar="FILE.json",
                        help="file with your per-album rules (see rules.example.json)")
    parser.add_argument("--no-auto", action="store_true",
                        help="no automatic decisions: only rules and unified album titles")
    parser.add_argument("--main-artist-ratio", type=float, default=0.6, metavar="0-1",
                        help="share of tracks with the same artist needed to treat the album "
                             "as 'by one artist' (default 0.6); below that it's a compilation")
    parser.add_argument("--split-comma", action="store_true",
                        help="also treat comma and '&' as artist separators "
                             "(careful with names like 'Earth, Wind & Fire')")
    parser.add_argument("--no-feat-in-title", action="store_true",
                        help="don't move guest artists into the title")
    parser.add_argument("--keep-compilation-artists", action="store_true",
                        help="in compilations keep each track's artist "
                             "(only sets 'album artist' and the compilation flag)")
    parser.add_argument("--move-dupes", action="store_true",
                        help=f"with --apply: move exact duplicates to '{DUPES_DIRNAME}'")
    parser.add_argument("--verbose", action="store_true",
                        help="print the decision made for each album")


# ---------------------------------------------------------------------- rules ---

def load_rules(path):
    """Reads the JSON rules file and validates it."""
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read the rules file '{path}': {exc}")
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise SystemExit("The rules file must contain a 'rules' list.")

    parsed = []
    for number, rule in enumerate(rules, 1):
        if not isinstance(rule, dict) or "album_regex" not in rule:
            raise SystemExit(f"Rule #{number}: missing 'album_regex'.")
        values = rule.get("set", {})
        unknown = set(values) - RULE_SET_KEYS
        if unknown:
            allowed = ", ".join(sorted(RULE_SET_KEYS))
            raise SystemExit(f"Rule #{number}: invalid fields in 'set': "
                             f"{', '.join(sorted(unknown))} (allowed: {allowed}).")
        try:
            rx = re.compile(rule["album_regex"], re.IGNORECASE)
        except re.error as exc:
            raise SystemExit(f"Rule #{number}: invalid 'album_regex': {exc}")
        parsed.append({
            "rx": rx,
            "text": rule["album_regex"],
            "set": {key: str(value) for key, value in values.items()},
            "compilation": bool(rule.get("compilation", False)),
            "artist_in_title": bool(rule.get("artist_in_title", False)),
        })
    return parsed


# ------------------------------------------------------------------- artists ---

def split_artists(text, split_comma=False):
    """Splits 'A/B', 'A; B', 'A feat. B' into a list of names."""
    if split_comma:
        pattern = r"\s*(?:/|;|,|&|\b(?:feat|ft|featuring)\b\.?)\s*"
    else:
        pattern = r"\s*(?:/|;|\b(?:feat|ft|featuring)\b\.?)\s*"
    parts = re.split(pattern, text or "", flags=re.IGNORECASE)
    return [p.strip(" ()[]") for p in parts if p and p.strip(" ()[]")]


def extra_artists(artist, main, split_comma):
    """The artists on a track besides the main one (the 'guests')."""
    parts = split_artists(artist, split_comma)
    if parts and parts[0].lower() == main.lower():
        return parts[1:]
    if (artist.lower().startswith(main.lower()) and len(artist) > len(main)
            and not artist[len(main)].isalnum()):
        rest = re.sub(r"^[\s,&/;+]+", "", artist[len(main):])
        rest = re.sub(r"^(?:and|e|x|with|con)\s+", "", rest, flags=re.IGNORECASE)
        return split_artists(rest, split_comma)
    return parts


# ------------------------------------------------------------------- records ---

def read_records(files):
    """Reads the tags of all files and prepares the 'old' and 'new' values."""
    records = []
    for path in files:
        try:
            audio = mutagen.File(path, easy=True)
        except Exception as exc:
            print(f"  [read error] {path}: {exc}")
            continue
        if audio is None:
            print(f"  [skip] unrecognized format: {path}")
            continue
        old = {key: first(audio, key) for key in FIELDS}
        records.append({
            "path": path,
            "old": old,
            "new": dict(old),
            "why": [],
            "track": first_number(first(audio, "tracknumber")),
            "size": path.stat().st_size,
        })
    return records


def note(record, text):
    if text not in record["why"]:
        record["why"].append(text)


def unify_album_titles(records):
    """In the same folder, album titles that differ only in punctuation -> a single one."""
    groups = defaultdict(list)
    for rec in records:
        key = key_text(rec["old"]["album"])
        if key:
            groups[(rec["path"].parent, key)].append(rec)
    for items in groups.values():
        spellings = Counter(rec["old"]["album"] for rec in items)
        if len(spellings) > 1:
            chosen = max(spellings, key=lambda s: (spellings[s], len(s)))
            for rec in items:
                if rec["new"]["album"] != chosen:
                    rec["new"]["album"] = chosen
                    note(rec, "album title unified")


def apply_rule(items, rule):
    for rec in items:
        old, new = rec["old"], rec["new"]
        for field, value in rule["set"].items():
            new[field] = value
        if "albumartist" not in rule["set"] and new["artist"]:
            new["albumartist"] = new["artist"]
        if rule["compilation"]:
            new["compilation"] = "1"
        if (rule["artist_in_title"] and old["artist"] and old["artist"] != new["artist"]
                and old["artist"] not in old["title"]):
            new["title"] = old["title"] + " (" + old["artist"] + ")"
        note(rec, "rule: " + rule["text"])


def apply_auto(items, opts):
    """Decides on its own whether the album is 'by one artist' or a compilation. Returns (description, warning)."""
    albumartists = {rec["old"]["albumartist"] for rec in items}
    mode = None
    main = ""
    detail = ""

    only = next(iter(albumartists)) if len(albumartists) == 1 else ""
    if only:
        if only.lower() == VARIOUS.lower():
            mode, detail = "compilation", "album artist is already 'Various Artists'"
        else:
            mode, main, detail = "album", only, "album artist already set: " + only
    else:
        counts = Counter()
        spellings = {}
        for rec in items:
            parts = split_artists(rec["old"]["artist"], opts.split_comma)
            if parts:
                key = parts[0].lower()
                counts[key] += 1
                spellings.setdefault(key, Counter())[parts[0]] += 1
        total = sum(counts.values())
        if total:
            top_key, top_n = counts.most_common(1)[0]
            if top_n / total >= opts.main_artist_ratio:
                main = spellings[top_key].most_common(1)[0][0]
                mode = "album"
                detail = f"main artist {main} ({top_n} tracks out of {total})"
            elif len(items) >= MIN_COMPILATION_TRACKS:
                mode = "compilation"
                detail = f"{len(counts)} different artists: compilation"
            else:
                return "", (f"album with different artists but only {len(items)} tracks: "
                            f"check by hand ({items[0]['new']['album']})")

    if mode == "album":
        for rec in items:
            old, new = rec["old"], rec["new"]
            extra = extra_artists(old["artist"], main, opts.split_comma)
            new["artist"] = main
            new["albumartist"] = main
            if extra and not opts.no_feat_in_title and not FEAT_RE.search(old["title"]):
                new["title"] = old["title"] + " (feat. " + ", ".join(extra) + ")"
            note(rec, "automatic: " + detail)
    elif mode == "compilation":
        for rec in items:
            old, new = rec["old"], rec["new"]
            new["albumartist"] = VARIOUS
            new["compilation"] = "1"
            if not opts.keep_compilation_artists:
                new["artist"] = VARIOUS
                if (old["artist"] and old["artist"].lower() != VARIOUS.lower()
                        and old["artist"] not in old["title"]):
                    new["title"] = old["title"] + " (" + old["artist"] + ")"
            note(rec, "automatic: " + detail)
    return detail, ""


def write_changes(path, changes):
    audio = mutagen.File(path, easy=True)
    if audio.tags is None:
        audio.add_tags()
    for field, value in changes.items():
        audio[field] = [value]
    if path.suffix.lower() == ".mp3":
        audio.save(v2_version=3)       # ID3v2.3: the most compatible with Windows and players
    else:
        audio.save()


def unique_destination(dest):
    if not dest.exists():
        return dest
    n = 2
    while True:
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# ----------------------------------------------------------------------- run ---

def run(args):
    root = Path(args.folder)
    files = find_audio_files(root)
    print(f"Found {len(files)} files.")
    rules = load_rules(args.rules)
    records = read_records(files)
    unify_album_titles(records)

    groups = defaultdict(list)
    for rec in records:
        groups[(rec["path"].parent, key_text(rec["new"]["album"]))].append(rec)

    warnings = []
    for (_parent, _key), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        album = items[0]["new"]["album"]
        if not album:
            continue                      # files with no album title: leave them alone
        rule = next((r for r in rules if r["rx"].search(norm(album))), None)
        decision = ""
        if rule:
            apply_rule(items, rule)
            decision = "rule: " + rule["text"]
        elif not args.no_auto:
            decision, warning = apply_auto(items, args)
            if warning:
                warnings.append(warning)
        else:
            for rec in items:
                rec["new"]["albumartist"] = rec["old"]["albumartist"] or rec["old"]["artist"]
        if args.verbose and decision:
            print(f"  {album}: {decision}")

    # --- differences and writing
    log_rows = []
    changed = 0
    for rec in records:
        changes = {f: v for f, v in rec["new"].items() if v and v != rec["old"][f]}
        if not changes:
            continue
        changed += 1
        reason = "; ".join(rec["why"])
        for field, value in changes.items():
            log_rows.append([str(rec["path"]), field, rec["old"][field], value, reason])
        if args.apply:
            try:
                write_changes(rec["path"], changes)
            except Exception as exc:
                print(f"  [write error] {rec['path']}: {exc}")

    # --- duplicates
    exact = defaultdict(list)
    loose = defaultdict(list)
    for rec in records:
        new = rec["new"]
        who = key_text(new["albumartist"] or new["artist"])
        album_id = norm(new["album"]) or str(rec["path"].parent)
        disc = first_number(new["discnumber"]) or 1
        title = key_text(rec["old"]["title"])
        exact[(who, album_id, disc, rec["track"], title)].append(rec)
        loose[(who, album_id, title)].append(rec)

    print("\n=== EXACT DUPLICATES (same album, disc, track and title) ===")
    moved = 0
    exact_groups = [g for g in exact.values() if len(g) > 1]
    for group in exact_groups:
        group.sort(key=lambda r: (-r["size"], str(r["path"])))
        print(f"  keeping: {group[0]['path']}")
        for extra in group[1:]:
            print(f"    duplicate: {extra['path']}")
            if args.apply and args.move_dupes and root.is_dir():
                dest = unique_destination(root / DUPES_DIRNAME / extra["path"].relative_to(root))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(extra["path"]), str(dest))
                moved += 1
    if not exact_groups:
        print("  none")

    exact_paths = {r["path"] for g in exact_groups for r in g}
    print("\n=== POSSIBLE DUPLICATES (same title, different track number) ===")
    print("    (they may be different versions: check by hand)")
    found = False
    for (_who, album_id, title), items in loose.items():
        tracks = {r["track"] for r in items}
        if len(items) > 1 and len(tracks) > 1 and not {r["path"] for r in items} <= exact_paths:
            found = True
            print(f"  {album_id} / {title}: tracks {sorted(tracks)}")
    if not found:
        print("  none")

    if warnings:
        print("\n=== CHECK BY HAND ===")
        for text in sorted(set(warnings)):
            print("  -", text)

    log_name = "tags_applied.csv" if args.apply else "tags_preview.csv"
    log_path = write_csv(args.out_dir, log_name,
                         ["file", "field", "before", "after", "reason"], log_rows)

    state = "MODIFIED" if args.apply else "TO MODIFY (preview, nothing was written)"
    print(f"\nFiles {state}: {changed} of {len(records)}")
    if args.apply and args.move_dupes:
        print(f"Duplicates moved to {DUPES_DIRNAME}: {moved}")
    print(f"Details in file: {log_path}")
    if not args.apply:
        print("If the preview looks right, run again adding --apply")
