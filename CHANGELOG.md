# Changelog

## 1.1.0
- `online`: albums are grouped by folder and title, so guest artists or different capitalization of the artist no longer split an album.
- `online`: releases with fewer tracks than yours, or whose tracks don't fit yours (another edition), are skipped and listed instead of guessed; `--verbose` explains every rejection.
- `online`: new `--match tags|audio|both` switch (audio fingerprint through AcoustID; newer and less tested).
- `online`: warns when some online requests were refused.
- Reports: saved in a `_reports` folder inside your music folder; Excel opens the columns correctly; a report open in Excel no longer crashes the program.
- Start menu when run without arguments, clear PREVIEW / APPLY messages and a "did you back up?" confirmation.
- English documentation, plus `README.txt`.

## 1.0.0
- First release: `tags`, `covers`, `id3v23` and `online` (metadata, covers, lyrics).
