# SPDX-License-Identifier: GPL-3.0-or-later
"""All texts shown in the window, in English and Italian (the log of the commands stays in English)."""

import os
import sys

LANGUAGES = ("it", "en")


def detect_language():
    """Italian if the system is set to Italian, English otherwise."""
    try:
        if sys.platform.startswith("win"):
            import ctypes
            return "it" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF == 0x10 else "en"
    except Exception:
        pass
    for name in ("LC_ALL", "LANG", "LANGUAGE"):
        if os.environ.get(name, "").lower().startswith("it"):
            return "it"
    return "en"


def make_translator(lang):
    table = TEXTS.get(lang, TEXTS["en"])

    def t(key, **fmt):
        text = table.get(key) or TEXTS["en"].get(key, key)
        return text.format(**fmt) if fmt else text
    return t


EN = {
    # window
    "app_subtitle": "Tidy up your mp3 / flac library",
    "btn_help": "Instructions",
    "folder_label": "Your music folder",
    "folder_hint": "Paste a path or press Browse",
    "browse": "Browse...",
    "choose_folder_title": "Choose your music folder",
    # tabs
    "tab_start": "Start",
    "tab_tags": "Tags",
    "tab_online": "Online",
    "tab_covers": "Covers",
    "tab_id3v23": "Windows covers",
    "sub_what": "What to do",
    "sub_match": "Recognition",
    "sub_more": "More",
    # start tab
    "start_title": "Welcome! Three simple rules",
    "start_rules": ("1. Always press Preview first: it only shows what WOULD change.\n"
                    "2. Look at the results below. If it looks right, press Apply changes.\n"
                    "3. Back up your music before applying."),
    "start_steps": "Suggested order, from top to bottom:",
    "step_tags": "Fix artist / album artist / album names and find duplicates.",
    "step_online": "Fill in missing info, covers and lyrics from the internet.",
    "step_covers": "Find missing or broken covers and copy them from the same album.",
    "step_id3v23": "Make covers show up in Windows Explorer and Media Player.",
    "open_step": "Open",
    # tags tab
    "desc_tags": "Makes artist, album artist and album consistent inside each album, and finds duplicate files.",
    "o_no_auto": "Only my rules, no guesses",
    "h_no_auto": "Skip the automatic decisions; only apply your rules file and unify album titles.",
    "o_no_feat": "Keep guests out of the title",
    "h_no_feat": "Don't move guest artists (feat.) into the track title.",
    "o_keep_comp": "Keep artists in compilations",
    "h_keep_comp": "In compilations keep each track's artist; only set 'album artist' and the compilation flag.",
    "o_split_comma": "Commas and & separate artists",
    "h_split_comma": "Careful with names like 'Earth, Wind & Fire'.",
    "o_move_dupes": "Move exact duplicates away",
    "h_move_dupes": "On Apply, moves identical files to a '_duplicates' folder (nothing is deleted).",
    "o_verbose_tags": "Explain every decision",
    "h_verbose": "Writes the reason for each album in the log.",
    "o_ratio": "Main artist share (0-1)",
    "h_ratio": "Share of tracks by the same artist needed to call the album 'by one artist'. Below it, it's a compilation. Default 0.6.",
    "o_rules": "Rules file (optional)",
    "h_rules": "Your own JSON file with per-album rules (see rules.example.json).",
    # online tab
    "desc_online": "Uses the internet (MusicBrainz, Cover Art Archive, LRCLIB). It can take a while: be patient.",
    "o_metadata": "Fill missing info",
    "h_metadata": "Year, genre, track and disc numbers, from MusicBrainz.",
    "o_covers": "Download missing covers",
    "h_covers": "Only for albums that have no cover.",
    "o_lyrics": "Add lyrics",
    "h_lyrics": "Looks them up on LRCLIB and embeds them in the files.",
    "o_lrc": "Also save .lrc files",
    "h_lrc": "Synced lyrics saved next to each track (some players need them as separate files).",
    "o_overwrite": "Replace existing values",
    "h_overwrite": "Also replaces title, date, genre, numbers and lyrics. Artist and album artist are never touched.",
    "o_no_cache": "Ignore saved answers",
    "h_no_cache": "Ask the internet again instead of reusing previous answers.",
    "o_verbose_online": "Explain every decision",
    "match_label": "How should tracks be recognized?",
    "match_tags": "tags",
    "match_audio": "audio",
    "match_both": "both",
    "match_help": ("tags: fast, but wrong tags can give wrong results.\n"
                   "audio: audio fingerprint, slower but the safest. Needs fpcalc and an AcoustID key.\n"
                   "both: fingerprint first, tags as a fallback."),
    "o_key": "AcoustID key",
    "h_key": "Free key from acoustid.org (only for audio / both).",
    "o_fpcalc": "fpcalc program",
    "h_fpcalc": "Path to fpcalc.exe (only for audio / both). Leave empty if it is in your PATH.",
    "o_contact": "Your email (optional)",
    "h_contact": "MusicBrainz likes to know who is asking.",
    "o_cover_size": "Cover size (pixels)",
    "h_cover_size": "250, 500 or 1200. Bigger covers use more space.",
    # covers tab
    "desc_covers": "Checks the covers embedded in your files. Choose what to do:",
    "c_fix": "Fix missing or broken covers",
    "c_fix_h": "Copies the album's cover onto tracks that have none or a broken one.",
    "c_unify": "Fix and make covers equal on each disc",
    "c_unify_h": "Also replaces valid but different covers within a disc.",
    "c_export": "Export different covers to compare",
    "c_export_h": "Saves images in the reports folder to compare them by eye. Changes nothing.",
    "c_inspect": "Inspect the files (ONE album folder)",
    "c_inspect_h": "Shows what is inside each file. Changes nothing.",
    "c_set": "Put my own image on some tracks (ONE album folder)",
    "c_set_h": "Choose the image, and optionally which tracks or disc.",
    "o_image": "Image (jpg / png)",
    "o_from": "from track",
    "o_to": "to track",
    "o_disc": "disc",
    # id3v23 tab
    "desc_id3v23": "Converts tags to ID3v2.3 so covers show up in Windows Explorer and Media Player.",
    "id3v23_nothing": "Nothing to choose: pick the folder and press Preview.",
    # bottom panel
    "bt_results": "Results",
    "bt_tracks": "Tracks",
    "bt_log": "Log",
    "res_empty": "Run a Preview to see here what would change.",
    "res_nothing": "Nothing to change: your files are already fine.",
    "res_no_table": "This action has no table of changes: see the Log tab.",
    "res_changes": "changes",
    "res_files": "files",
    "res_mode_preview": "Preview",
    "res_mode_applied": "Applied",
    "res_title_preview": "What would change",
    "res_title_applied": "What was changed",
    "col_file": "File", "col_field": "Field", "col_before": "Before", "col_after": "After", "col_reason": "Reason",
    "col_kind": "Kind", "col_source": "Source", "col_album artist": "Album artist", "col_album": "Album",
    "col_action": "Action", "col_problem": "Problem", "col_version before": "Before", "col_version after": "After",
    "col_cover": "Cover", "col_num": "#", "col_title": "Title", "col_artist": "Artist",
    "col_albumartist": "Album artist", "col_lyrics": "Lyrics", "col_format": "Format / ID3",
    "tr_search": "Search title, artist, album...",
    "tr_f_all": "All tracks", "tr_f_cover": "Without cover", "tr_f_lyrics": "Without lyrics",
    "tr_f_albumartist": "Without album artist",
    "tr_reload": "Reload",
    "tr_empty": "Choose a music folder to see its tracks here.",
    "lib_reading": "Reading tracks... {done} / {total}",
    "lib_summary": "{shown} of {tracks} tracks  |  {no_cover} without cover  |  {no_lyrics} without lyrics  |  {no_albumartist} without album artist",
    # actions
    "btn_preview": "Preview (changes nothing)",
    "btn_apply": "Apply changes",
    "btn_stop": "Stop",
    "btn_reports": "Open reports folder",
    "log_title": "Log",
    "log_intro": ("Choose your music folder, pick a tab and press Preview.\n"
                  "Nothing is changed until you press Apply and confirm.\n"),
    "st_ready": "Ready. Start with a preview: it never changes your files.",
    "st_preview": "Preview running... (this can take a while)",
    "st_apply": "Applying changes... (this can take a while)",
    "st_done": "Finished.",
    "st_stopped": "Stopped.",
    "st_error": "Finished with an error (code {code}).",
    "dlg_apply_title": "Apply changes",
    "dlg_apply_text": "This will change your files.\n\nDid you back up your music?\n\nContinue?",
    "dlg_no_reports": "No reports yet: run a preview first.",
    "dlg_cannot_start": "Could not start: {error}",
    # argument errors
    "e_start": "Open one of the tabs (Tags, Online, Covers, Windows covers) first.",
    "e_folder": "Choose your music folder first.",
    "e_ratio": "The main artist share must be a number between 0 and 1.",
    "e_online_none": "Tick at least one of: fill missing info, covers, lyrics.",
    "e_key": "Audio recognition needs your free AcoustID key (see the Instructions).",
    "e_image": "Choose the image file to use as cover.",
    "e_int": "Track and disc numbers must be whole numbers.",
    # instructions window
    "help_title": "Instructions",
    "help_close": "Close",
    "help_readme": "Open the full README online",
    "help_text": """\
QUICK START
1. Press Browse and choose the folder with your music (it can be the main folder: subfolders are included).
2. Pick a tab (go in order, from left to right) and press Preview.
3. Look at the Results tab on the right: it lists what would change. Nothing has been changed yet.
4. If it looks right, press Apply changes and confirm.

PREVIEW AND APPLY
- Preview never changes your files. It writes reports (CSV files you can open with Excel) in a folder called _reports inside your music folder.
- Apply changes really writes to your files. Back up your music first.
- Stop cancels the operation that is running.
- Open reports folder opens the _reports folder.

TAGS TAB
Makes artist, album artist and album consistent inside every album and finds duplicates.
- Only my rules, no guesses: apply only your rules file and unify album titles.
- Keep guests out of the title: don't move "feat." artists into the title.
- Keep artists in compilations: leave each track's artist; only set album artist and the compilation flag.
- Commas and & separate artists: treat "A, B & C" as three artists (careful with "Earth, Wind & Fire").
- Move exact duplicates away: on Apply, identical files go to a _duplicates folder. Nothing is deleted.
- Explain every decision: shows the reason for each album in the log.
- Main artist share: how many tracks must share the same artist for the album to count as "by one artist" (default 0.6). Below that, it is a compilation.
- Rules file: your own JSON file with per-album rules (see rules.example.json in the project).

ONLINE TAB
Looks things up on the internet. Be patient: it asks one request per second.
- Fill missing info: year, genre, track and disc numbers (MusicBrainz).
- Download missing covers: only for albums without a cover (Cover Art Archive).
- Add lyrics: from LRCLIB, embedded in the file. With "Also save .lrc files" it also writes synced lyrics next to each track.
- Replace existing values: also replaces title, date, genre, numbers and lyrics. Artist and album artist are never changed.
- Ignore saved answers: don't reuse answers from previous runs.
- Recognition tab: how tracks are identified.
  tags = fast but depends on how clean your tags are.
  audio = audio fingerprint: slower but safest.
  both = fingerprint first, tags as a fallback.
  Audio and both need two things: the fpcalc program (download "Chromaprint" from acoustid.org/chromaprint, extract fpcalc.exe and choose it in the window) and a free AcoustID key (register an application at acoustid.org/new-application).
- More tab: your email (MusicBrainz likes to know who is asking), cover size and extra options.
- If an album is not recognized it is listed at the end of the log: fix its tags in the Tags tab, or use audio recognition.

COVERS TAB
- Fix missing or broken covers: copies the album's cover to tracks that lack it.
- Fix and make covers equal on each disc: also replaces valid but different covers.
- Export different covers to compare: saves images so you can compare them by eye. Changes nothing.
- Inspect the files: shows what is inside each file. Use it on ONE album folder.
- Put my own image on some tracks: choose a jpg/png and, if you want, from/to track number and disc. Use it on ONE album folder.

WINDOWS COVERS TAB
Converts tags to ID3v2.3, the version Windows Explorer and Media Player understand, so covers show up there.

RESULTS, TRACKS AND LOG (right side)
- Results: after a Preview or Apply, a table lists every change: file, field, before and after (and the reason). The cards on top count the changes and the files involved. This table comes from the CSV report, which you can also open with Excel.
- Tracks: all the tracks of your folder, with a small cover, number, title, artist, album, album artist, whether it has lyrics, and the format (for mp3, the ID3 version). Type in the search box or use the filter to see only tracks without cover, lyrics or album artist. Click a column title to sort. It refreshes by itself after Apply; "Reload" reads the folder again.
- Log: the raw text of the program, in case you need the details.

LANGUAGE
The IT / EN button at the top changes the language of the window. The log of the commands stays in English.

LICENSE
musictools is free software (GPL-3.0-or-later). See LICENSE and THIRD_PARTY.md.

SETTINGS
The window remembers your folder, rules file, AcoustID key, fpcalc path, email and language in a plain-text file called .musictools_gui.json in your user folder. Delete it to forget them.
""",
}

IT = {
    "app_subtitle": "Metti in ordine la tua libreria mp3 / flac",
    "btn_help": "Istruzioni",
    "folder_label": "La tua cartella di musica",
    "folder_hint": "Incolla un percorso o premi Sfoglia",
    "browse": "Sfoglia...",
    "choose_folder_title": "Scegli la cartella della tua musica",
    "tab_start": "Inizio",
    "tab_tags": "Tag",
    "tab_online": "Online",
    "tab_covers": "Copertine",
    "tab_id3v23": "Copertine Windows",
    "sub_what": "Cosa fare",
    "sub_match": "Riconoscimento",
    "sub_more": "Altro",
    "start_title": "Benvenuto! Tre regole semplici",
    "start_rules": ("1. Premi sempre prima Anteprima: mostra solo cosa CAMBIEREBBE.\n"
                    "2. Guarda i risultati qui sotto. Se ti sembra giusto, premi Applica modifiche.\n"
                    "3. Fai una copia di sicurezza della musica prima di applicare."),
    "start_steps": "Ordine consigliato, dall'alto in basso:",
    "step_tags": "Sistema artista / artista dell'album / nome dell'album e trova i doppioni.",
    "step_online": "Completa informazioni mancanti, copertine e testi da internet.",
    "step_covers": "Trova copertine mancanti o rotte e le copia dallo stesso album.",
    "step_id3v23": "Fa vedere le copertine in Esplora file e in Windows Media Player.",
    "open_step": "Apri",
    "desc_tags": "Rende coerenti artista, artista dell'album e album dentro ogni album, e trova i file doppi.",
    "o_no_auto": "Solo le mie regole, niente decisioni automatiche",
    "h_no_auto": "Salta le scelte automatiche; applica solo il tuo file di regole e unifica i titoli degli album.",
    "o_no_feat": "Lascia gli ospiti fuori dal titolo",
    "h_no_feat": "Non sposta gli artisti ospiti (feat.) nel titolo del brano.",
    "o_keep_comp": "Mantieni gli artisti nelle compilation",
    "h_keep_comp": "Nelle compilation lascia l'artista di ogni brano; imposta solo 'artista dell'album' e il flag compilation.",
    "o_split_comma": "Virgole e & separano gli artisti",
    "h_split_comma": "Attenzione a nomi come 'Earth, Wind & Fire'.",
    "o_move_dupes": "Sposta i doppioni identici",
    "h_move_dupes": "Con Applica, sposta i file identici in una cartella '_duplicates' (non cancella nulla).",
    "o_verbose_tags": "Spiega ogni decisione",
    "h_verbose": "Scrive nel registro il motivo di ogni scelta per album.",
    "o_ratio": "Quota artista principale (0-1)",
    "h_ratio": "Quota di brani dello stesso artista per dire che l'album è 'di un solo artista'. Sotto questa soglia è una compilation. Predefinito 0,6.",
    "o_rules": "File di regole (facoltativo)",
    "h_rules": "Un tuo file JSON con regole per album (vedi rules.example.json).",
    "desc_online": "Usa internet (MusicBrainz, Cover Art Archive, LRCLIB). Può richiedere tempo: abbi pazienza.",
    "o_metadata": "Completa le informazioni mancanti",
    "h_metadata": "Anno, genere, numeri di traccia e di disco, da MusicBrainz.",
    "o_covers": "Scarica le copertine mancanti",
    "h_covers": "Solo per gli album senza copertina.",
    "o_lyrics": "Aggiungi i testi",
    "h_lyrics": "Li cerca su LRCLIB e li inserisce nei file.",
    "o_lrc": "Salva anche file .lrc",
    "h_lrc": "Testi sincronizzati accanto a ogni brano (alcuni lettori li vogliono come file separati).",
    "o_overwrite": "Sostituisci i valori esistenti",
    "h_overwrite": "Sostituisce anche titolo, data, genere, numeri e testi. Artista e artista dell'album non si toccano mai.",
    "o_no_cache": "Ignora le risposte salvate",
    "h_no_cache": "Interroga di nuovo internet invece di riusare le risposte precedenti.",
    "o_verbose_online": "Spiega ogni decisione",
    "match_label": "Come riconoscere i brani?",
    "match_tags": "tag",
    "match_audio": "audio",
    "match_both": "entrambi",
    "match_help": ("tag: veloce, ma tag sbagliati possono dare risultati sbagliati.\n"
                   "audio: impronta audio, più lento ma il più sicuro. Servono fpcalc e una chiave AcoustID.\n"
                   "entrambi: prima l'impronta audio, poi i tag come ripiego."),
    "o_key": "Chiave AcoustID",
    "h_key": "Chiave gratuita da acoustid.org (solo per audio / entrambi).",
    "o_fpcalc": "Programma fpcalc",
    "h_fpcalc": "Percorso di fpcalc.exe (solo per audio / entrambi). Lascia vuoto se è nel PATH.",
    "o_contact": "La tua email (facoltativa)",
    "h_contact": "A MusicBrainz piace sapere chi sta chiedendo.",
    "o_cover_size": "Dimensione copertine (pixel)",
    "h_cover_size": "250, 500 o 1200. Copertine più grandi occupano più spazio.",
    "desc_covers": "Controlla le copertine incorporate nei file. Scegli cosa fare:",
    "c_fix": "Ripara copertine mancanti o rotte",
    "c_fix_h": "Copia la copertina dell'album sui brani che non ce l'hanno o ce l'hanno rotta.",
    "c_unify": "Ripara e rendi uguali le copertine di ogni disco",
    "c_unify_h": "Sostituisce anche copertine valide ma diverse nello stesso disco.",
    "c_export": "Esporta le copertine diverse per confrontarle",
    "c_export_h": "Salva immagini nella cartella dei report per confrontarle a occhio. Non cambia nulla.",
    "c_inspect": "Ispeziona i file (UNA cartella di album)",
    "c_inspect_h": "Mostra cosa c'è dentro ogni file. Non cambia nulla.",
    "c_set": "Metti una mia immagine su alcuni brani (UNA cartella di album)",
    "c_set_h": "Scegli l'immagine e, se vuoi, quali brani o quale disco.",
    "o_image": "Immagine (jpg / png)",
    "o_from": "dal brano",
    "o_to": "al brano",
    "o_disc": "disco",
    "desc_id3v23": "Converte i tag in ID3v2.3 così le copertine si vedono in Esplora file e Windows Media Player.",
    "id3v23_nothing": "Niente da scegliere: seleziona la cartella e premi Anteprima.",
    # pannello in basso
    "bt_results": "Risultati",
    "bt_tracks": "Tracce",
    "bt_log": "Registro",
    "res_empty": "Fai un'Anteprima per vedere qui cosa cambierebbe.",
    "res_nothing": "Niente da cambiare: i tuoi file sono già a posto.",
    "res_no_table": "Questa azione non ha una tabella di modifiche: guarda la scheda Registro.",
    "res_changes": "modifiche",
    "res_files": "file",
    "res_mode_preview": "Anteprima",
    "res_mode_applied": "Applicato",
    "res_title_preview": "Cosa cambierebbe",
    "res_title_applied": "Cosa è stato modificato",
    "col_file": "File", "col_field": "Campo", "col_before": "Prima", "col_after": "Dopo", "col_reason": "Motivo",
    "col_kind": "Tipo", "col_source": "Fonte", "col_album artist": "Artista album", "col_album": "Album",
    "col_action": "Azione", "col_problem": "Problema", "col_version before": "Prima", "col_version after": "Dopo",
    "col_cover": "Copertina", "col_num": "#", "col_title": "Titolo", "col_artist": "Artista",
    "col_albumartist": "Artista album", "col_lyrics": "Testo", "col_format": "Formato / ID3",
    "tr_search": "Cerca titolo, artista, album...",
    "tr_f_all": "Tutte le tracce", "tr_f_cover": "Senza copertina", "tr_f_lyrics": "Senza testo",
    "tr_f_albumartist": "Senza artista album",
    "tr_reload": "Ricarica",
    "tr_empty": "Scegli una cartella di musica per vedere qui le tracce.",
    "lib_reading": "Leggo le tracce... {done} / {total}",
    "lib_summary": "{shown} di {tracks} tracce  |  {no_cover} senza copertina  |  {no_lyrics} senza testo  |  {no_albumartist} senza artista album",
    "btn_preview": "Anteprima (non cambia nulla)",
    "btn_apply": "Applica modifiche",
    "btn_stop": "Ferma",
    "btn_reports": "Apri cartella report",
    "log_title": "Registro",
    "log_intro": ("Scegli la cartella della musica, apri una scheda e premi Anteprima.\n"
                  "Non cambia nulla finché non premi Applica e confermi.\n"),
    "st_ready": "Pronto. Comincia con un'anteprima: non cambia mai i tuoi file.",
    "st_preview": "Anteprima in corso... (può richiedere tempo)",
    "st_apply": "Applico le modifiche... (può richiedere tempo)",
    "st_done": "Finito.",
    "st_stopped": "Fermato.",
    "st_error": "Terminato con un errore (codice {code}).",
    "dlg_apply_title": "Applica modifiche",
    "dlg_apply_text": "Questo modificherà i tuoi file.\n\nHai fatto una copia di sicurezza della musica?\n\nContinuare?",
    "dlg_no_reports": "Ancora nessun report: fai prima un'anteprima.",
    "dlg_cannot_start": "Impossibile avviare: {error}",
    "e_start": "Apri prima una delle schede (Tag, Online, Copertine, Copertine Windows).",
    "e_folder": "Scegli prima la cartella della musica.",
    "e_ratio": "La quota dell'artista principale deve essere un numero tra 0 e 1.",
    "e_online_none": "Spunta almeno una voce: informazioni mancanti, copertine, testi.",
    "e_key": "Il riconoscimento audio richiede la tua chiave AcoustID gratuita (vedi Istruzioni).",
    "e_image": "Scegli il file immagine da usare come copertina.",
    "e_int": "I numeri di brano e di disco devono essere numeri interi.",
    "help_title": "Istruzioni",
    "help_close": "Chiudi",
    "help_readme": "Apri il README completo online",
    "help_text": """\
PER COMINCIARE
1. Premi Sfoglia e scegli la cartella con la tua musica (può essere la cartella principale: le sottocartelle sono incluse).
2. Apri una scheda (vai in ordine, da sinistra a destra) e premi Anteprima.
3. Guarda la scheda Risultati a destra: elenca cosa cambierebbe. Finora non è stato cambiato nulla.
4. Se ti sembra giusto, premi Applica modifiche e conferma.

ANTEPRIMA E APPLICA
- L'anteprima non cambia mai i tuoi file. Scrive dei report (file CSV da aprire con Excel) in una cartella chiamata _reports dentro la cartella della musica.
- Applica modifiche scrive davvero nei tuoi file. Fai prima una copia di sicurezza.
- Ferma interrompe l'operazione in corso.
- Apri cartella report apre la cartella _reports.

SCHEDA TAG
Rende coerenti artista, artista dell'album e album dentro ogni album e trova i doppioni.
- Solo le mie regole, niente decisioni automatiche: applica solo il tuo file di regole e unifica i titoli degli album.
- Lascia gli ospiti fuori dal titolo: non sposta gli artisti "feat." nel titolo.
- Mantieni gli artisti nelle compilation: lascia l'artista di ogni brano; imposta solo l'artista dell'album e il flag compilation.
- Virgole e & separano gli artisti: "A, B & C" diventa tre artisti (attenzione a "Earth, Wind & Fire").
- Sposta i doppioni identici: con Applica, i file identici vanno in una cartella _duplicates. Non si cancella nulla.
- Spiega ogni decisione: mostra nel registro il motivo di ogni scelta per album.
- Quota artista principale: quanti brani devono avere lo stesso artista perché l'album sia "di un solo artista" (predefinito 0,6). Sotto, è una compilation.
- File di regole: un tuo file JSON con regole per album (vedi rules.example.json nel progetto).

SCHEDA ONLINE
Cerca informazioni su internet. Abbi pazienza: fa una richiesta al secondo.
- Completa le informazioni mancanti: anno, genere, numeri di traccia e di disco (MusicBrainz).
- Scarica le copertine mancanti: solo per gli album senza copertina (Cover Art Archive).
- Aggiungi i testi: da LRCLIB, inseriti nel file. Con "Salva anche file .lrc" scrive anche i testi sincronizzati accanto a ogni brano.
- Sostituisci i valori esistenti: sostituisce anche titolo, data, genere, numeri e testi. Artista e artista dell'album non cambiano mai.
- Ignora le risposte salvate: non riusa le risposte delle esecuzioni precedenti.
- Scheda Riconoscimento: come vengono identificati i brani.
  tag = veloce ma dipende da quanto sono puliti i tuoi tag.
  audio = impronta audio: più lento ma il più sicuro.
  entrambi = prima l'impronta audio, poi i tag come ripiego.
  Audio ed entrambi richiedono due cose: il programma fpcalc (scarica "Chromaprint" da acoustid.org/chromaprint, estrai fpcalc.exe e sceglilo nella finestra) e una chiave AcoustID gratuita (registra un'applicazione su acoustid.org/new-application).
- Scheda Altro: la tua email (a MusicBrainz piace sapere chi chiede), dimensione delle copertine e opzioni extra.
- Se un album non viene riconosciuto compare in fondo al registro: sistema i suoi tag nella scheda Tag, oppure usa il riconoscimento audio.

SCHEDA COPERTINE
- Ripara copertine mancanti o rotte: copia la copertina dell'album sui brani che ne sono privi.
- Ripara e rendi uguali le copertine di ogni disco: sostituisce anche copertine valide ma diverse.
- Esporta le copertine diverse per confrontarle: salva le immagini per confrontarle a occhio. Non cambia nulla.
- Ispeziona i file: mostra cosa c'è dentro ogni file. Usalo su UNA cartella di album.
- Metti una mia immagine su alcuni brani: scegli un jpg/png e, se vuoi, dal/al numero di brano e il disco. Usalo su UNA cartella di album.

SCHEDA COPERTINE WINDOWS
Converte i tag in ID3v2.3, la versione che Esplora file e Windows Media Player capiscono, così le copertine si vedono.

RISULTATI, TRACCE E REGISTRO (lato destro)
- Risultati: dopo un'Anteprima o un'Applicazione, una tabella elenca ogni modifica: file, campo, prima e dopo (e il motivo). Le schede in alto contano le modifiche e i file coinvolti. La tabella viene dal report CSV, che puoi aprire anche con Excel.
- Tracce: tutte le tracce della tua cartella, con copertina in miniatura, numero, titolo, artista, album, artista dell'album, se hanno il testo e il formato (per gli mp3, la versione ID3). Scrivi nella casella di ricerca o usa il filtro per vedere solo le tracce senza copertina, testo o artista dell'album. Clicca sul titolo di una colonna per ordinare. Si aggiorna da solo dopo Applica; "Ricarica" rilegge la cartella.
- Registro: il testo grezzo del programma, se ti servono i dettagli.

LINGUA
Il pulsante IT / EN in alto cambia la lingua della finestra. Il registro dei comandi resta in inglese.

LICENZA
musictools è software libero (GPL-3.0-or-later). Vedi LICENSE e THIRD_PARTY.md.

IMPOSTAZIONI
La finestra ricorda cartella, file di regole, chiave AcoustID, percorso di fpcalc, email e lingua in un file di testo chiamato .musictools_gui.json nella tua cartella utente. Cancellalo per dimenticarli.
""",
}

TEXTS = {"en": EN, "it": IT}
