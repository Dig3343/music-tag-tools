"""'online' command: fill in missing metadata, cover art and lyrics from free online services.

  * metadata  - MusicBrainz (https://musicbrainz.org, open data): release date, genre, track and
                disc numbers, missing titles/artists, MusicBrainz IDs.
  * covers    - Cover Art Archive (https://coverartarchive.org): only for albums in which NO
                track has a usable embedded cover.
  * identify  - with --fingerprint the audio itself is fingerprinted (Chromaprint "fpcalc") and
                identified through AcoustID, instead of trusting the tags. Used to pick the right
                release, to pair each file with the right track, and to flag tracks whose tags
                disagree with the audio.
  * lyrics    - LRCLIB (https://lrclib.net, community database, no account needed): plain
                lyrics are embedded in the file; with --lrc synced lyrics are also saved as a
                .lrc file next to the track.

Only the standard library is used for the network access (no extra dependency).
By default nothing existing is overwritten: only EMPTY fields are filled (see --overwrite).
Like every command it is a preview until you add --apply; the preview does contact the
services (it has to, to know what it would change) but never touches your files.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import mutagen
from mutagen.id3 import ID3, ID3NoHeaderError, USLT

from . import __version__
from . import covers as cv
from .common import add_common_arguments, find_audio_files, first, first_number, key_text, write_csv
from .tags import VARIOUS, split_artists, write_changes

MB_API = "https://musicbrainz.org/ws/2"
CAA_API = "https://coverartarchive.org"
LRCLIB_API = "https://lrclib.net/api"
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
MIN_FINGERPRINT_SCORE = 0.8     # AcoustID score (0-1) needed to trust an identification

MIN_RELEASE_SCORE = 80          # MusicBrainz search score (0-100) needed to consider a release
MIN_TITLE_SIMILARITY = 0.85     # album title similarity needed to accept a release
MIN_TRACK_SIMILARITY = 0.5      # title similarity needed to match a track by position
MAX_DURATION_DIFF = 3           # seconds of tolerance for lyrics matches

DISC_SUFFIX_RE = re.compile(r"\s*[\(\[]\s*(?:disc|disk|cd)\s*\d+\s*[\)\]]\s*$", re.IGNORECASE)
FEAT_SUFFIX_RE = re.compile(r"\s*[\(\[]\s*(?:feat|ft|featuring)\b.*?[\)\]]\s*$", re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)+", re.MULTILINE)


class OfflineError(Exception):
    """Raised when the services can't be reached several times in a row."""


class FingerprintError(Exception):
    """Raised when fingerprinting can't continue (no fpcalc, bad API key...)."""


# ------------------------------------------------------------------- arguments ---

def add_arguments(parser):
    add_common_arguments(parser)
    parser.add_argument("--metadata", action="store_true",
                        help="fill missing metadata from MusicBrainz")
    parser.add_argument("--covers", action="store_true",
                        help="download covers (Cover Art Archive) for albums that have none")
    parser.add_argument("--lyrics", action="store_true",
                        help="fetch lyrics (LRCLIB) and embed them in the files")
    parser.add_argument("--lrc", action="store_true",
                        help="with --lyrics: also save synced lyrics as a .lrc file next to the track")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace existing values too (title, date, genre, numbers, lyrics). "
                             "Artist and album artist are never overwritten")
    parser.add_argument("--cover-size", type=int, choices=(250, 500, 1200), default=500,
                        metavar="PX", help="cover size to download: 250, 500 or 1200 (default 500)")
    parser.add_argument("--match", choices=("tags", "audio", "both"), default=None,
                        help="how to identify the tracks: 'tags' (default: title/artist/album tags), "
                             "'audio' (audio fingerprint via AcoustID only, the safest) or 'both' "
                             "(fingerprint first, tags as fallback). 'audio' and 'both' need fpcalc "
                             "and an AcoustID API key")
    parser.add_argument("--fingerprint", action="store_true", help=argparse.SUPPRESS)   # = --match both
    parser.add_argument("--acoustid-key", metavar="KEY", default=os.environ.get("ACOUSTID_API_KEY", ""),
                        help="your free AcoustID application key (or set ACOUSTID_API_KEY)")
    parser.add_argument("--fpcalc", metavar="PATH",
                        help="path to the Chromaprint 'fpcalc' program (default: found in PATH)")
    parser.add_argument("--contact", metavar="EMAIL_OR_URL",
                        default=os.environ.get("MUSICTOOLS_CONTACT", ""),
                        help="your contact info, sent in the User-Agent as MusicBrainz asks "
                             "(or set the MUSICTOOLS_CONTACT environment variable)")
    parser.add_argument("--no-cache", action="store_true",
                        help="don't reuse answers saved in <out-dir>/online_cache")
    parser.add_argument("--verbose", action="store_true", help="print every decision")


# ------------------------------------------------------------------------ HTTP ---

class Http:
    """Tiny polite HTTP client: User-Agent, rate limit, retries and an on-disk cache."""

    MIN_INTERVAL = {"musicbrainz.org": 1.1, "api.acoustid.org": 0.34}     # seconds between requests to the same host
    DEFAULT_INTERVAL = 0.2
    MAX_FAILURES = 3

    def __init__(self, user_agent, cache_dir=None, timeout=20, opener=None, sleep=time.sleep):
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.last_request = {}
        self.failures = 0
        self.error_counts = Counter()      # HTTP status -> how many answers had it

    # -- cache
    def _cache_path(self, url):
        if not self.cache_dir:
            return None
        return self.cache_dir / hashlib.sha1(url.encode("utf-8")).hexdigest()

    def _wait(self, host):
        interval = self.MIN_INTERVAL.get(host, self.DEFAULT_INTERVAL)
        elapsed = time.monotonic() - self.last_request.get(host, 0)
        if elapsed < interval:
            self.sleep(interval - elapsed)
        self.last_request[host] = time.monotonic()

    def fetch(self, url, data=None, cache_key=None):
        """Return the body (bytes) or None if not found. Raises OfflineError if unreachable.
        With 'data' the request is a POST; 'cache_key' replaces the URL as the cache key."""
        cache = self._cache_path(cache_key or url)
        if cache is not None:
            if cache.with_suffix(".404").exists():
                return None
            if cache.exists():
                return cache.read_bytes()

        host = urllib.parse.urlparse(url).netloc
        for attempt in range(1, 4):
            self._wait(host)
            request = urllib.request.Request(url, data=data, headers={"User-Agent": self.user_agent})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                self.failures = 0
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(body)
                return body
            except urllib.error.HTTPError as exc:
                self.failures = 0
                if exc.code == 404:
                    if cache is not None:
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        cache.with_suffix(".404").write_bytes(b"")
                    return None
                if exc.code in (429, 502, 503, 504) and attempt < 3:
                    retry = exc.headers.get("Retry-After") if exc.headers else None
                    self.sleep(float(retry) if retry and retry.isdigit() else 2.0 * attempt)
                    continue
                self.error_counts[exc.code] += 1
                return None
            except (urllib.error.URLError, OSError, ValueError):
                if attempt < 3:
                    self.sleep(1.0 * attempt)
                    continue
                self.failures += 1
                if self.failures >= self.MAX_FAILURES:
                    raise OfflineError("can't reach the online services (are you connected?)")
                return None
        return None

    def get_json(self, url):
        body = self.fetch(url)
        if body is None:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return None

    def get_bytes(self, url):
        return self.fetch(url)

    def post_json(self, url, fields, cache_key):
        body = self.fetch(url, data=urllib.parse.urlencode(fields).encode("utf-8"),
                          cache_key=url + "|" + cache_key)
        if body is None:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return None


def make_http(args):
    contact = f" ( {args.contact} )" if args.contact else ""
    user_agent = f"musictools/{__version__}{contact}"
    cache_dir = None if args.no_cache else Path(args.out_dir) / "online_cache"
    return Http(user_agent, cache_dir)


# ------------------------------------------------------------------ MusicBrainz ---

def lucene_phrase(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def credit_text(credit):
    """'Artist A & Artist B' from a MusicBrainz artist-credit list."""
    return "".join((c.get("name") or c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
                   for c in credit or []).strip()


def similarity(a, b):
    a, b = key_text(a), key_text(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)):
        ratio = max(ratio, 0.9)
    return ratio


def find_release(http, artist, album, local_count, log=None):
    """Search MusicBrainz for the album. Returns the best search hit (dict) or None."""
    query = f"release:{lucene_phrase(album)}"
    is_various = not artist or artist.lower() == VARIOUS.lower()
    if not is_various:
        query += f" AND artist:{lucene_phrase(artist)}"
    url = f"{MB_API}/release/?query={urllib.parse.quote(query)}&fmt=json&limit=10"
    data = http.get_json(url)
    best, best_score = None, 0.0
    hits = (data or {}).get("releases", [])
    if log:
        top = hits[0] if hits else None
        log(f"search returned {len(hits)} results" + (
            f" (first: '{top.get('title')}' by '{credit_text(top.get('artist-credit'))}', score {top.get('score')})"
            if top else ""))
    def reject(hit, reason):
        if log:
            log(f"  skipped '{hit.get('title')}': {reason}")

    for hit in hits:
        score = int(hit.get("score", 0))
        if score < MIN_RELEASE_SCORE:
            reject(hit, f"search score {score} is too low")
            continue
        title_sim = similarity(hit.get("title", ""), album)
        if title_sim < MIN_TITLE_SIMILARITY:
            reject(hit, "title is too different")
            continue
        if not is_various and similarity(credit_text(hit.get("artist-credit")), artist) < 0.6:
            reject(hit, "artist is too different")
            continue
        count = hit.get("track-count") or 0
        if count and local_count > count:
            reject(hit, f"it has {count} tracks but you have {local_count}")
            continue                    # we have more tracks than this release: wrong edition
        value = (score / 100 + title_sim + (0.5 if count == local_count else 0)
                 + (1.0 if title_sim >= 0.999 else 0))      # an exact title beats a similar one
        if value > best_score:
            best, best_score = hit, value
    return best


def group_artist(items):
    """The artist of an album: the album artist, else the first artist shared by most tracks.
    Returns '' when there's no clear main artist (a compilation)."""
    named = Counter(t["tags"]["albumartist"] for t in items if t["tags"]["albumartist"])
    if named:
        return named.most_common(1)[0][0]
    firsts = Counter()
    for t in items:
        names = split_artists(t["tags"]["artist"], split_comma=True)
        if names:
            firsts[names[0]] += 1
    if firsts:
        name, count = firsts.most_common(1)[0]
        if count * 2 > len(items):
            return name
    return ""


def release_details(http, mbid):
    url = f"{MB_API}/release/{mbid}?inc=recordings+artist-credits+release-groups+genres&fmt=json"
    return http.get_json(url)


def release_tracks(release):
    """Flatten the media of a release into a list of track dicts."""
    tracks = []
    media = release.get("media", [])
    for medium in media:
        total = medium.get("track-count") or len(medium.get("tracks", []))
        for track in medium.get("tracks", []):
            recording = track.get("recording") or {}
            tracks.append({
                "disc": medium.get("position") or 1,
                "discs": len(media),
                "num": track.get("position") or first_number(track.get("number", "")),
                "total": total,
                "title": track.get("title") or recording.get("title", ""),
                "recording": recording.get("id", ""),
                "artist": credit_text(track.get("artist-credit") or recording.get("artist-credit")),
            })
    return tracks


def best_genre(release):
    genres = release.get("genres") or (release.get("release-group") or {}).get("genres") or []
    if not genres:
        return ""
    top = sorted(genres, key=lambda g: (-g.get("count", 0), g.get("name", "")))[0]
    return top.get("name", "").title()


def match_tracks(local, mb_tracks):
    """Pair local tracks with MusicBrainz tracks. Returns {local index: mb track}."""
    by_title = defaultdict(list)
    by_pos = {}
    for t in mb_tracks:
        by_title[key_text(t["title"])].append(t)
        by_pos[(t["disc"], t["num"])] = t
    used, result = set(), {}

    for i, item in enumerate(local):                       # pass 1: same title
        candidates = [t for t in by_title.get(key_text(item["title"]), []) if id(t) not in used]
        if not candidates:
            continue
        same_pos = [t for t in candidates if (t["disc"], t["num"]) == (item["disc"], item["num"])]
        chosen = (same_pos or candidates)[0]
        used.add(id(chosen))
        result[i] = chosen

    for i, item in enumerate(local):                       # pass 2: same position, similar title
        if i in result:
            continue
        t = by_pos.get((item["disc"], item["num"]))
        if t is None or id(t) in used:
            continue
        if not item["title"] or similarity(item["title"], t["title"]) >= MIN_TRACK_SIMILARITY:
            used.add(id(t))
            result[i] = t
    return result


def metadata_changes(item, mb_track, release, overwrite):
    """Return {field: new value} for one track (only what is missing, unless overwrite)."""
    wanted = {}
    group = release.get("release-group") or {}
    wanted["date"] = release.get("date", "")
    wanted["originaldate"] = group.get("first-release-date", "")
    wanted["genre"] = best_genre(release)
    wanted["musicbrainz_albumid"] = release.get("id", "")
    wanted["musicbrainz_releasegroupid"] = group.get("id", "")
    if mb_track:
        wanted["title"] = mb_track["title"]
        wanted["musicbrainz_trackid"] = mb_track["recording"]
        if mb_track["num"]:
            wanted["tracknumber"] = f'{mb_track["num"]}/{mb_track["total"]}'
        if mb_track["discs"] > 1:
            wanted["discnumber"] = f'{mb_track["disc"]}/{mb_track["discs"]}'
    changes = {}
    for field, value in wanted.items():
        if not value:
            continue
        current = item["tags"].get(field, "")
        if field in ("tracknumber", "discnumber"):
            if current and not overwrite:
                continue
            if current == value:
                continue
        elif current and not overwrite:
            continue
        elif current == value:
            continue
        changes[field] = value
    # artists are only ever filled in when empty
    if mb_track and mb_track["artist"] and not item["tags"].get("artist"):
        changes["artist"] = mb_track["artist"]
    album_artist = credit_text(release.get("artist-credit"))
    if album_artist and not item["tags"].get("albumartist"):
        changes["albumartist"] = album_artist
    return changes


# ---------------------------------------------------------------- fingerprints ---

def find_fpcalc(explicit):
    exe = explicit or shutil.which("fpcalc")
    if not exe or not (Path(exe).exists() or shutil.which(exe)):
        raise SystemExit(
            "Audio matching needs the Chromaprint 'fpcalc' program. Download it from "
            "https://acoustid.org/chromaprint, then either put it in your PATH or pass "
            "--fpcalc \"C:\\path\\to\\fpcalc.exe\".")
    return exe


def fingerprint_file(fpcalc, path):
    """Return (duration, fingerprint) for a file, or None if fpcalc can't read it."""
    try:
        done = subprocess.run([fpcalc, "-json", "-length", "120", str(path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        data = json.loads(done.stdout.decode("utf-8", "replace"))
        return int(data["duration"]), data["fingerprint"]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return None


def identify_recording(http, api_key, duration, fingerprint):
    """Ask AcoustID who this audio is. Returns a dict or None."""
    data = http.post_json(
        ACOUSTID_URL,
        {"client": api_key, "meta": "recordings+releaseids", "duration": str(duration),
         "fingerprint": fingerprint, "format": "json"},
        cache_key=f"{duration}:{fingerprint}")
    if data and data.get("status") == "error":
        message = (data.get("error") or {}).get("message", "unknown error")
        raise FingerprintError(f"AcoustID refused the request: {message}")
    best = None
    for result in (data or {}).get("results", []):
        score = result.get("score", 0)
        if score < MIN_FINGERPRINT_SCORE:
            continue
        for rec in result.get("recordings", []):
            if best is None or score > best["score"]:
                best = {"recording": rec.get("id", ""), "title": rec.get("title", ""),
                        "artist": credit_text(rec.get("artists")), "score": score,
                        "releases": [r.get("id") for r in rec.get("releases", []) if r.get("id")]}
    return best


def fingerprint_album(http, api_key, fpcalc, items):
    """Identify every track of an album. Returns {path: identification}."""
    found = {}
    for item in items:
        fp = fingerprint_file(fpcalc, item["path"])
        if fp is None:
            continue
        result = identify_recording(http, api_key, fp[0], fp[1])
        if result:
            found[item["path"]] = result
    return found


def total_tracks(release):
    return sum(m.get("track-count") or len(m.get("tracks", [])) for m in release.get("media", []))


def release_from_fingerprints(http, found, local_count):
    """The release that most identified tracks belong to (and that is big enough for the album)."""
    counts = Counter(rid for ident in found.values() for rid in set(ident["releases"]))
    needed = 2 if len(found) >= 2 else 1
    best, best_key = None, None
    for rid, n in counts.most_common(5):
        if n < needed:
            break
        details = release_details(http, rid)
        if not details or total_tracks(details) < local_count:
            continue
        key = (n, total_tracks(details) == local_count)
        if best is None or key > best_key:
            best, best_key = details, key
    return best


def pair_with_fingerprints(items, found, mb_tracks):
    """Pair tracks by recording id first (reliable), then by tags for the rest."""
    by_recording = {t["recording"]: t for t in mb_tracks if t["recording"]}
    pairs, used = {}, set()
    for index, item in enumerate(items):
        ident = found.get(item["path"])
        track = by_recording.get(ident["recording"]) if ident else None
        if track is not None and id(track) not in used:
            pairs[index] = track
            used.add(id(track))
    rest_items = [(i, it) for i, it in enumerate(items) if i not in pairs]
    rest_tracks = [t for t in mb_tracks if id(t) not in used]
    rest_pairs = match_tracks([it for _i, it in rest_items], rest_tracks)
    for position, track in rest_pairs.items():
        pairs[rest_items[position][0]] = track
    return pairs


# --------------------------------------------------------------------- covers ---

def fetch_cover(http, hit, size, release=None):
    """Download the front cover of a release (or of its release group)."""
    mbid = hit["id"]
    candidates = []
    if release is None or (release.get("cover-art-archive") or {}).get("front", True):
        candidates.append(f"{CAA_API}/release/{mbid}/front-{size}")
    group = (release or hit).get("release-group") or {}
    if group.get("id"):
        candidates.append(f"{CAA_API}/release-group/{group['id']}/front-{size}")
    for url in candidates:
        data = http.get_bytes(url)
        if data and cv.is_valid((3, cv.mime_for(data), data)):
            return data, url
    return None, ""


# --------------------------------------------------------------------- lyrics ---

def clean_title(title):
    return FEAT_SUFFIX_RE.sub("", title).strip() or title


def find_lyrics(http, artist, title, album, duration):
    """Return the LRCLIB record for a track, or None."""
    title = clean_title(title)
    if album and duration:
        query = urllib.parse.urlencode({"artist_name": artist, "track_name": title,
                                        "album_name": album, "duration": int(round(duration))})
        data = http.get_json(f"{LRCLIB_API}/get?{query}")
        if data and (data.get("plainLyrics") or data.get("syncedLyrics") or data.get("instrumental")):
            return data
    query = urllib.parse.urlencode({"artist_name": artist, "track_name": title})
    results = http.get_json(f"{LRCLIB_API}/search?{query}") or []
    best, best_value = None, None
    for rec in results:
        if not (rec.get("plainLyrics") or rec.get("syncedLyrics") or rec.get("instrumental")):
            continue
        if key_text(rec.get("trackName", "")) != key_text(title):
            continue
        diff = abs((rec.get("duration") or 0) - duration) if duration else 0
        if duration and diff > MAX_DURATION_DIFF:
            continue
        if best is None or diff < best_value:
            best, best_value = rec, diff
    return best


def lyrics_text(record):
    """Plain lyrics from a record (derived from the synced ones if needed)."""
    if record.get("plainLyrics"):
        return record["plainLyrics"].strip()
    if record.get("syncedLyrics"):
        return TIMESTAMP_RE.sub("", record["syncedLyrics"]).strip()
    return ""


def read_lyrics(path):
    if path.suffix.lower() == ".mp3":
        try:
            return any(frame.text.strip() for frame in ID3(path).getall("USLT"))
        except ID3NoHeaderError:
            return False
    audio = mutagen.File(path)
    return bool(audio and (audio.get("lyrics") or audio.get("unsyncedlyrics")))


def write_lyrics(path, text):
    if path.suffix.lower() == ".mp3":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags.delall("USLT")
        tags.add(USLT(encoding=1, lang="XXX", desc="", text=text))   # UTF-16: valid in v2.3
        tags.save(path, v2_version=3)
    else:
        audio = mutagen.File(path)
        audio["lyrics"] = [text]
        audio.save()


# ------------------------------------------------------------------------ run ---

def read_tracks(files):
    tracks = []
    for path in files:
        try:
            audio = mutagen.File(path, easy=True)
            if audio is None:
                continue
            fields = ("title", "artist", "albumartist", "album", "date", "originaldate", "genre",
                      "tracknumber", "discnumber", "musicbrainz_albumid",
                      "musicbrainz_releasegroupid", "musicbrainz_trackid")
            tags = {}
            for field in fields:
                try:
                    tags[field] = first(audio, field)
                except Exception:
                    tags[field] = ""
            tracks.append({
                "path": path, "tags": tags,
                "title": tags["title"],
                "num": first_number(tags["tracknumber"]),
                "disc": first_number(tags["discnumber"]) or 1,
                "length": getattr(audio.info, "length", 0) or 0,
            })
        except Exception as exc:
            print(f"  [read error] {path}: {exc}")
    return tracks


def run(args):
    do_meta, do_covers, do_lyrics = args.metadata, args.covers, args.lyrics
    if not (do_meta or do_covers or do_lyrics):
        do_meta = do_covers = do_lyrics = True

    mode = args.match or ("both" if args.fingerprint else "tags")
    fpcalc = None
    if mode != "tags":
        if not args.acoustid_key:
            raise SystemExit(f"--match {mode} needs your free AcoustID application key: pass "
                             "--acoustid-key KEY (or set ACOUSTID_API_KEY). Get one at "
                             "https://acoustid.org/new-application")
        fpcalc = find_fpcalc(args.fpcalc)

    files = find_audio_files(args.folder)
    print(f"Found {len(files)} files.")
    tracks = read_tracks(files)
    http = make_http(args)

    rows, stats, no_match = [], Counter(), []
    idents = {}                            # path -> AcoustID identification
    pending_meta = defaultdict(dict)       # path -> fields
    pending_covers = []                    # (album label, [paths], bytes, url)
    pending_lyrics = []                    # (path, text, synced text or "")

    try:
        albums = defaultdict(list)           # one album = same folder + same album title
        for t in tracks:
            albums[(t["path"].parent, key_text(t["tags"]["album"]))].append(t)

        if do_meta or do_covers or (do_lyrics and mode != "tags"):
            for (_folder, _key), items in sorted(albums.items(), key=lambda kv: str(kv[0])):
                album = Counter(t["tags"]["album"] for t in items).most_common(1)[0][0]
                artist = group_artist(items)
                if not album:
                    continue
                label = f"{artist} - {album}" if artist else album
                query_album = DISC_SUFFIX_RE.sub("", album)
                found, release, hit = {}, None, None
                if fpcalc:
                    try:
                        found = fingerprint_album(http, args.acoustid_key, fpcalc, items)
                    except FingerprintError as exc:
                        print(f"\nFingerprinting stopped: {exc}")
                        fpcalc = None
                    stats["tracks identified from the audio"] += len(found)
                    stats["tracks not identified from the audio"] += len(items) - len(found)
                    idents.update(found)
                    if found:
                        release = release_from_fingerprints(http, found, len(items))
                        if release:
                            hit = {"id": release["id"], "title": release.get("title"),
                                   "release-group": release.get("release-group")}
                            stats["albums matched by fingerprint"] += 1
                    for item in items:
                        ident = found.get(item["path"])
                        if ident and ident["title"] and item["title"] \
                                and similarity(item["title"], ident["title"]) < MIN_TRACK_SIMILARITY:
                            rows.append([str(item["path"]), "check", "title", item["title"],
                                         ident["title"], "AcoustID: the audio looks like a different track"])
                            stats["tracks whose tags disagree with the audio"] += 1
                if not (do_meta or do_covers):
                    continue                      # lyrics only: the identification is all we need
                if hit is None and mode != "audio":
                    hit = find_release(http, artist, query_album, len(items),
                                       log=(lambda m, n=label: print(f"  {n}: {m}")) if args.verbose else None)
                if hit is None:
                    stats["albums without a confident match"] += 1
                    no_match.append(label)
                    continue
                stats["albums matched"] += 1
                if args.verbose:
                    print(f"  {label}: matched '{hit.get('title')}' ({hit['id']})")

                if release is None and do_meta:
                    release = release_details(http, hit["id"])
                if do_meta and release:
                    mb_tracks = release_tracks(release)
                    pairs = pair_with_fingerprints(items, found, mb_tracks)
                    if len(pairs) * 2 < len(items):
                        # most of your tracks don't exist on this release: probably another edition
                        stats["albums skipped: your tracks don't fit the release"] += 1
                        no_match.append(label + "  (found a release, but your tracks don't fit it)")
                        pairs = None
                    for index, item in enumerate(items if pairs is not None else []):
                        changes = metadata_changes(item, pairs.get(index), release, args.overwrite)
                        for field, value in changes.items():
                            rows.append([str(item["path"]), "metadata", field,
                                         item["tags"].get(field, ""), value, "MusicBrainz"])
                            pending_meta[item["path"]][field] = value
                            stats[f"metadata: {field}"] += 1
                        if index not in pairs:
                            stats["tracks not matched to the release"] += 1

                if do_covers:
                    has_cover = any(any(cv.is_valid(p) for p in cv.get_pictures(t["path"]))
                                    for t in items)
                    if has_cover:
                        stats["albums that already have a cover"] += 1
                    else:
                        data, url = fetch_cover(http, hit, args.cover_size, release)
                        if data is None:
                            stats["albums with no cover found online"] += 1
                        else:
                            paths = [t["path"] for t in items]
                            pending_covers.append((label, paths, data, url))
                            for path in paths:
                                rows.append([str(path), "cover", "front cover", "(none)",
                                             f"{len(data) // 1024} KB", url])
                            stats["covers to add (tracks)"] += len(paths)

        if do_lyrics:
            for t in tracks:
                artist = split_artists(t["tags"]["albumartist"] or t["tags"]["artist"])
                artist = artist[0] if artist else ""
                title = t["title"]
                ident = idents.get(t["path"])
                if mode == "audio" or (ident and ident["title"] and (
                        not title or similarity(title, ident["title"]) < MIN_TRACK_SIMILARITY)):
                    # trust the audio, not a tag that disagrees with it
                    if not ident or not ident["title"]:
                        continue
                    title = ident["title"]
                    names = split_artists(ident["artist"])
                    artist = names[0] if names else artist
                if not artist or not title:
                    continue
                if read_lyrics(t["path"]) and not args.overwrite:
                    stats["lyrics: already present"] += 1
                    continue
                record = find_lyrics(http, artist, title, t["tags"]["album"], t["length"])
                if record is None:
                    stats["lyrics: not found"] += 1
                    continue
                if record.get("instrumental") and not lyrics_text(record):
                    stats["lyrics: instrumental"] += 1
                    continue
                text = lyrics_text(record)
                if not text:
                    stats["lyrics: not found"] += 1
                    continue
                synced = record.get("syncedLyrics") or ""
                pending_lyrics.append((t["path"], text, synced if args.lrc else ""))
                rows.append([str(t["path"]), "lyrics", "lyrics", "(none)",
                             f"{len(text.splitlines())} lines" + (" + .lrc" if synced and args.lrc else ""),
                             "LRCLIB"])
                stats["lyrics to add"] += 1
    except OfflineError as exc:
        print(f"\nStopped: {exc}")
        stats["stopped early (offline)"] += 1

    # ---- write
    errors = 0
    if args.apply:
        for path, changes in pending_meta.items():
            try:
                write_changes(path, changes)
            except Exception as exc:
                errors += 1
                print(f"  [write error] {path}: {exc}")
        for label, paths, data, _url in pending_covers:
            for path in paths:
                try:
                    cv.set_picture(path, data)
                except Exception as exc:
                    errors += 1
                    print(f"  [write error] {path}: {exc}")
        for path, text, synced in pending_lyrics:
            try:
                write_lyrics(path, text)
                if synced:
                    path.with_suffix(".lrc").write_text(synced, encoding="utf-8")
            except Exception as exc:
                errors += 1
                print(f"  [write error] {path}: {exc}")

    if no_match:
        print("\n=== ALBUMS WITH NO CONFIDENT MATCH (nothing was changed for them) ===")
        for label in no_match:
            print("  -", label)

    print("\n=== SUMMARY ===")
    for label, n in sorted(stats.items()):
        print(f"  {label}: {n}")
    if errors:
        print(f"  write errors: {errors}")
    failed = getattr(http, "error_counts", None)
    if failed:
        details = ", ".join(f"HTTP {code} x{n}" for code, n in sorted(failed.items()))
        print(f"  WARNING: some online requests failed ({details}). "
              "Results may be incomplete: try again later.")
    name = "online_applied.csv" if args.apply else "online_preview.csv"
    log = write_csv(args.out_dir, name, ["file", "kind", "field", "before", "after", "source"], rows)
    print(f"Details saved to: {log}")
    if not args.apply:
        print("Nothing was written to your files. If it looks right, run again adding --apply "
              "(answers are cached, so it will be quick)")
