# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

from musictools import gui_data
from tests.helpers import TempDir, make_track, set_cover
import tests.helpers as helpers


class TrackTests(unittest.TestCase):
    def test_read_and_scan(self):
        with TempDir() as tmp:
            a = make_track(tmp, "a.mp3", title="One", artist="Art", album="Alb", albumartist="Art", tracknumber="1")
            make_track(tmp, "b.mp3", title="Two", artist="Art", album="Alb", tracknumber="2")
            set_cover(a, helpers.RED_JPG)
            info = gui_data.read_track(a)
            self.assertEqual((info["title"], info["artist"], info["album"], info["track"]), ("One", "Art", "Alb", 1))
            self.assertEqual(info["format"], "ID3v2.3")
            self.assertIsNotNone(info["cover"])
            rows = [t for _i, _n, t in gui_data.scan_library(tmp, make_thumb=lambda data: len(data))]
            self.assertEqual(len(rows), 2)
            self.assertEqual(gui_data.library_summary(rows),
                             {"tracks": 2, "no_cover": 1, "no_lyrics": 2, "no_albumartist": 1})
            self.assertEqual(len(gui_data.filter_tracks(rows, only="albumartist")), 1)
            self.assertEqual(len(gui_data.filter_tracks(rows, only="cover")), 1)
            self.assertEqual(len(gui_data.filter_tracks(rows, text="two")), 1)
            self.assertTrue(any(t["thumb"] for t in rows))

    def test_unreadable_file_is_skipped(self):
        with TempDir() as tmp:
            (Path(tmp) / "bad.mp3").write_bytes(b"not audio")
            self.assertEqual(list(gui_data.scan_library(tmp)), [])


class ReportTests(unittest.TestCase):
    def test_load_and_summarize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags_preview.csv"
            path.write_text("sep=,\r\nfile,field,before,after,reason\r\nx/a.mp3,artist,A,B,rule\r\n"
                            "x/b.mp3,artist,A,B,rule\r\nx/b.mp3,album,C,D,rule\r\n", encoding="utf-8-sig")
            header, rows = gui_data.load_report(path)
            self.assertEqual(header[0], "file")
            self.assertEqual(len(rows), 3)
            summary = gui_data.summarize("tags", header, rows)
            self.assertEqual((summary["changes"], summary["files"]), (3, 2))
            self.assertEqual(summary["kinds"][0], ("artist", 2))
            found = gui_data.find_report(tmp, "tags", False, 0)
            self.assertEqual(found, path)
            self.assertIsNone(gui_data.find_report(tmp, "tags", True, 0))


if __name__ == "__main__":
    unittest.main()
