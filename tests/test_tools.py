import contextlib
import io
import json
import unittest

from mutagen.id3 import ID3
from mutagen.mp3 import EasyMP3

from musictools.cli import main
from tests.helpers import BLUE_JPG, GREEN_JPG, RED_JPG, TempDir, cover_of, make_track, set_cover


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main([str(a) for a in argv])
    return code, buf.getvalue()


def tag(path, key):
    value = EasyMP3(path).get(key)
    return value[0] if value else ""


class TagsTest(unittest.TestCase):
    def test_preview_changes_nothing_and_apply_does(self):
        with TempDir() as d:
            out = d / "out"
            a = make_track(d / "alb", "1.mp3", title="One", artist="Main", album="Rec", tracknumber="1")
            b = make_track(d / "alb", "2.mp3", title="Two", artist="Main / Guest", album="Rec", tracknumber="2")
            run("tags", d, "--out-dir", out)
            self.assertEqual(tag(b, "artist"), "Main / Guest")
            run("tags", d, "--apply", "--out-dir", out)
            self.assertEqual(tag(b, "artist"), "Main")
            self.assertEqual(tag(a, "albumartist"), "Main")
            self.assertIn("feat. Guest", tag(b, "title"))
            self.assertEqual(ID3(b).version[1], 3)

    def test_no_feat_in_title(self):
        with TempDir() as d:
            a = make_track(d, "1.mp3", title="One", artist="Main", album="Rec", tracknumber="1")
            b = make_track(d, "2.mp3", title="Two", artist="Main; Guest", album="Rec", tracknumber="2")
            run("tags", d, "--apply", "--no-feat-in-title", "--out-dir", d / "o")
            self.assertEqual(tag(b, "title"), "Two")
            self.assertEqual(tag(b, "artist"), "Main")

    def test_compilation_detected(self):
        with TempDir() as d:
            files = [make_track(d, f"{i}.mp3", title=f"T{i}", artist=f"Band {i}", album="Mix", tracknumber=str(i))
                     for i in range(1, 5)]
            run("tags", d, "--apply", "--out-dir", d / "o")
            for f in files:
                self.assertEqual(tag(f, "albumartist"), "Various Artists")
                self.assertEqual(tag(f, "compilation"), "1")
            self.assertIn("(Band 1)", tag(files[0], "title"))

    def test_rules_file(self):
        with TempDir() as d:
            f = make_track(d, "1.mp3", title="X", artist="Whoever", album="My: Album", tracknumber="1")
            rules = d / "r.json"
            rules.write_text(json.dumps({"rules": [
                {"album_regex": "^my album$", "set": {"artist": "Chosen", "album": "Fixed Title"}}]}))
            run("tags", d, "--apply", "--rules", rules, "--out-dir", d / "o")
            self.assertEqual(tag(f, "artist"), "Chosen")
            self.assertEqual(tag(f, "album"), "Fixed Title")

    def test_invalid_rules_rejected(self):
        with TempDir() as d:
            make_track(d, "1.mp3", title="X", artist="A", album="B")
            rules = d / "r.json"
            rules.write_text(json.dumps({"rules": [{"set": {"artist": "x"}}]}))
            with self.assertRaises(SystemExit):
                run("tags", d, "--rules", rules, "--out-dir", d / "o")

    def test_duplicates_moved_only_with_flag(self):
        with TempDir() as d:
            make_track(d / "a", "1.mp3", title="Same", artist="A", album="Al", tracknumber="1")
            make_track(d / "a", "1 copy.mp3", title="Same", artist="A", album="Al", tracknumber="1")
            run("tags", d, "--apply", "--out-dir", d / "o")
            self.assertEqual(len(list(d.rglob("*.mp3"))), 2)
            run("tags", d, "--apply", "--move-dupes", "--out-dir", d / "o")
            self.assertEqual(len(list((d / "_duplicates").rglob("*.mp3"))), 1)


class CoversTest(unittest.TestCase):
    def album(self, d, discs=1):
        paths = []
        for disc in range(1, discs + 1):
            for n in range(1, 4):
                paths.append(make_track(d / "alb", f"{disc}-{n}.mp3", title=f"T{n}", artist="A",
                                        albumartist="A", album="Al", tracknumber=str(n),
                                        discnumber=f"{disc}/{discs}"))
        return paths

    def test_missing_cover_filled_from_siblings(self):
        with TempDir() as d:
            p = self.album(d)
            set_cover(p[0], RED_JPG)
            set_cover(p[1], RED_JPG)
            run("covers", d, "--out-dir", d / "o")
            self.assertIsNone(cover_of(p[2]))
            run("covers", d, "--apply", "--out-dir", d / "o")
            self.assertEqual(cover_of(p[2]), RED_JPG)

    def test_invalid_cover_repaired(self):
        with TempDir() as d:
            p = self.album(d)
            set_cover(p[0], RED_JPG)
            set_cover(p[1], RED_JPG)
            set_cover(p[2], b"not an image at all" * 20)
            run("covers", d, "--apply", "--out-dir", d / "o")
            self.assertEqual(cover_of(p[2]), RED_JPG)

    def test_each_disc_keeps_its_own_cover(self):
        with TempDir() as d:
            p = self.album(d, discs=2)
            for f in p[:3]:
                set_cover(f, RED_JPG)
            for f in p[3:]:
                set_cover(f, BLUE_JPG)
            run("covers", d, "--apply", "--unify", "--out-dir", d / "o")
            self.assertTrue(all(cover_of(f) == RED_JPG for f in p[:3]))
            self.assertTrue(all(cover_of(f) == BLUE_JPG for f in p[3:]))

    def test_unify_within_disc(self):
        with TempDir() as d:
            p = self.album(d)
            set_cover(p[0], RED_JPG)
            set_cover(p[1], RED_JPG)
            set_cover(p[2], GREEN_JPG)
            run("covers", d, "--apply", "--unify", "--out-dir", d / "o")
            self.assertTrue(all(cover_of(f) == RED_JPG for f in p))

    def test_set_cover_range(self):
        with TempDir() as d:
            p = self.album(d)
            img = d / "x.jpg"
            img.write_bytes(GREEN_JPG)
            run("covers", d / "alb", "--set-cover", img, "--from", "2", "--apply", "--out-dir", d / "o")
            self.assertIsNone(cover_of(p[0]))
            self.assertEqual(cover_of(p[1]), GREEN_JPG)
            self.assertEqual(cover_of(p[2]), GREEN_JPG)

    def test_export_with_awkward_album_name(self):
        with TempDir() as d:
            p = make_track(d, "1.mp3", title="T", artist="A", album="Weird: name? ", tracknumber="1")
            set_cover(p, RED_JPG)
            code, _ = run("covers", d, "--export", "--out-dir", d / "o")
            self.assertEqual(code, 0)


class Id3v23Test(unittest.TestCase):
    def test_convert(self):
        with TempDir() as d:
            p = make_track(d, "1.mp3", title="T", artist="A", album="B")
            tags = ID3(p)
            tags.save(p, v2_version=4)
            self.assertEqual(ID3(p).version[1], 4)
            run("id3v23", d, "--out-dir", d / "o")
            self.assertEqual(ID3(p).version[1], 4)
            run("id3v23", d, "--apply", "--out-dir", d / "o")
            self.assertEqual(ID3(p).version[1], 3)
            self.assertEqual(tag(p, "title"), "T")


class CliTest(unittest.TestCase):
    def test_no_command_shows_welcome(self):
        code, out = run()
        self.assertEqual(code, 0)
        for name in ("tags", "online", "covers", "id3v23", "--apply"):
            self.assertIn(name, out)

    def test_command_prints_mode_and_reports_folder(self):
        with TempDir() as d:
            make_track(d, "1.mp3", title="T", artist="A", album="B")
            _code, out = run("id3v23", d)
            self.assertIn("MODE: PREVIEW", out)
            self.assertIn("_reports", out)
            _code, out = run("id3v23", d, "--apply")
            self.assertIn("MODE: APPLY", out)
            self.assertIn("Done.", out)


if __name__ == "__main__":
    unittest.main()


class ReportsFolderTest(unittest.TestCase):
    def test_reports_folder_created_inside_music_folder(self):
        with TempDir() as d:
            make_track(d / "alb", "1.mp3", title="One", artist="A", album="Al", tracknumber="1")
            self.assertFalse((d / "_reports").exists())
            run("tags", d)
            self.assertTrue(list((d / "_reports").glob("tags_preview.csv")))
            run("id3v23", d, "--apply")
            self.assertTrue((d / "_reports" / "id3v23_applied.csv").exists())
