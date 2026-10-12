# SPDX-License-Identifier: GPL-3.0-or-later
"""The 'covers' tool: checks the covers embedded in the files and fills the gaps.

For each album (and for each disc, if the album has more than one):
  - tracks with no cover, or with a damaged cover / one in a format Windows can't read
    (not a real JPEG/PNG): get the good cover from the other tracks;
  - if no track has a good cover, it looks for an image in the folder
    (cover.jpg, folder.jpg, front.jpg, album.jpg...);
  - if nothing is found, the album is listed (cover to be found by hand);
  - tracks with a VALID cover that is DIFFERENT from the most common one on the disc are
    listed (covers_different.csv); with --unify they all become the same.
To force ONE cover onto some tracks by hand: --set-cover IMAGE with --from/--to/--disc.
To see what's inside the files: --inspect.
"""

import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError

from .common import add_common_arguments, find_audio_files, first, first_number, safe_name, write_csv

FOLDER_NAMES = ["cover", "folder", "front", "album", "albumart", "albumartsmall"]
IMG_EXTS = (".jpg", ".jpeg", ".png")
MIN_BYTES = 100          # below this size an image is certainly broken


def add_arguments(parser):
    add_common_arguments(parser)
    parser.add_argument("--unify", action="store_true",
                        help="make valid but different covers on the same disc identical")
    parser.add_argument("--export", action="store_true",
                        help="save the main cover and the different ones of each album in "
                             "<out-dir>/cover_compare, to compare them by eye")
    parser.add_argument("--inspect", action="store_true",
                        help="changes nothing: shows what's inside each file "
                             "(use it on ONE album folder)")
    parser.add_argument("--set-cover", metavar="IMAGE",
                        help="put THIS image (jpg/png) on the tracks chosen with "
                             "--from/--to/--disc. Use it on ONE album folder")
    parser.add_argument("--from", dest="from_track", type=int, metavar="N",
                        help="with --set-cover: from track number N (inclusive)")
    parser.add_argument("--to", dest="to_track", type=int, metavar="N",
                        help="with --set-cover: up to track number N (inclusive)")
    parser.add_argument("--disc", type=int, metavar="N",
                        help="with --set-cover: only the tracks on disc N")


# ------------------------------------------------------------------- images ---

def image_format(data):
    """Recognizes the format by looking at the first bytes."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    return "unknown"


def mime_for(data):
    return "image/png" if image_format(data) == "png" else "image/jpeg"


def is_valid(pic):
    """A cover is good if it is a real JPEG or PNG (the formats Windows always reads)."""
    data = pic[2]
    return len(data) >= MIN_BYTES and image_format(data) in ("jpeg", "png")


def sha(pic):
    return hashlib.sha1(pic[2]).hexdigest()


def rep_picture(pics):
    """The 'representative' cover of a track: the front one, otherwise the first."""
    return ([p for p in pics if p[0] == 3] or pics)[0]


def best_picture(pictures):
    """Picks the most common cover (on a tie, the largest)."""
    fronts = [p for p in pictures if p[0] == 3] or pictures
    counts = Counter(sha(p) for p in fronts)
    by_hash = {sha(p): p for p in fronts}
    top = max(counts, key=lambda h: (counts[h], len(by_hash[h][2])))
    return by_hash[top]


# ------------------------------------------------------- reading / writing ---

def get_pictures(path):
    """Returns the list of (type, mime, data) of the embedded covers."""
    if path.suffix.lower() == ".mp3":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            return []
        return [(int(f.type), f.mime, f.data) for f in tags.getall("APIC")]
    return [(int(p.type), p.mime, p.data) for p in FLAC(path).pictures]


def set_picture(path, data):
    """Replaces ALL embedded covers with the given one (front cover)."""
    mime = mime_for(data)
    if path.suffix.lower() == ".mp3":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("APIC")
        tags.add(APIC(encoding=0, mime=mime, type=3, desc="Cover", data=data))
        tags.save(path, v2_version=3)      # ID3v2.3: the most compatible
    else:
        flac = FLAC(path)
        flac.clear_pictures()
        pic = Picture()
        pic.type, pic.mime, pic.desc, pic.data = 3, mime, "Cover", data
        flac.add_picture(pic)
        flac.save()


def track_info(path):
    """Returns ((album artist, album), disc number, track number)."""
    audio = mutagen.File(path, easy=True)
    album = first(audio, "album")
    disc = first_number(first(audio, "discnumber")) or 1
    num = first_number(first(audio, "tracknumber"))
    if not album:
        return (str(path.parent), "(no album)"), disc, num
    return (first(audio, "albumartist") or first(audio, "artist"), album), disc, num


def folder_image(folders):
    """Looks for cover.jpg / folder.jpg etc. (valid ones) in the tracks' folders."""
    for folder in folders:
        for name in FOLDER_NAMES:
            for ext in IMG_EXTS:
                for candidate in (folder / (name + ext), folder / (name.capitalize() + ext)):
                    if candidate.is_file():
                        data = candidate.read_bytes()
                        if is_valid((3, "", data)):
                            return candidate, data
    return None


def export_covers(base, artist, album, main, others):
    """Saves the main cover and the different ones in one folder per album."""
    folder = Path(base) / safe_name(artist + " - " + album)
    folder.mkdir(parents=True, exist_ok=True)
    mime, data, count = main
    ext = ".png" if "png" in mime else ".jpg"
    (folder / f"0_main_{count}tracks{ext}").write_bytes(data)
    for i, (mime, data, count) in enumerate(others, 1):
        ext = ".png" if "png" in mime else ".jpg"
        (folder / f"{i}_different_{count}tracks{ext}").write_bytes(data)


# ------------------------------------------------------------------ inspection ---

def inspect(files):
    """Prints, for each file, what is really inside (why isn't a cover showing?)."""
    for path in files:
        version = ""
        if path.suffix.lower() == ".mp3":
            try:
                version = "ID3v2." + str(ID3(path).version[1])
            except ID3NoHeaderError:
                version = "no ID3v2 tag"
        try:
            pics = get_pictures(path)
        except Exception as exc:
            print(f"{path.name} | ERROR: {exc}")
            continue
        if not pics:
            print(f"{path.name} | {version} | NO embedded cover")
            continue
        for i, pic in enumerate(pics, 1):
            state = "ok" if is_valid(pic) else "NOT VALID (Windows won't show it)"
            print(f"{path.name} | {version} | cover {i}/{len(pics)}: type {pic[0]}, "
                  f"mime '{pic[1]}', {len(pic[2])} bytes, format {image_format(pic[2])} -> {state}")


# -------------------------------------------------------- manually chosen cover ---

def set_cover_manual(files, args):
    """Puts ONE image chosen by you on the selected tracks (by track number or disc)."""
    img = Path(args.set_cover)
    if not img.is_file():
        raise SystemExit(f"Image not found: {img}")
    data = img.read_bytes()
    if not is_valid((3, "", data)):
        raise SystemExit("The image isn't a valid JPEG or PNG (or it's too small).")

    selected = []
    for path in files:
        try:
            _key, disc, num = track_info(path)
        except Exception as exc:
            print(f"  [read error] {path}: {exc}")
            continue
        if args.from_track is not None and num < args.from_track:
            continue
        if args.to_track is not None and num > args.to_track:
            continue
        if args.disc is not None and disc != args.disc:
            continue
        selected.append((disc, num, path))
    selected.sort(key=lambda t: (t[0], t[1], str(t[2])))

    if args.from_track is None and args.to_track is None and args.disc is None:
        print("WARNING: no filter (--from / --to / --disc): the cover will go on ALL "
              "the tracks in the folder.")
    if not selected:
        print("No track matches the given filters.")
        return

    print(f"Cover to apply: {img.name} ({len(data) // 1024} KB)")
    print(f"Selected tracks: {len(selected)}")
    for disc, num, path in selected:
        print(f"  track {num:>3}  (disc {disc})  {path.name}")

    if not args.apply:
        print("\nPREVIEW: nothing was written. If the list is right, "
              "run again adding --apply")
        return
    done = 0
    for _disc, _num, path in selected:
        try:
            set_picture(path, data)
            done += 1
        except Exception as exc:
            print(f"  [write error] {path}: {exc}")
    print(f"\nDone: cover written to {done} tracks.")


# ----------------------------------------------------------------------- run ---

def run(args):
    files = find_audio_files(args.folder)

    if args.inspect:
        inspect(files)
        return
    if args.set_cover:
        set_cover_manual(files, args)
        return

    print(f"Found {len(files)} files. Reading covers...")
    albums = defaultdict(list)
    for path in files:
        try:
            key, disc, _num = track_info(path)
            albums[key].append((path, get_pictures(path), disc))
        except Exception as exc:
            print(f"  [read error] {path}: {exc}")

    log = []
    no_cover_albums = []
    diverse_albums = []
    diverse_rows = []
    stats = Counter()
    export_base = Path(args.out_dir) / "cover_compare"

    for (artist, album_name), album_tracks in sorted(albums.items()):
        # The discs of one album may have different covers: each disc is compared with
        # its own tracks. Only if a disc has NO cover at all is the other discs' one used.
        discs = defaultdict(list)
        for p, pics, disc in album_tracks:
            discs[disc].append((p, pics))
        album_good = [rep_picture(pics) for _, pics, _ in album_tracks
                      if pics and is_valid(rep_picture(pics))]

        for disc, tracks in sorted(discs.items()):
            album = album_name if len(discs) == 1 else f"{album_name} [disc {disc}]"
            ok, broken, missing = [], [], []
            for p, pics in tracks:
                if not pics:
                    missing.append(p)
                elif is_valid(rep_picture(pics)):
                    ok.append((p, pics))
                else:
                    broken.append((p, pics))
            without = missing + [p for p, _ in broken]

            # --- where do I get the good cover from?
            if ok:
                data = best_picture([rep_picture(pics) for _, pics in ok])[2]
                origin = ("other tracks of the album" if len(discs) == 1
                          else "other tracks on the same disc")
            elif album_good:
                data = best_picture(album_good)[2]
                origin = "other discs of the album"
            else:
                found = folder_image({p.parent for p in without}) if without else None
                if not found:
                    if without:
                        no_cover_albums.append((artist, album, len(without), len(broken)))
                        stats["tracks without a good cover (no source)"] += len(without)
                    continue
                img, data = found
                origin = "file " + img.name
            mime = mime_for(data)
            best_hash = hashlib.sha1(data).hexdigest()

            # --- what to fix
            targets = [(p, "added", "no cover") for p in missing]
            for p, pics in broken:
                pic = rep_picture(pics)
                targets.append((p, "repaired", "invalid cover: format "
                                + image_format(pic[2]) + ", " + str(len(pic[2])) + " bytes"))
            diff_tracks = [(p, pics) for p, pics in ok if sha(rep_picture(pics)) != best_hash]
            if args.unify:
                targets += [(p, "replaced", "cover different from the most common one")
                            for p, _ in diff_tracks]

            # --- valid but different covers: list + export
            if diff_tracks:
                hash_count = Counter(sha(rep_picture(pics)) for _, pics in ok)
                diverse_albums.append((artist, album, len(diff_tracks), len(tracks)))
                unique_others = {}
                for p, pics in diff_tracks:
                    pic = rep_picture(pics)
                    h = sha(pic)
                    unique_others[h] = (mime_for(pic[2]), pic[2], hash_count[h])
                    diverse_rows.append([str(p), artist, album, len(pic[2]) // 1024,
                                         len(data) // 1024, hash_count[best_hash],
                                         hash_count[h]])
                if args.export:
                    export_covers(export_base, artist, album,
                                  (mime, data, hash_count[best_hash]),
                                  list(unique_others.values()))
                if not args.unify:
                    stats["tracks with a valid but different cover (use --unify)"] += len(diff_tracks)

            if targets:
                extra = f", of which {len(broken)} with a damaged cover" if broken else ""
                print(f"  {artist} - {album}: {len(targets)} tracks to fix{extra} "
                      f"(source: {origin})")
            for path, action, problem in targets:
                if args.apply:
                    try:
                        set_picture(path, data)
                    except Exception as exc:
                        print(f"    [write error] {path}: {exc}")
                        continue
                stats["cover " + action] += 1
                log.append([str(path), artist, album, action, origin, problem])

    print("\n=== ALBUMS WITH NO GOOD COVER (to find by hand) ===")
    if no_cover_albums:
        for artist, album, n, n_broken in no_cover_albums:
            extra = f", {n_broken} with a damaged cover" if n_broken else ""
            print(f"  {artist} - {album} ({n} tracks{extra})")
        print("  Tip: save the image as cover.jpg in the album folder "
              "and run again: it will be used for all the tracks.")
    else:
        print("  none")

    print("\n=== ALBUMS WITH VALID BUT DIFFERENT COVERS ACROSS TRACKS ===")
    if diverse_albums:
        for artist, album, n_diff, n_tot in diverse_albums:
            print(f"  {artist} - {album}: {n_diff} tracks out of {n_tot} with a cover different "
                  f"from the most common one")
        if args.export:
            print(f"  Images to compare in folder: {export_base.resolve()}")
        else:
            print("  To see the images run again with --export")
    else:
        print("  none")
    diff_path = write_csv(args.out_dir, "covers_different.csv",
                          ["file", "album artist", "album", "this track's cover (KB)",
                           "main cover (KB)", "tracks with the main cover",
                           "tracks with this cover"], diverse_rows)
    print(f"  Track-by-track list in file: {diff_path}")

    log_name = "covers_applied.csv" if args.apply else "covers_preview.csv"
    log_path = write_csv(args.out_dir, log_name,
                         ["file", "album artist", "album", "action", "source", "problem"], log)

    print("\n=== SUMMARY ===")
    print(f"Albums checked: {len(albums)}")
    for label, n in stats.items():
        suffix = "" if args.apply or not label.startswith("cover") else " (preview, not written)"
        print(f"  {label}: {n}{suffix}")
    if not stats:
        print("  all covers are already fine")
    print(f"Details in file: {log_path}")
    if not args.apply:
        print("If the preview looks right, run again adding --apply")
