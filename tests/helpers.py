"""Minimal test data (an empty mp3 and three differently coloured JPEGs) and helper functions."""

import base64
import shutil
import tempfile
from pathlib import Path

from mutagen.id3 import APIC, ID3
from mutagen.mp3 import EasyMP3

T_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//MgxAAAAANIAAAAAExBTUUzLjEwMFVVVVVVVVVVVVVVTEFNRTMuMTAwVVVVVVVVVVVVVf/zIsQnAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVVV//MgxE8AAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zIMR2AAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/8yDEnQAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//MixMQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/8yDE2AAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//MgxNgAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQ=="
)
RED_JPG = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABNAAEBAAAAAAAAAAAAAAAAAAAABgEBAQEAAAAAAAAAAAAAAAAAAAYHEAEAAAAAAAAAAAAAAAAAAAAAEQEAAAAAAAAAAAAAAAAAAAAA/8AAEQgAIAAgAwEiAAIRAAMRAP/aAAwDAQACEQMRAD8AiwEo38AAAAAB/9k="
)
BLUE_JPG = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABNAAEBAAAAAAAAAAAAAAAAAAAABwEBAQEAAAAAAAAAAAAAAAAAAAUHEAEAAAAAAAAAAAAAAAAAAAAAEQEAAAAAAAAAAAAAAAAAAAAA/8AAEQgAIAAgAwEiAAIRAAMRAP/aAAwDAQACEQMRAD8AjgDf0sAAAAAB/9k="
)
GREEN_JPG = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABMAAEBAAAAAAAAAAAAAAAAAAAABgEBAQAAAAAAAAAAAAAAAAAAAAYQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCAAgACADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCLASqJAAAAAAf/2Q=="
)


def make_track(folder, name, **tags):
    """Create an mp3 in 'folder' with the given tags (title, artist, album, albumartist, tracknumber, discnumber...)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(T_MP3)
    audio = EasyMP3(path)
    if audio.tags is None:
        audio.add_tags()
    for key, value in tags.items():
        audio[key] = [value]
    audio.save(v2_version=3)
    return path


def set_cover(path, data, v2_version=3):
    tags = ID3(path)
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=data))
    tags.save(path, v2_version=v2_version)


def cover_of(path):
    pics = ID3(path).getall("APIC")
    return pics[0].data if pics else None


class TempDir:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        return Path(self.tmp)

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)

