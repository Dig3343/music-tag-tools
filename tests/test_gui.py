# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

from musictools.gui import build_args


class BuildArgsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_folder(self):
        with self.assertRaises(ValueError):
            build_args("tags", "", False, {})
        with self.assertRaises(ValueError):
            build_args("tags", str(Path(self.folder) / "nope"), False, {})

    def test_preview_and_apply(self):
        self.assertEqual(build_args("id3v23", self.folder, False, {}), ["id3v23", self.folder])
        self.assertEqual(build_args("id3v23", self.folder, True, {}), ["id3v23", self.folder, "--apply", "--yes"])

    def test_tags_options(self):
        args = build_args("tags", self.folder, False, {"no_auto": True, "ratio": "0,7", "rules": "r.json"})
        self.assertIn("--no-auto", args)
        self.assertEqual(args[args.index("--main-artist-ratio") + 1], "0.7")
        self.assertEqual(args[args.index("--rules") + 1], "r.json")
        self.assertNotIn("--main-artist-ratio", build_args("tags", self.folder, False, {"ratio": "0.6"}))
        with self.assertRaises(ValueError):
            build_args("tags", self.folder, False, {"ratio": "abc"})
        with self.assertRaises(ValueError):
            build_args("tags", self.folder, False, {"ratio": "2"})

    def test_online(self):
        allon = {"metadata": True, "covers": True, "lyrics": True, "match": "tags"}
        args = build_args("online", self.folder, False, allon)
        self.assertNotIn("--metadata", args)
        self.assertIn("--match", args)
        only = build_args("online", self.folder, False, {"lyrics": True, "lrc": True, "match": "tags"})
        self.assertIn("--lyrics", only)
        self.assertIn("--lrc", only)
        with self.assertRaises(ValueError):
            build_args("online", self.folder, False, {"match": "tags"})
        with self.assertRaises(ValueError):
            build_args("online", self.folder, False, dict(allon, match="audio"))
        ok = build_args("online", self.folder, False, dict(allon, match="both", key="K"))
        self.assertEqual(ok[ok.index("--acoustid-key") + 1], "K")

    def test_covers(self):
        self.assertIn("--unify", build_args("covers", self.folder, False, {"mode": "unify"}))
        with self.assertRaises(ValueError):
            build_args("covers", self.folder, False, {"mode": "set"})
        img = Path(self.folder) / "c.jpg"
        img.write_bytes(b"x")
        args = build_args("covers", self.folder, False, {"mode": "set", "image": str(img), "from": "1", "to": "5"})
        self.assertEqual(args[args.index("--from") + 1], "1")
        with self.assertRaises(ValueError):
            build_args("covers", self.folder, False, {"mode": "set", "image": str(img), "from": "x"})



class CommandForTests(unittest.TestCase):
    def test_source_and_frozen(self):
        from unittest import mock
        from musictools import gui
        with mock.patch.object(gui, "FROZEN", False):
            self.assertEqual(gui.command_for(["tags", "x"])[1:3], ["-m", "musictools"])
            self.assertIsNotNone(gui.process_cwd())
        with mock.patch.object(gui, "FROZEN", True):
            cmd = gui.command_for(["tags", "x"])
            self.assertEqual(cmd[1:], ["tags", "x"])
            self.assertIsNone(gui.process_cwd())



class TextsTests(unittest.TestCase):
    def test_languages_have_same_keys(self):
        from musictools.gui_texts import EN, IT
        self.assertEqual(set(EN), set(IT))

    def test_translator_falls_back(self):
        from musictools.gui_texts import make_translator
        self.assertEqual(make_translator("it")("btn_stop"), "Ferma")
        self.assertEqual(make_translator("xx")("btn_stop"), "Stop")
        self.assertIn("7", make_translator("en")("st_error", code=7))


if __name__ == "__main__":
    unittest.main()
