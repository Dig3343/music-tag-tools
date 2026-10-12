# SPDX-License-Identifier: GPL-3.0-or-later
import contextlib
import io
import json
import unittest
import urllib.error
from unittest import mock

from mutagen.id3 import ID3
from mutagen.mp3 import EasyMP3

from musictools import online
from musictools.cli import main
from tests.helpers import RED_JPG, TempDir, cover_of, make_track, set_cover

RELEASE_ID = "11111111-1111-1111-1111-111111111111"
GROUP_ID = "22222222-2222-2222-2222-222222222222"

SEARCH = {"releases": [{
    "id": RELEASE_ID, "score": 100, "title": "Test Album", "track-count": 3,
    "artist-credit": [{"name": "Test Artist", "artist": {"name": "Test Artist"}}],
    "release-group": {"id": GROUP_ID},
}]}

DETAILS = {
    "id": RELEASE_ID, "title": "Test Album", "date": "1999-04-01",
    "artist-credit": [{"name": "Test Artist", "joinphrase": "", "artist": {"name": "Test Artist"}}],
    "release-group": {"id": GROUP_ID, "first-release-date": "1999",
                      "genres": [{"name": "trip hop", "count": 5}, {"name": "pop", "count": 1}]},
    "cover-art-archive": {"front": True},
    "media": [{"position": 1, "track-count": 3, "tracks": [
        {"position": i, "number": str(i), "title": f"Song {i}",
         "recording": {"id": f"rec-{i}"},
         "artist-credit": [{"name": "Test Artist", "joinphrase": ""}]} for i in (1, 2, 3)]}],
}


class FakeHttp:
    """Answers like the three services, without any network access."""

    def __init__(self, lyrics=True, cover=True):
        self.urls = []
        self.lyrics = lyrics
        self.cover = cover

    def get_json(self, url):
        self.urls.append(url)
        if "musicbrainz.org/ws/2/release/?" in url:
            return SEARCH
        if "musicbrainz.org/ws/2/release/" in url:
            return DETAILS
        if "lrclib.net/api/get" in url or "lrclib.net/api/search" in url:
            if not self.lyrics:
                return None
            record = {"trackName": "Song 1", "duration": 0, "plainLyrics": "line one\nline two",
                      "syncedLyrics": "[00:01.00] line one\n[00:02.00] line two", "instrumental": False}
            return [record] if "search" in url else record
        return None

    def post_json(self, url, fields, cache_key):
        self.urls.append(url)
        index = int(fields["fingerprint"].split("-")[1])
        if index == 9:                                    # a track AcoustID doesn't know
            return {"status": "ok", "results": []}
        return {"status": "ok", "results": [{"score": 0.97, "recordings": [{
            "id": f"rec-{index}", "title": f"Song {index}",
            "artists": [{"name": "Test Artist"}], "releases": [{"id": RELEASE_ID}]}]}]}

    def get_bytes(self, url):
        self.urls.append(url)
        return RED_JPG if (self.cover and "coverartarchive.org" in url) else None


def run_online(folder, fake, *extra):
    with mock.patch("musictools.online.make_http", return_value=fake), \
            contextlib.redirect_stdout(io.StringIO()):
        return main(["online", str(folder), "--out-dir", str(folder / "_out"), *extra])


def album(d):
    return [make_track(d / "alb", f"{i}.mp3", artist="Test Artist", album="Test Album",
                       title=f"Song {i}") for i in (1, 2, 3)]


class OnlineTest(unittest.TestCase):
    def test_preview_writes_nothing(self):
        with TempDir() as d:
            files = album(d)
            run_online(d, FakeHttp())
            tags = EasyMP3(files[0])
            self.assertNotIn("date", tags)
            self.assertIsNone(cover_of(files[0]))

    def test_metadata_filled_when_missing(self):
        with TempDir() as d:
            files = album(d)
            run_online(d, FakeHttp(), "--metadata", "--apply")
            tags = EasyMP3(files[1])
            self.assertEqual(tags["date"], ["1999-04-01"])
            self.assertEqual(tags["originaldate"], ["1999"])
            self.assertEqual(tags["genre"], ["Trip Hop"])
            self.assertEqual(tags["tracknumber"], ["2/3"])
            self.assertEqual(tags["albumartist"], ["Test Artist"])
            self.assertEqual(tags["musicbrainz_albumid"], [RELEASE_ID])
            self.assertEqual(tags["musicbrainz_trackid"], ["rec-2"])
            self.assertEqual(ID3(files[1]).version[1], 3)

    def test_existing_values_kept_unless_overwrite(self):
        with TempDir() as d:
            p = make_track(d, "1.mp3", artist="Test Artist", album="Test Album", title="Song 1",
                           date="2001", genre="Rock")
            make_track(d, "2.mp3", artist="Test Artist", album="Test Album", title="Song 2")
            make_track(d, "3.mp3", artist="Test Artist", album="Test Album", title="Song 3")
            run_online(d, FakeHttp(), "--metadata", "--apply")
            self.assertEqual(EasyMP3(p)["date"], ["2001"])
            self.assertEqual(EasyMP3(p)["genre"], ["Rock"])
            run_online(d, FakeHttp(), "--metadata", "--apply", "--overwrite", "--no-cache")
            self.assertEqual(EasyMP3(p)["date"], ["1999-04-01"])
            self.assertEqual(EasyMP3(p)["artist"], ["Test Artist"])

    def test_missing_title_filled_by_track_number(self):
        with TempDir() as d:
            make_track(d, "1.mp3", artist="Test Artist", album="Test Album", title="Song 1", tracknumber="1")
            make_track(d, "3.mp3", artist="Test Artist", album="Test Album", title="Song 3", tracknumber="3")
            p = make_track(d, "2.mp3", artist="Test Artist", album="Test Album", tracknumber="2")
            run_online(d, FakeHttp(), "--metadata", "--apply")
            self.assertEqual(EasyMP3(p)["title"], ["Song 2"])

    def test_cover_added_only_when_album_has_none(self):
        with TempDir() as d:
            files = album(d)
            run_online(d, FakeHttp(), "--covers", "--apply")
            self.assertTrue(all(cover_of(f) == RED_JPG for f in files))

    def test_existing_cover_not_replaced(self):
        with TempDir() as d:
            files = album(d)
            from tests.helpers import BLUE_JPG
            set_cover(files[0], BLUE_JPG)
            fake = FakeHttp()
            run_online(d, fake, "--covers", "--apply")
            self.assertEqual(cover_of(files[0]), BLUE_JPG)
            self.assertIsNone(cover_of(files[1]))          # left to the 'covers' command
            self.assertFalse(any("coverartarchive" in u for u in fake.urls))

    def test_lyrics_embedded_and_lrc_saved(self):
        with TempDir() as d:
            files = album(d)
            run_online(d, FakeHttp(), "--lyrics", "--lrc", "--apply")
            frames = ID3(files[0]).getall("USLT")
            self.assertEqual(len(frames), 1)
            self.assertIn("line one", frames[0].text)
            self.assertEqual(ID3(files[0]).version[1], 3)
            lrc = files[0].with_suffix(".lrc")
            self.assertTrue(lrc.exists())
            self.assertIn("[00:01.00]", lrc.read_text(encoding="utf-8"))

    def test_lyrics_not_replaced_without_overwrite(self):
        with TempDir() as d:
            files = album(d)
            online.write_lyrics(files[0], "my own words")
            run_online(d, FakeHttp(), "--lyrics", "--apply")
            self.assertEqual(ID3(files[0]).getall("USLT")[0].text, "my own words")

    def test_guest_artists_do_not_split_an_album(self):
        with TempDir() as d:
            files = [make_track(d, "1.mp3", artist="Test Artist", album="Test Album", title="Song 1"),
                     make_track(d, "2.mp3", artist="Test Artist, Some Guest", album="Test Album", title="Song 2"),
                     make_track(d, "3.mp3", artist="TEST ARTIST", album="Test Album", title="Song 3")]
            fake = FakeHttp()
            run_online(d, fake, "--metadata", "--apply")
            searches = [u for u in fake.urls if "musicbrainz.org/ws/2/release/?" in u]
            self.assertEqual(len(searches), 1)
            self.assertTrue(all(EasyMP3(f)["date"] == ["1999-04-01"] for f in files))

    def test_release_whose_tracks_dont_fit_is_skipped(self):
        with TempDir() as d:
            files = [make_track(d, f"{i}.mp3", artist="Test Artist", album="Test Album",
                                title=f"Unrelated {i}") for i in (1, 2, 3)]
            run_online(d, FakeHttp(), "--metadata", "--apply")
            self.assertNotIn("musicbrainz_albumid", EasyMP3(files[0]))

    def test_unconfident_album_untouched(self):
        with TempDir() as d:
            files = [make_track(d, "1.mp3", artist="Test Artist", album="Totally Different", title="x")]
            run_online(d, FakeHttp(), "--metadata", "--apply")
            self.assertNotIn("date", EasyMP3(files[0]))


class FingerprintTest(unittest.TestCase):
    def run_fp(self, folder, *extra):
        def fake_fingerprint(_exe, path):
            return 200, "fp-" + path.stem                      # file '2.mp3' -> 'fp-2'
        with mock.patch("musictools.online.find_fpcalc", return_value="fpcalc"), \
                mock.patch("musictools.online.fingerprint_file", side_effect=fake_fingerprint):
            return run_online(folder, FakeHttp(), "--fingerprint", "--acoustid-key", "k", *extra)

    def test_identifies_album_the_tags_cannot_find(self):
        with TempDir() as d:
            files = [make_track(d, f"{i}.mp3", artist="Test Artist", album="Some Wrong Album",
                                title=f"Song {i}") for i in (1, 2, 3)]
            run_online(d, FakeHttp(), "--metadata", "--apply")         # tags alone: no match
            self.assertNotIn("date", EasyMP3(files[0]))
            self.run_fp(d, "--metadata", "--apply")
            self.assertEqual(EasyMP3(files[1])["date"], ["1999-04-01"])
            self.assertEqual(EasyMP3(files[1])["musicbrainz_trackid"], ["rec-2"])

    def test_tag_that_disagrees_with_audio_is_flagged_and_paired_by_audio(self):
        with TempDir() as d:
            files = [make_track(d, f"{i}.mp3", artist="Test Artist", album="Test Album",
                                title="Totally Wrong Title" if i == 2 else f"Song {i}") for i in (1, 2, 3)]
            self.run_fp(d, "--metadata", "--apply")
            self.assertEqual(EasyMP3(files[1])["tracknumber"], ["2/3"])
            self.assertEqual(EasyMP3(files[1])["title"], ["Totally Wrong Title"])   # not overwritten
            report = (d / "_out" / "online_applied.csv").read_text(encoding="utf-8-sig")
            self.assertIn("check,title,Totally Wrong Title,Song 2", report)

    def test_match_audio_has_no_tag_fallback_but_both_has(self):
        with TempDir() as d:
            files = [make_track(d, f"{i}.mp3", artist="Test Artist", album="Test Album",
                                title=f"Song {i}") for i in (1, 2, 3)]
            def unknown(_exe, path):
                return 200, "fp-9"                              # AcoustID knows none of them
            with mock.patch("musictools.online.find_fpcalc", return_value="fpcalc"), \
                    mock.patch("musictools.online.fingerprint_file", side_effect=unknown):
                run_online(d, FakeHttp(), "--match", "audio", "--metadata", "--apply", "--acoustid-key", "k")
                self.assertNotIn("date", EasyMP3(files[0]))
                run_online(d, FakeHttp(), "--match", "both", "--metadata", "--apply", "--acoustid-key", "k")
                self.assertEqual(EasyMP3(files[0])["date"], ["1999-04-01"])

    def test_match_tags_never_calls_acoustid(self):
        with TempDir() as d:
            make_track(d, "1.mp3", artist="Test Artist", album="Test Album", title="Song 1")
            fake = FakeHttp()
            run_online(d, fake, "--match", "tags", "--metadata", "--apply")
            self.assertFalse(any("acoustid" in u for u in fake.urls))

    def test_lyrics_use_the_audio_identity_when_tag_is_wrong(self):
        with TempDir() as d:
            p = make_track(d, "1.mp3", artist="Test Artist", album="Test Album", title="Wrong Name")
            fake = FakeHttp()
            with mock.patch("musictools.online.find_fpcalc", return_value="fpcalc"), \
                    mock.patch("musictools.online.fingerprint_file", return_value=(200, "fp-1")), \
                    mock.patch("musictools.online.make_http", return_value=fake), \
                    contextlib.redirect_stdout(io.StringIO()):
                main(["online", str(d), "--match", "audio", "--lyrics", "--acoustid-key", "k",
                      "--out-dir", str(d / "_out")])
            self.assertTrue(any("track_name=Song+1" in u for u in fake.urls))

    def test_missing_key_is_refused(self):
        with TempDir() as d:
            make_track(d, "1.mp3", title="x", artist="A", album="B")
            with self.assertRaises(SystemExit):
                with mock.patch("musictools.online.make_http", return_value=FakeHttp()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    main(["online", str(d), "--fingerprint", "--acoustid-key", ""])

    def test_unknown_track_is_skipped_without_crashing(self):
        with TempDir() as d:
            make_track(d, "9.mp3", artist="Test Artist", album="Some Wrong Album", title="Mystery")
            self.assertEqual(self.run_fp(d, "--metadata"), 0)


class HttpTest(unittest.TestCase):
    class Opener:
        def __init__(self, behaviour):
            self.behaviour, self.calls = behaviour, 0

        def open(self, request, timeout=0):
            self.calls += 1
            return self.behaviour(self.calls)

    class Body:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def make(self, behaviour, cache=None):
        return online.Http("test", cache, opener=self.Opener(behaviour), sleep=lambda s: None)

    def test_404_is_none_and_cached(self):
        def behave(n):
            raise urllib.error.HTTPError("u", 404, "nf", {}, None)
        with TempDir() as d:
            http = self.make(behave, d)
            self.assertIsNone(http.get_json("https://example.org/a"))
            self.assertIsNone(http.get_json("https://example.org/a"))
            self.assertEqual(http.opener.calls, 1)

    def test_retry_then_success(self):
        def behave(n):
            if n < 3:
                raise urllib.error.HTTPError("u", 503, "busy", {}, None)
            return self.Body(json.dumps({"ok": 1}).encode())
        http = self.make(behave)
        self.assertEqual(http.get_json("https://example.org/a"), {"ok": 1})

    def test_offline_aborts(self):
        def behave(n):
            raise urllib.error.URLError("no network")
        http = self.make(behave)
        with self.assertRaises(online.OfflineError):
            for i in range(5):
                http.get_json(f"https://example.org/{i}")

    def test_lucene_escape(self):
        self.assertEqual(online.lucene_phrase('say "hi"'), '"say \\"hi\\""')


if __name__ == "__main__":
    unittest.main()


class CsvLockTest(unittest.TestCase):
    def test_locked_report_is_saved_under_another_name(self):
        from musictools.common import write_csv
        with TempDir() as d:
            real_open = open

            def locked(path, *a, **kw):
                if str(path).endswith("report.csv"):
                    raise PermissionError(13, "Permission denied")
                return real_open(path, *a, **kw)
            with mock.patch("builtins.open", side_effect=locked), \
                    contextlib.redirect_stdout(io.StringIO()):
                path = write_csv(d, "report.csv", ["a"], [["1"]])
            self.assertNotEqual(path.name, "report.csv")
            self.assertTrue(path.exists())
