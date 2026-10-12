# Third-party software

musictools is licensed under GPL-3.0-or-later (see `LICENSE`). It uses:

- **mutagen** - GPL-2.0-or-later - https://github.com/quodlibet/mutagen
- **customtkinter** - MIT - https://github.com/TomSchimansky/CustomTkinter
- **Pillow** - MIT-CMU (HPND) - https://python-pillow.org/
- **PyInstaller** (only to build `musictools.exe`) - GPL-2.0-or-later with a bootloader exception - https://pyinstaller.org/
- **Chromaprint / fpcalc** (optional, a separate program that is not included) - LGPL-2.1 - https://acoustid.org/chromaprint

`musictools.exe` is a bundle of musictools, the Python runtime and the libraries above. The source code of
musictools for each version is the tag of the same name in this repository
(https://github.com/Dig3343/music-tag-tools). The other libraries are available from the links above.

Online services used: MusicBrainz, Cover Art Archive, LRCLIB and AcoustID, each under its own terms.
