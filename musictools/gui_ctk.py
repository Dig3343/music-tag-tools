# SPDX-License-Identifier: GPL-3.0-or-later
"""Window for musictools, built with customtkinter (pip install customtkinter).

It builds the same command line you would type, runs it in the background and shows the output
live. Preview is the default; Apply asks for confirmation. Italian / English with one button.
"""

import io
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
try:
    from PIL import Image, ImageOps, ImageTk      # for the small covers in the Tracks table
except ImportError:                              # the table still works, without pictures
    Image = ImageOps = ImageTk = None

from . import __version__, gui_data
from .common import default_out_dir
from .gui import (ArgError, build_args, command_for, load_config, open_in_file_manager, process_cwd,
                  reports_folder, save_config, set_app_id, set_window_icon)
from .gui_texts import LANGUAGES, detect_language, make_translator

ACCENT = "#2f6fed"
GRAY = ("gray35", "gray65")
README_URL = "https://github.com/Dig3343/music-tag-tools#readme"
TAB_ORDER = ("start", "tags", "online", "covers", "id3v23")
BOTTOM_ORDER = ("results", "tracks", "log")
TRACK_COLUMNS = ("num", "title", "artist", "album", "albumartist", "lyrics", "format")
TRACK_WIDTHS = {"num": 48, "title": 220, "artist": 170, "album": 190, "albumartist": 160, "lyrics": 190, "format": 120}
FILTERS = ("", "cover", "lyrics", "albumartist")
IMAGE_TYPES = [("Images", "*.jpg *.jpeg *.png"), ("*", "*.*")]


def run_gui():
    config = load_config()
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    set_app_id()                                    # own taskbar icon on Windows
    root = ctk.CTk()
    root.title(f"musictools {__version__}")
    try:                                            # Windows display scaling (125%, 150%...); 1.0 elsewhere
        sc = float(ctk.ScalingTracker.get_window_scaling(root))
    except Exception:
        sc = 1.0
    sc = max(1.0, sc)
    # Tk window geometry uses screen pixels directly; only CustomTkinter widgets
    # are scaled. Dividing the screen size by `sc` makes the whole window too small.
    usable_w, usable_h = root.winfo_screenwidth() - 30, root.winfo_screenheight() - 80
    root.geometry(f"{min(1320, usable_w)}x{min(840, usable_h)}")
    root.minsize(min(1000, usable_w), min(600, usable_h))

    def px(value):                                  # size for plain tkinter widgets, which customtkinter does not scale
        return int(round(value * sc))
    for delay in (250, 900):                           # customtkinter sets its own icon late on Windows
        root.after(delay, lambda: set_window_icon(root))
    mono = ctk.CTkFont(family="Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono", size=12)
    bold = ctk.CTkFont(weight="bold")
    title_font = ctk.CTkFont(size=22, weight="bold")
    
    lang = config.get("lang")
    state = {"proc": None, "queue": queue.Queue(), "stopped": False,
             "lang": lang if lang in LANGUAGES else detect_language(),
             "status": ("st_ready", {}), "tab": "start", "help": None, "shell": None,
             "bottom": "tracks", "tracks": [], "tracks_folder": "", "scan_id": 0, "scan_q": queue.Queue(),
             "photos": {}, "result": None, "run": None, "filter": "", "sort": ("", False), "render_id": 0,
             "scan_status": None, "search": "", "left_w": px(480)}
    ui = {}                                           # widgets that other functions need

    # ---- values (created once, so they survive a language change)
    S = ctk.StringVar
    B = ctk.BooleanVar
    var = {
        "folder": S(value=config.get("folder", "")),
        "ratio": S(value="0.6"), "rules": S(value=config.get("rules", "")),
        "match": S(value=config.get("match", "tags")), "key": S(value=config.get("key", "")),
        "fpcalc": S(value=config.get("fpcalc", "")), "contact": S(value=config.get("contact", "")),
        "cover_size": S(value="500"), "covers_mode": S(value="fix"), "image": S(),
        "from": S(), "to": S(), "disc": S(),
    }
    tags_flags = {k: B(value=False) for k in ("no_auto", "no_feat", "keep_comp", "split_comma", "move_dupes", "verbose")}
    online_flags = {k: B(value=v) for k, v in (("metadata", True), ("covers", True), ("lyrics", True), ("lrc", False),
                                               ("overwrite", False), ("no_cache", False), ("verbose", False))}
    status_var = S()

    def t(key, **fmt):
        return make_translator(state["lang"])(key, **fmt)

    def set_status(key, **fmt):
        state["status"] = (key, fmt)
        status_var.set(t(key, **fmt))

    class RoundedTabView(ctk.CTkFrame):
        """Tab container with a full-width row of independent rounded buttons."""

        def __init__(self, parent, command=None):
            colors = ctk.ThemeManager.theme
            frame_color = colors["CTkFrame"]["fg_color"]
            super().__init__(parent, fg_color=frame_color, corner_radius=15, border_width=0)
            self._command = command
            self._pages = {}
            self._buttons = {}
            self._current = ""

            self._bar = ctk.CTkFrame(
                self, fg_color=colors["CTkSegmentedButton"]["fg_color"], corner_radius=10
            )
            self._bar.pack(fill="x", padx=10, pady=(10, 0))
            self._content = ctk.CTkFrame(
                self, fg_color=frame_color, corner_radius=0, border_width=0
            )
            self._content.pack(fill="both", expand=True, padx=10, pady=(6, 10))

            self._selected_color = colors["CTkSegmentedButton"]["selected_color"]
            self._selected_hover = colors["CTkSegmentedButton"]["selected_hover_color"]
            self._unselected_hover = colors["CTkSegmentedButton"]["unselected_hover_color"]
            self._text_color = colors["CTkSegmentedButton"]["text_color"]

        def add(self, name):
            page = ctk.CTkFrame(self._content, fg_color="transparent", corner_radius=0, border_width=0)
            self._pages[name] = page
            index = len(self._buttons)
            self._bar.grid_columnconfigure(index, weight=1, uniform="tabs")
            button = ctk.CTkButton(
                self._bar,
                text=name,
                width=0,
                height=32,
                corner_radius=8,
                border_width=0,
                fg_color="transparent",
                hover_color=self._unselected_hover,
                text_color=self._text_color,
                command=lambda tab=name: self._select(tab, notify=True),
            )
            button.grid(row=0, column=index, sticky="ew", padx=2, pady=2)
            self._buttons[name] = button
            if not self._current:
                self._select(name)
            return page

        def _select(self, name, notify=False):
            if name not in self._pages:
                return
            if self._current in self._pages:
                self._pages[self._current].pack_forget()
            self._current = name
            self._pages[name].pack(fill="both", expand=True)
            for tab_name, button in self._buttons.items():
                selected = tab_name == name
                button.configure(
                    fg_color=self._selected_color if selected else "transparent",
                    hover_color=self._selected_hover if selected else self._unselected_hover,
                )
            if notify and self._command is not None:
                self._command()

        def set(self, name):
            self._select(name)

        def get(self):
            return self._current

    def tabview(parent, **kwargs):
        return RoundedTabView(parent, command=kwargs.get("command"))

    # ------------------------------------------------------------------ building ---
    def build():
        old_log = ""
        if state["shell"] is not None:
            try:
                old_log = ui["log"].get("1.0", "end").rstrip("\n")
            except Exception:
                pass
            try:
                state["left_w"] = ui["paned"].sash_coord(0)[0]
            except Exception:
                pass
            state["shell"].destroy()
        shell = ctk.CTkFrame(root, fg_color="transparent")
        shell.pack(fill="both", expand=True)
        state["shell"] = shell

        # header
        head = ctk.CTkFrame(shell, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 0))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text=f"musictools  {__version__}", font=title_font).pack(anchor="w")
        lang_btn = ctk.CTkSegmentedButton(head, values=["IT", "EN"], width=110, command=change_language)
        lang_btn.set(state["lang"].upper())
        lang_btn.pack(side="right")
        ctk.CTkButton(head, text=t("btn_help"), width=100, command=show_help).pack(side="right", padx=(0, 10))

        # folder
        top = ctk.CTkFrame(shell, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(top, text=t("folder_label"), font=bold).pack(anchor="w")
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        folder_entry = ctk.CTkEntry(row, textvariable=var["folder"])
        folder_entry.pack(side="left", fill="x", expand=True)
        folder_entry.bind("<Return>", lambda _e: start_scan())
        folder_entry.bind("<FocusOut>", lambda _e: start_scan())
        ctk.CTkButton(row, text=t("browse"), width=110, command=browse_folder).pack(side="left", padx=(8, 0))

        # two panes: settings on the left, results on the right (drag the bar between them)
        paned = tk.PanedWindow(shell, orient="horizontal", sashwidth=px(10), sashrelief="flat", bd=0,
                               bg=root._apply_appearance_mode(root.cget("fg_color")), opaqueresize=True)
        paned.pack(fill="both", expand=True, padx=12, pady=(10, 12))
        ui["paned"] = paned
        left = ctk.CTkFrame(paned, fg_color="transparent")
        right = ctk.CTkFrame(paned, fg_color="transparent")
        paned.add(left, minsize=px(400), width=state["left_w"], stretch="never")
        paned.add(right, minsize=px(420), stretch="always")

        # left: tabs with the settings
        tabs = tabview(left, command=lambda: state.update(tab=current_key()))
        tabs.pack(fill="both", expand=True)
        ui["tabs"] = tabs
        ui["tab_names"] = {key: t("tab_" + key) for key in TAB_ORDER}
        pages = {key: tabs.add(ui["tab_names"][key]) for key in TAB_ORDER}
        build_start(scrolling(pages["start"]))
        build_tags(scrolling(pages["tags"]))
        build_online(pages["online"])
        build_covers(scrolling(pages["covers"]))
        build_id3v23(scrolling(pages["id3v23"]))
        tabs.set(ui["tab_names"][state["tab"]])

        # left: actions
        bar = ctk.CTkFrame(left, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 0))
        bar.columnconfigure((0, 1), weight=1, uniform="buttons")
        ui["preview"] = ctk.CTkButton(bar, text=t("btn_preview"), command=lambda: start(False))
        ui["apply"] = ctk.CTkButton(bar, text=t("btn_apply"), fg_color="#c0392b", hover_color="#962d22",
                                    command=lambda: start(True))
        ui["stop"] = ctk.CTkButton(bar, text=t("btn_stop"), fg_color="#b8860b", hover_color="#946b08",
                                   text_color="white", text_color_disabled="white",
                                   command=stop, state="disabled")
        reports = ctk.CTkButton(bar, text=t("btn_reports"), fg_color="transparent", border_width=1,
                                text_color=("gray10", "gray90"), command=open_reports)
        ui["preview"].grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        ui["apply"].grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        ui["stop"].grid(row=1, column=0, sticky="ew", padx=(0, 4))
        reports.grid(row=1, column=1, sticky="ew", padx=(4, 0))
        ui["progress"] = ctk.CTkProgressBar(left, mode="determinate")
        ui["progress"].pack(fill="x", pady=(12, 0))
        ui["progress"].set(0)
        ctk.CTkLabel(left, textvariable=status_var, anchor="w", justify="left", wraplength=400).pack(
            fill="x", pady=(6, 0))

        # right: results, tracks, log
        bottom = tabview(right, command=lambda: state.update(bottom=current_bottom()))
        bottom.pack(fill="both", expand=True, padx=(4, 0))
        ui["bottom"] = bottom
        ui["bottom_names"] = {key: t("bt_" + key) for key in BOTTOM_ORDER}
        bpages = {key: bottom.add(ui["bottom_names"][key]) for key in BOTTOM_ORDER}
        build_results(bpages["results"])
        build_tracks(bpages["tracks"])
        log = ctk.CTkTextbox(bpages["log"], font=mono, wrap="word", state="disabled")
        log.pack(fill="both", expand=True)
        log.tag_config("head", foreground=ACCENT)
        log.tag_config("warn", foreground="#d64545")
        ui["log"] = log
        log.configure(state="normal")
        if old_log:
            log.insert("end", old_log + "\n")
        log.configure(state="disabled")
        bottom.set(ui["bottom_names"][state["bottom"]])
        render_results()
        render_tracks()

        set_status(state["status"][0], **state["status"][1])
        set_running(state["proc"] is not None and state["proc"].poll() is None)

    def scrolling(page):
        frame = ctk.CTkScrollableFrame(page, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        return frame

    # every option uses two grid rows: the control (row*2) and its hint underneath (row*2+1)
    def hint(parent, row, key):
        # Keep only the few quick notes that help with optional, less obvious fields.
        if key not in {"h_rules", "h_contact", "h_cover_size"}:
            return
        ctk.CTkLabel(parent, text=t(key), text_color=GRAY, wraplength=380,
                     justify="left", anchor="w").grid(
            row=row * 2 + 1, column=0, columnspan=3, sticky="w", padx=(30, 0), pady=(0, 6))

    def check(parent, row, label_key, hint_key, variable):
        ctk.CTkCheckBox(parent, text=t(label_key), variable=variable).grid(
            row=row * 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        hint(parent, row, hint_key)

    def entry(parent, row, label_key, hint_key, variable, width=120, show=None):
        line = ctk.CTkFrame(parent, fg_color="transparent")
        line.grid(row=row * 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ctk.CTkLabel(line, text=t(label_key)).pack(side="left", padx=(0, 10))
        ctk.CTkEntry(line, textvariable=variable, width=width, show=show).pack(side="left")
        hint(parent, row, hint_key)

    def file_cell(parent, row, label_key, variable, filetypes, pady=(4, 0)):
        line = ctk.CTkFrame(parent, fg_color="transparent")
        line.grid(row=row * 2, column=0, columnspan=3, sticky="w", pady=pady)
        ctk.CTkLabel(line, text=t(label_key)).pack(side="left", padx=(0, 10))
        ctk.CTkEntry(line, textvariable=variable, width=190).pack(side="left")

        def choose():
            picked = filedialog.askopenfilename(title=t(label_key), filetypes=filetypes)
            if picked:
                variable.set(os.path.normpath(picked))
        ctk.CTkButton(line, text="...", width=34, command=choose).pack(side="left", padx=(6, 0))

    def file_entry(parent, row, label_key, hint_key, variable, filetypes):
        file_cell(parent, row, label_key, variable, filetypes)
        hint(parent, row, hint_key)

    def build_start(page):
        ctk.CTkLabel(page, text=t("start_title"), font=bold).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(page, text=t("start_rules"), justify="left", anchor="w", wraplength=410).grid(
            row=1, column=0, sticky="w", pady=(4, 12))
        ctk.CTkLabel(page, text=t("start_steps"), font=bold).grid(row=2, column=0, sticky="w")
        for i, key in enumerate(("tags", "online", "covers", "id3v23")):
            ctk.CTkButton(page, text=f"{t('open_step')}  {t('tab_' + key)}", width=220, anchor="w",
                          command=lambda k=key: goto(k)).grid(row=3 + i * 2, column=0, sticky="w", pady=(6, 0))
            ctk.CTkLabel(page, text=t("step_" + key), text_color=GRAY, wraplength=400, justify="left",
                         anchor="w").grid(row=4 + i * 2, column=0, sticky="w", padx=(4, 0))

    def build_tags(page):
        check(page, 1, "o_no_auto", "h_no_auto", tags_flags["no_auto"])
        check(page, 2, "o_no_feat", "h_no_feat", tags_flags["no_feat"])
        check(page, 3, "o_keep_comp", "h_keep_comp", tags_flags["keep_comp"])
        check(page, 4, "o_split_comma", "h_split_comma", tags_flags["split_comma"])
        check(page, 5, "o_move_dupes", "h_move_dupes", tags_flags["move_dupes"])
        check(page, 6, "o_verbose_tags", "h_verbose", tags_flags["verbose"])
        entry(page, 7, "o_ratio", "h_ratio", var["ratio"], width=70)
        file_entry(page, 8, "o_rules", "h_rules", var["rules"], [("JSON", "*.json"), ("*", "*.*")])

    def build_online(page):
        sub = tabview(page)
        sub.pack(fill="both", expand=True)
        a, b, c = (scrolling(sub.add(t(k))) for k in ("sub_what", "sub_match", "sub_more"))
        check(a, 0, "o_metadata", "h_metadata", online_flags["metadata"])
        check(a, 1, "o_covers", "h_covers", online_flags["covers"])
        check(a, 2, "o_lyrics", "h_lyrics", online_flags["lyrics"])
        check(a, 3, "o_lrc", "h_lrc", online_flags["lrc"])
        check(a, 4, "o_overwrite", "h_overwrite", online_flags["overwrite"])

        ctk.CTkLabel(b, text=t("match_label"), font=bold).grid(row=0, column=0, sticky="w", pady=(0, 6))
        labels = {"tags": t("match_tags"), "audio": t("match_audio"), "both": t("match_both")}
        reverse = {v: k for k, v in labels.items()}
        seg = ctk.CTkSegmentedButton(b, values=list(labels.values()),
                                     command=lambda v: var["match"].set(reverse[v]))
        seg.set(labels.get(var["match"].get(), labels["tags"]))
        seg.grid(row=1, column=0, sticky="w", pady=(0, 6))
        entry(b, 2, "o_key", "h_key", var["key"], width=200, show="*")
        file_entry(b, 3, "o_fpcalc", "h_fpcalc", var["fpcalc"], [("fpcalc", "fpcalc*"), ("*", "*.*")])

        entry(c, 0, "o_contact", "h_contact", var["contact"], width=200)
        line = ctk.CTkFrame(c, fg_color="transparent")
        line.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ctk.CTkLabel(line, text=t("o_cover_size")).pack(side="left", padx=(0, 10))
        ctk.CTkOptionMenu(line, values=["250", "500", "1200"], variable=var["cover_size"], width=100).pack(side="left")
        hint(c, 1, "h_cover_size")
        check(c, 2, "o_no_cache", "h_no_cache", online_flags["no_cache"])
        check(c, 3, "o_verbose_online", "h_verbose", online_flags["verbose"])

    def build_covers(page):
        for r, key in enumerate(("fix", "unify", "export", "inspect", "set"), start=1):
            ctk.CTkRadioButton(page, text=t("c_" + key), value=key, variable=var["covers_mode"]).grid(
                row=r * 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
            hint(page, r, f"c_{key}_h")
        file_cell(page, 6, "o_image", var["image"], IMAGE_TYPES, pady=(10, 0))
        rng = ctk.CTkFrame(page, fg_color="transparent")
        rng.grid(row=13, column=0, columnspan=3, sticky="w", pady=(8, 0))
        for i, (key, name) in enumerate((("o_from", "from"), ("o_to", "to"), ("o_disc", "disc"))):
            ctk.CTkLabel(rng, text=t(key)).grid(row=0, column=i * 2, padx=(0, 6))
            ctk.CTkEntry(rng, textvariable=var[name], width=56).grid(row=0, column=i * 2 + 1, padx=(0, 14))

    def build_id3v23(page):
        ctk.CTkLabel(page, text=t("id3v23_nothing"), text_color=GRAY, wraplength=410,
                     justify="left", anchor="w").pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------- result tables ---
    def style_tables():
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2b2b2b", "#dce4ee") if dark else ("#ffffff", "#1a1a1a")
        head_bg = "#3a3a3a" if dark else "#e4e6ea"
        ui["odd"] = "#323232" if dark else "#f4f6fa"
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        for name, height in (("MT.Treeview", px(78)), ("MTR.Treeview", px(28))):
            style.configure(name, background=bg, fieldbackground=bg, foreground=fg, rowheight=height, borderwidth=0,
                            font=("", -px(13)))
            style.configure(name + ".Heading", background=head_bg, foreground=fg, relief="flat",
                            font=("", -px(12), "bold"), padding=(6, 5))
            style.map(name, background=[("selected", "#1f538d")], foreground=[("selected", "white")])
        style.layout("MT.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.layout("MTR.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    def make_tree(parent, columns, style_name, show="headings"):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show=show, style=style_name, selectmode="browse")
        scroll_y = ctk.CTkScrollbar(frame, command=tree.yview)
        scroll_x = ctk.CTkScrollbar(frame, command=tree.xview, orientation="horizontal")
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)
        tree.tag_configure("odd", background=ui["odd"])
        return frame, tree

    def current_bottom():
        names = {v: k for k, v in ui["bottom_names"].items()}
        return names.get(ui["bottom"].get(), "tracks")

    def show_bottom(key):
        state["bottom"] = key
        ui["bottom"].set(ui["bottom_names"][key])

    # results ----------------------------------------------------------------
    def build_results(page):
        style_tables()
        ui["res_holder"] = ctk.CTkFrame(page, fg_color="transparent")
        ui["res_holder"].pack(fill="both", expand=True)

    def card(parent, big, small):
        frame = ctk.CTkFrame(parent, corner_radius=10)
        frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(frame, text=str(big), font=ctk.CTkFont(size=22, weight="bold")).pack(padx=20, pady=(6, 0))
        ctk.CTkLabel(frame, text=small, text_color=GRAY).pack(padx=20, pady=(0, 6))

    def render_results():
        holder = ui["res_holder"]
        for widget in holder.winfo_children():
            widget.destroy()
        res = state["result"]
        if not res:
            ctk.CTkLabel(holder, text=t("res_empty"), text_color=GRAY).pack(pady=40)
            return
        if res.get("note"):
            ctk.CTkLabel(holder, text=t(res["note"]), text_color=GRAY).pack(pady=40)
            return
        applied = res["apply"]
        ctk.CTkLabel(holder, text=t("res_title_applied" if applied else "res_title_preview"), font=bold).pack(
            anchor="w", pady=(0, 4))
        summary = res["summary"]
        if summary["changes"] == 0:
            ctk.CTkLabel(holder, text="\u2713  " + t("res_nothing"), text_color=("#1e7e34", "#5cd679")).pack(
                anchor="w", pady=20)
            return
        cards = ctk.CTkFrame(holder, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 8))
        card(cards, summary["changes"], t("res_changes"))
        card(cards, summary["files"], t("res_files"))
        card(cards, t("res_mode_applied" if applied else "res_mode_preview"), "")
        if summary["kinds"]:
            ctk.CTkLabel(cards, text="   ".join(f"{k}  \u00d7{n}" for k, n in summary["kinds"]), text_color=GRAY,
                         wraplength=520, justify="left").pack(side="left", padx=8)
        header = res["header"]
        _frame, tree = make_tree(holder, header, "MTR.Treeview")
        for name in header:
            label = t("col_" + name)
            tree.heading(name, text=name if label == "col_" + name else label)
            width = px(280 if name == "file" else 170)
            tree.column(name, width=width, minwidth=width, anchor="w", stretch=False)
        for index, row in enumerate(res["rows"]):
            row = list(row) + [""] * (len(header) - len(row))
            row[0] = gui_data.display_name(row[0], res["root"])
            tree.insert("", "end", values=row[:len(header)], tags=("odd",) if index % 2 else ())

    # tracks -----------------------------------------------------------------
    def make_thumb(data):
        if Image is None:
            return None
        image = Image.open(io.BytesIO(data))
        return ImageOps.fit(image.convert("RGB"), (px(68), px(68)))

    def photo_for(track):
        key = track.get("cover_key")
        if not key or track.get("thumb") is None:
            return None
        if key not in state["photos"]:
            state["photos"][key] = ImageTk.PhotoImage(track["thumb"])
        return state["photos"][key]

    def filter_labels():
        return {"": t("tr_f_all"), "cover": t("tr_f_cover"), "lyrics": t("tr_f_lyrics"),
                "albumartist": t("tr_f_albumartist")}

    def build_tracks(page):
        labels = filter_labels()
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 6))
        search = ctk.CTkEntry(bar, width=240, placeholder_text=t("tr_search"))
        if state["search"]:
            search.insert(0, state["search"])
        search.pack(side="left")

        def typed(_event):
            state["search"] = search.get()
            schedule_render()
        search.bind("<KeyRelease>", typed)
        menu = ctk.CTkOptionMenu(bar, values=list(labels.values()), width=190, command=change_filter)
        menu.set(labels[state["filter"]])
        menu.pack(side="left", padx=8)
        ctk.CTkButton(bar, text=t("tr_reload"), width=90, command=lambda: start_scan(force=True)).pack(side="left")
        ui["tr_count"] = ctk.CTkLabel(page, text="", text_color=GRAY, anchor="w", justify="left", wraplength=620)
        ui["tr_count"].pack(fill="x", pady=(0, 4))
        frame, tree = make_tree(page, TRACK_COLUMNS, "MT.Treeview", show=("tree", "headings"))
        ui["tr_tree"] = tree
        tree.heading("#0", text=t("col_cover"))
        tree.column("#0", width=px(96), minwidth=px(96), anchor="center", stretch=False)
        for col in TRACK_COLUMNS:
            tree.heading(col, text=t("col_" + col), command=lambda c=col: sort_by(c))
            tree.column(col, width=px(TRACK_WIDTHS[col]), minwidth=px(TRACK_WIDTHS[col]), anchor="w", stretch=False)

    def change_filter(label):
        state["filter"] = next(k for k, v in filter_labels().items() if v == label)
        render_tracks()

    def schedule_render():
        if ui.get("render_after"):
            root.after_cancel(ui["render_after"])
        ui["render_after"] = root.after(250, render_tracks)

    def sort_by(column):
        current, reverse = state["sort"]
        state["sort"] = (column, not reverse if current == column else False)
        render_tracks()

    def sort_key(column):
        if column == "num":
            return lambda tr: tr["track"]
        if column == "lyrics":
            return lambda tr: bool(tr["lyrics"])
        return lambda tr: str(tr.get(column, "")).lower()

    def track_values(tr):
        dash = "\u2014"
        lyrics = ("\u2713  " + tr["lyrics"].replace("\n", " ")[:28]) if tr["lyrics"] else dash
        return (tr["track"] or "", tr["title"] or Path(tr["path"]).stem, tr["artist"] or dash, tr["album"] or dash,
                tr["albumartist"] or dash, lyrics, tr["format"])

    def insert_track(tree, tr, index):
        photo = photo_for(tr)
        options = {"values": track_values(tr), "tags": ("odd",) if index % 2 else ()}
        if photo is not None:
            options["image"] = photo
            options["text"] = ""
        else:
            options["text"] = "\u2014"
        tree.insert("", "end", **options)

    def update_count():
        try:
            label = ui["tr_count"]
            if not label.winfo_exists():
                return
        except Exception:
            return
        tracks = state["tracks"]
        if state["scan_status"]:
            label.configure(text=t("lib_reading", done=state["scan_status"][0], total=state["scan_status"][1]))
            return
        if not tracks:
            label.configure(text=t("tr_empty") if not state["tracks_folder"] else "")
            return
        summary = gui_data.library_summary(tracks)
        shown = len(gui_data.filter_tracks(tracks, state["search"], state["filter"]))
        label.configure(text=t("lib_summary", shown=shown, tracks=summary["tracks"], no_cover=summary["no_cover"],
                               no_lyrics=summary["no_lyrics"], no_albumartist=summary["no_albumartist"]))

    def render_tracks():
        tree = ui.get("tr_tree")
        try:
            if tree is None or not tree.winfo_exists():
                return
        except Exception:
            return
        state["render_id"] += 1
        rid = state["render_id"]
        tree.delete(*tree.get_children())
        rows = gui_data.filter_tracks(state["tracks"], state["search"], state["filter"])
        column, reverse = state["sort"]
        if column:
            rows = sorted(rows, key=sort_key(column), reverse=reverse)
        update_count()

        def chunk(start_at):
            if rid != state["render_id"] or not tree.winfo_exists():
                return
            for offset, tr in enumerate(rows[start_at:start_at + 100]):
                insert_track(tree, tr, start_at + offset)
            if start_at + 100 < len(rows):
                root.after(5, lambda: chunk(start_at + 100))
        chunk(0)

    def start_scan(force=False):
        folder = var["folder"].get().strip().strip('"')
        if not folder or not Path(folder).is_dir():
            return
        if not force and folder == state["tracks_folder"]:
            return
        state["scan_id"] += 1
        sid = state["scan_id"]
        state["tracks"], state["tracks_folder"], state["scan_status"] = [], folder, (0, 0)
        render_tracks()

        def worker():
            try:
                for done, total, info in gui_data.scan_library(
                        folder, make_thumb=make_thumb, should_stop=lambda: sid != state["scan_id"]):
                    state["scan_q"].put((sid, "track", done, total, info))
            except Exception:
                pass
            state["scan_q"].put((sid, "end", 0, 0, None))
        threading.Thread(target=worker, daemon=True).start()

    def poll_scan():
        tree = ui.get("tr_tree")
        changed = False
        try:
            for _ in range(150):
                sid, kind, done, total, info = state["scan_q"].get_nowait()
                if sid != state["scan_id"]:
                    continue
                if kind == "track":
                    state["tracks"].append(info)
                    state["scan_status"] = (done, total)
                    changed = True
                    if tree is not None and tree.winfo_exists() and gui_data.filter_tracks(
                            [info], state["search"], state["filter"]):
                        insert_track(tree, info, len(tree.get_children()))
                else:
                    state["scan_status"] = None
                    render_tracks()
                    changed = False
                    update_count()
        except queue.Empty:
            pass
        if changed:
            update_count()

    def load_result(run, code):
        if code != 0:
            return
        out_dir = default_out_dir(run["folder"])
        path = gui_data.find_report(out_dir, run["command"], run["apply"], run["since"]) if out_dir.exists() else None
        if path is None:
            state["result"] = {"note": "res_no_table"}
        else:
            header, rows = gui_data.load_report(path)
            state["result"] = {"command": run["command"], "apply": run["apply"], "header": header, "rows": rows,
                               "summary": gui_data.summarize(run["command"], header, rows), "root": run["folder"]}
        render_results()
        show_bottom("results")

    # ------------------------------------------------------------------ actions ---
    def current_key():
        names = {v: k for k, v in ui["tab_names"].items()}
        return names.get(ui["tabs"].get(), "start")

    def goto(key):
        state["tab"] = key
        ui["tabs"].set(ui["tab_names"][key])

    def browse_folder():
        chosen = filedialog.askdirectory(title=t("choose_folder_title"), initialdir=var["folder"].get() or None)
        if chosen:
            var["folder"].set(os.path.normpath(chosen))
            start_scan()

    def change_language(value):
        try:
            state["tab"] = current_key()
        except Exception:
            pass
        state["lang"] = value.lower()
        reopen = state["help"] is not None and state["help"].winfo_exists()
        if reopen:
            state["help"].destroy()
        build()
        if reopen:
            show_help()
        persist()

    def show_help():
        if state["help"] is not None and state["help"].winfo_exists():
            state["help"].lift()
            state["help"].focus()
            return
        win = ctk.CTkToplevel(root)
        state["help"] = win
        win.title(f"musictools - {t('help_title')}")
        win.geometry("820x680")
        win.transient(root)
        set_window_icon(win)          # set right away: a late icon change makes the window flash and close on Windows
        box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(size=13))
        box.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        box.tag_config("h", foreground=ACCENT)
        for line in t("help_text").splitlines():
            heading = line.strip() != "" and line == line.upper() and any(ch.isalpha() for ch in line)
            box.insert("end", line + "\n", "h" if heading else None)
        box.configure(state="disabled")
        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(buttons, text=t("help_readme"), command=lambda: webbrowser.open(README_URL)).pack(side="left")
        ctk.CTkButton(buttons, text=t("help_close"), width=100, command=win.destroy).pack(side="right")
        win.after(120, lambda: (win.winfo_exists() and (win.lift(), win.focus_force())))

    def persist():
        save_config({"folder": var["folder"].get().strip().strip('"'), "rules": var["rules"].get(),
                     "match": var["match"].get(), "key": var["key"].get(), "fpcalc": var["fpcalc"].get(),
                     "contact": var["contact"].get(), "lang": state["lang"]})

    def log_write(text, tag=None):
        log = ui["log"]
        log.configure(state="normal")
        log.insert("end", text, tag)
        log.see("end")
        log.configure(state="disabled")

    def collect(command):
        if command == "tags":
            opts = {k: v.get() for k, v in tags_flags.items()}
            opts.update(ratio=var["ratio"].get(), rules=var["rules"].get().strip())
        elif command == "online":
            opts = {k: v.get() for k, v in online_flags.items()}
            opts.update(match=var["match"].get(), key=var["key"].get().strip(), fpcalc=var["fpcalc"].get().strip(),
                        contact=var["contact"].get().strip(), cover_size=var["cover_size"].get())
        elif command == "covers":
            opts = {"mode": var["covers_mode"].get(), "image": var["image"].get().strip(),
                    "from": var["from"].get(), "to": var["to"].get(), "disc": var["disc"].get()}
        else:
            opts = {}
        return opts

    def set_running(running):
        for b in (ui["preview"], ui["apply"]):
            b.configure(state="disabled" if running else "normal")
        ui["stop"].configure(state="normal" if running else "disabled")
        bar = ui["progress"]
        if running:
            bar.configure(mode="indeterminate")
            bar.start()
        else:
            bar.stop()
            bar.configure(mode="determinate")
            bar.set(0)

    def reader(proc):
        for raw in iter(proc.stdout.readline, b""):
            state["queue"].put(raw.decode("utf-8", "replace"))
        proc.wait()
        state["queue"].put(("done", proc.returncode))

    def poll():
        try:
            while True:
                item = state["queue"].get_nowait()
                if isinstance(item, tuple):
                    state["proc"] = None
                    set_running(False)
                    code = item[1]
                    if code == 0:
                        set_status("st_done")
                    elif state["stopped"]:
                        set_status("st_stopped")
                    else:
                        set_status("st_error", code=code)
                    log_write("\n" + status_var.get() + "\n", "head")
                    run = state["run"]
                    if run and not state["stopped"]:
                        load_result(run, code)
                        if run["apply"] and code == 0:
                            start_scan(force=True)
                    state["stopped"] = False
                else:
                    tag = "head" if item.startswith("===") else (
                        "warn" if any(w in item for w in ("WARNING", "error", "Error", "Traceback")) else None)
                    log_write(item, tag)
        except queue.Empty:
            pass
        poll_scan()
        root.after(100, poll)

    def start(apply):
        command = current_key()
        if command == "start":
            messagebox.showinfo("musictools", t("e_start"))
            return
        folder = var["folder"].get().strip().strip('"')
        try:
            args = build_args(command, folder, apply, collect(command))
        except ArgError as exc:
            messagebox.showwarning("musictools", t(exc.key))
            return
        except ValueError as exc:
            messagebox.showwarning("musictools", str(exc))
            return
        if apply and not messagebox.askyesno(t("dlg_apply_title"), t("dlg_apply_text"), icon="warning"):
            return
        persist()
        ui["log"].configure(state="normal")
        ui["log"].delete("1.0", "end")
        ui["log"].configure(state="disabled")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        try:
            proc = subprocess.Popen(command_for(args), cwd=process_cwd(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            messagebox.showerror("musictools", t("dlg_cannot_start", error=exc))
            return
        state["proc"], state["stopped"] = proc, False
        state["run"] = {"command": command, "apply": apply, "folder": folder, "since": time.time()}
        show_bottom("log")
        set_status("st_apply" if apply else "st_preview")
        set_running(True)
        threading.Thread(target=reader, args=(proc,), daemon=True).start()

    def stop():
        proc = state.get("proc")
        if proc and proc.poll() is None:
            state["stopped"] = True
            proc.terminate()

    def open_reports():
        folder = var["folder"].get().strip().strip('"')
        target = reports_folder(folder) if folder else None
        if target and target.exists():
            open_in_file_manager(target)
        else:
            messagebox.showinfo("musictools", t("dlg_no_reports"))

    def on_close():
        stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    build()
    start_scan()
    poll()
    root.mainloop()


if __name__ == "__main__":
    run_gui()
