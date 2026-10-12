# SPDX-License-Identifier: GPL-3.0-or-later
"""Graphical window for musictools (tkinter, nothing to install).

The window only builds the same command line you would type and runs it in the background,
showing its output live. Preview is the default; "Apply" asks for confirmation first.
"""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__

CONFIG_PATH = Path.home() / ".musictools_gui.json"
PACKAGE_PARENT = Path(__file__).resolve().parent.parent      # folder that contains 'musictools'
FROZEN = getattr(sys, "frozen", False)                       # True inside the .exe built with PyInstaller


def resource_path(relative):
    """Path of a bundled file (works from the source folder and inside the .exe)."""
    base = Path(getattr(sys, "_MEIPASS", PACKAGE_PARENT))
    return base / relative


def command_for(args):
    """Command line that runs musictools with 'args' in a separate process.
    From source: python -m musictools ...   Inside the .exe: the exe itself with the arguments."""
    if FROZEN:
        return [sys.executable, *args]
    return [sys.executable, "-m", "musictools", *args]


def process_cwd():
    return None if FROZEN else str(PACKAGE_PARENT)


def set_app_id():
    """Windows: give the program its own identity so the taskbar shows our icon, not Python's."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Dig3343.musictools")
        except Exception:
            pass


def set_window_icon(window):
    """Use assets/icon.ico (Windows) or assets/icon.png as the window icon, if present."""
    try:
        if sys.platform.startswith("win"):
            window.iconbitmap(str(resource_path("assets/icon.ico")))
        else:
            import tkinter
            window.iconphoto(True, tkinter.PhotoImage(file=str(resource_path("assets/icon.png"))))
    except Exception:
        pass

COMMAND_INFO = (
    ("tags", "Tags", "Fix artist / album artist / album names, find duplicates."),
    ("online", "Online", "Fill in missing info, covers and lyrics from the internet."),
    ("covers", "Covers", "Find missing or broken covers and copy them from the same album."),
    ("id3v23", "Windows covers", "Make covers show up in Windows Explorer / Media Player (ID3v2.3)."),
)


# ------------------------------------------------------------ command building ---

class ArgError(ValueError):
    """Something is missing or wrong; 'key' identifies the message so the window can translate it."""

    def __init__(self, key, message):
        super().__init__(message)
        self.key = key


def build_args(command, folder, apply, opts):
    """Return the argument list for 'python -m musictools' (pure function, easy to test).
    Raises ValueError with a readable message if something required is missing."""
    if not folder or not Path(folder).exists():
        raise ArgError("e_folder", "Choose your music folder first.")
    args = [command, folder]
    if apply:
        args += ["--apply", "--yes"]

    if command == "tags":
        if opts.get("rules"):
            args += ["--rules", opts["rules"]]
        for key, flag in (("no_auto", "--no-auto"), ("split_comma", "--split-comma"),
                          ("no_feat", "--no-feat-in-title"), ("keep_comp", "--keep-compilation-artists"),
                          ("move_dupes", "--move-dupes"), ("verbose", "--verbose")):
            if opts.get(key):
                args.append(flag)
        ratio = str(opts.get("ratio", "0.6")).replace(",", ".")
        try:
            value = float(ratio)
        except ValueError:
            raise ArgError("e_ratio", "The main artist share must be a number between 0 and 1.")
        if not 0 < value <= 1:
            raise ArgError("e_ratio", "The main artist share must be between 0 and 1.")
        if abs(value - 0.6) > 1e-9:
            args += ["--main-artist-ratio", ratio]

    elif command == "online":
        chosen = [name for name in ("metadata", "covers", "lyrics") if opts.get(name)]
        if not chosen:
            raise ArgError("e_online_none", "Tick at least one of: metadata, covers, lyrics.")
        if len(chosen) < 3:
            args += ["--" + name for name in chosen]
        if opts.get("lrc") and opts.get("lyrics"):
            args.append("--lrc")
        if opts.get("overwrite"):
            args.append("--overwrite")
        match = opts.get("match", "tags")
        args += ["--match", match]
        if match != "tags":
            if not opts.get("key"):
                raise ArgError("e_key", "Audio matching needs your free AcoustID key (see the README).")
            args += ["--acoustid-key", opts["key"]]
            if opts.get("fpcalc"):
                args += ["--fpcalc", opts["fpcalc"]]
        if opts.get("contact"):
            args += ["--contact", opts["contact"]]
        if str(opts.get("cover_size", "500")) != "500":
            args += ["--cover-size", str(opts["cover_size"])]
        if opts.get("no_cache"):
            args.append("--no-cache")
        if opts.get("verbose"):
            args.append("--verbose")

    elif command == "covers":
        mode = opts.get("mode", "fix")
        if mode == "unify":
            args.append("--unify")
        elif mode == "export":
            args.append("--export")
        elif mode == "inspect":
            args.append("--inspect")
        elif mode == "set":
            if not opts.get("image") or not Path(opts["image"]).is_file():
                raise ArgError("e_image", "Choose the image file to use as cover.")
            args += ["--set-cover", opts["image"]]
            for key, flag in (("from", "--from"), ("to", "--to"), ("disc", "--disc")):
                value = str(opts.get(key, "")).strip()
                if value:
                    if not value.isdigit():
                        raise ArgError("e_int", f"'{flag}' must be a whole number.")
                    args += [flag, value]
    return args


def reports_folder(folder):
    return Path(folder) / "_reports"


def open_in_file_manager(path):
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)                                    # noqa: S606 (Windows only)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(data):
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------------- GUI ---

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    config = load_config()
    root = tk.Tk()
    root.title(f"musictools {__version__}")
    root.minsize(860, 680)
    set_window_icon(root)
    try:
        ttk.Style().theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError:
        pass
    mono = ("Consolas", 10) if sys.platform.startswith("win") else ("DejaVu Sans Mono", 9)

    state = {"proc": None, "queue": queue.Queue(), "running": False}
    pad = {"padx": 10, "pady": 4}

    # ---- folder row
    top = ttk.Frame(root)
    top.pack(fill="x", padx=10, pady=(10, 0))
    ttk.Label(top, text="Music folder", font=("", 10, "bold")).grid(row=0, column=0, sticky="w")
    folder_var = tk.StringVar(value=config.get("folder", ""))
    ttk.Entry(top, textvariable=folder_var).grid(row=1, column=0, sticky="ew", pady=4)
    top.columnconfigure(0, weight=1)

    def browse_folder():
        chosen = filedialog.askdirectory(title="Choose your music folder", initialdir=folder_var.get() or None)
        if chosen:
            folder_var.set(os.path.normpath(chosen))

    ttk.Button(top, text="Browse...", command=browse_folder).grid(row=1, column=1, padx=(8, 0))

    # ---- tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill="x", padx=10, pady=10)
    frames = {}
    for command, title, description in COMMAND_INFO:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text=title)
        ttk.Label(frame, text=description, wraplength=780, foreground="#444").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        frames[command] = frame

    def check(frame, text, row, column=0, value=False, span=1):
        var = tk.BooleanVar(value=value)
        ttk.Checkbutton(frame, text=text, variable=var).grid(
            row=row, column=column, columnspan=span, sticky="w", padx=(0, 16), pady=2)
        return var

    def file_row(frame, label, row, var, filetypes):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(frame, textvariable=var, width=46).grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)

        def choose():
            picked = filedialog.askopenfilename(title=label, filetypes=filetypes)
            if picked:
                var.set(os.path.normpath(picked))
        ttk.Button(frame, text="Browse...", command=choose).grid(row=row, column=3, padx=(8, 0))

    # tags
    f = frames["tags"]
    tags_vars = {
        "no_auto": check(f, "No automatic decisions (only my rules)", 1),
        "no_feat": check(f, "Don't move guests into the title", 1, 1),
        "keep_comp": check(f, "Keep each track's artist in compilations", 2),
        "split_comma": check(f, "Treat commas and & as artist separators", 2, 1),
        "move_dupes": check(f, "Move exact duplicates to the _duplicates folder", 3),
        "verbose": check(f, "Show every decision in the log", 3, 1),
    }
    ratio_var = tk.StringVar(value="0.6")
    ttk.Label(f, text="Main artist share (0-1)").grid(row=4, column=0, sticky="w", pady=2)
    ttk.Entry(f, textvariable=ratio_var, width=6).grid(row=4, column=1, sticky="w", pady=2)
    rules_var = tk.StringVar(value=config.get("rules", ""))
    file_row(f, "Rules file (optional)", 5, rules_var, [("JSON", "*.json"), ("All files", "*.*")])

    # online
    f = frames["online"]
    online_vars = {
        "metadata": check(f, "Fill missing info (MusicBrainz)", 1, value=True),
        "covers": check(f, "Download missing covers", 1, 1, value=True),
        "lyrics": check(f, "Lyrics (LRCLIB)", 1, 2, value=True),
        "lrc": check(f, "Also save synced lyrics as .lrc files", 2),
        "overwrite": check(f, "Replace existing values (never the artist)", 2, 1),
        "no_cache": check(f, "Ignore saved answers", 3),
        "verbose": check(f, "Show every decision in the log", 3, 1),
    }
    ttk.Label(f, text="How to recognize tracks").grid(row=4, column=0, sticky="w", pady=(8, 2))
    match_var = tk.StringVar(value=config.get("match", "tags"))
    ttk.Combobox(f, textvariable=match_var, values=("tags", "audio", "both"), state="readonly",
                 width=8).grid(row=4, column=1, sticky="w", pady=(8, 2))
    ttk.Label(f, text="tags = fast, depends on your tags   audio = slow, safest   both = audio then tags",
              foreground="#444").grid(row=4, column=2, columnspan=2, sticky="w", pady=(8, 2))
    key_var = tk.StringVar(value=config.get("key", ""))
    ttk.Label(f, text="AcoustID key (audio/both)").grid(row=5, column=0, sticky="w", pady=2)
    ttk.Entry(f, textvariable=key_var, width=30, show="*").grid(row=5, column=1, columnspan=2, sticky="w", pady=2)
    fpcalc_var = tk.StringVar(value=config.get("fpcalc", ""))
    file_row(f, "fpcalc program (audio/both)", 6, fpcalc_var, [("fpcalc", "fpcalc*"), ("All files", "*.*")])
    contact_var = tk.StringVar(value=config.get("contact", ""))
    ttk.Label(f, text="Your email (optional)").grid(row=7, column=0, sticky="w", pady=2)
    ttk.Entry(f, textvariable=contact_var, width=30).grid(row=7, column=1, columnspan=2, sticky="w", pady=2)
    size_var = tk.StringVar(value="500")
    ttk.Label(f, text="Cover size (px)").grid(row=8, column=0, sticky="w", pady=2)
    ttk.Combobox(f, textvariable=size_var, values=("250", "500", "1200"), state="readonly",
                 width=8).grid(row=8, column=1, sticky="w", pady=2)

    # covers
    f = frames["covers"]
    covers_mode = tk.StringVar(value="fix")
    for row, (value, text) in enumerate((
            ("fix", "Fix missing or broken covers using the rest of the album"),
            ("unify", "Also make different covers equal within each disc"),
            ("export", "Export the different covers to compare them by eye"),
            ("inspect", "Inspect what is inside each file (use on ONE album folder)"),
            ("set", "Put a chosen image on some tracks (use on ONE album folder)")), start=1):
        ttk.Radiobutton(f, text=text, value=value, variable=covers_mode).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=1)
    image_var = tk.StringVar()
    file_row(f, "Image", 6, image_var, [("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*")])
    range_frame = ttk.Frame(f)
    range_frame.grid(row=7, column=0, columnspan=4, sticky="w", pady=2)
    from_var, to_var, disc_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
    for column, (label, var) in enumerate((("from track", from_var), ("to track", to_var), ("disc", disc_var))):
        ttk.Label(range_frame, text=label).grid(row=0, column=column * 2, padx=(0, 4))
        ttk.Entry(range_frame, textvariable=var, width=5).grid(row=0, column=column * 2 + 1, padx=(0, 14))

    # id3v23
    ttk.Label(frames["id3v23"], text="Nothing to set: just choose the folder and run.",
              foreground="#444").grid(row=1, column=0, sticky="w")

    # ---- buttons + status
    bar = ttk.Frame(root)
    bar.pack(fill="x", padx=10)
    preview_btn = ttk.Button(bar, text="Preview (changes nothing)")
    apply_btn = ttk.Button(bar, text="Apply changes")
    stop_btn = ttk.Button(bar, text="Stop", state="disabled")
    reports_btn = ttk.Button(bar, text="Open reports folder")
    for button in (preview_btn, apply_btn, stop_btn):
        button.pack(side="left", padx=(0, 8))
    reports_btn.pack(side="right")
    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.pack(fill="x", padx=10, pady=(8, 0))
    status_var = tk.StringVar(value="Ready. Start with a preview: it never changes your files.")
    ttk.Label(root, textvariable=status_var).pack(fill="x", padx=10, pady=(4, 0), anchor="w")

    # ---- log
    log_frame = ttk.Frame(root)
    log_frame.pack(fill="both", expand=True, padx=10, pady=10)
    log = tk.Text(log_frame, height=14, wrap="word", font=mono, state="disabled",
                  background="#fafafa", relief="solid", borderwidth=1)
    scroll = ttk.Scrollbar(log_frame, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    log.tag_configure("head", font=(mono[0], mono[1], "bold"))
    log.tag_configure("warn", foreground="#b00020")

    def log_write(text, tag=None):
        log.configure(state="normal")
        log.insert("end", text, tag)
        log.see("end")
        log.configure(state="disabled")

    def current_command():
        return COMMAND_INFO[notebook.index(notebook.select())][0]

    def collect(command):
        if command == "tags":
            opts = {k: v.get() for k, v in tags_vars.items()}
            opts.update(ratio=ratio_var.get(), rules=rules_var.get().strip())
        elif command == "online":
            opts = {k: v.get() for k, v in online_vars.items()}
            opts.update(match=match_var.get(), key=key_var.get().strip(), fpcalc=fpcalc_var.get().strip(),
                        contact=contact_var.get().strip(), cover_size=size_var.get())
        elif command == "covers":
            opts = {"mode": covers_mode.get(), "image": image_var.get().strip(),
                    "from": from_var.get(), "to": to_var.get(), "disc": disc_var.get()}
        else:
            opts = {}
        return opts

    def set_running(running):
        state["running"] = running
        for button in (preview_btn, apply_btn):
            button.configure(state="disabled" if running else "normal")
        stop_btn.configure(state="normal" if running else "disabled")
        if running:
            progress.start(12)
        else:
            progress.stop()

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
                    set_running(False)
                    code = item[1]
                    status_var.set("Finished." if code == 0 else
                                   ("Stopped." if state.get("stopped") else f"Finished with an error (code {code})."))
                    log_write("\n" + status_var.get() + "\n", "head")
                    state["stopped"] = False
                else:
                    tag = "head" if item.startswith("===") else (
                        "warn" if any(w in item for w in ("WARNING", "error", "Error", "Traceback")) else None)
                    log_write(item, tag)
        except queue.Empty:
            pass
        root.after(100, poll)

    def start(apply):
        command = current_command()
        folder = folder_var.get().strip().strip('"')
        try:
            args = build_args(command, folder, apply, collect(command))
        except ValueError as exc:
            messagebox.showwarning("musictools", str(exc))
            return
        if apply and not messagebox.askyesno(
                "Apply changes", "This will change your files.\n\nDid you back up your music?\n\nContinue?",
                icon="warning"):
            return
        save_config({"folder": folder, "rules": rules_var.get(), "match": match_var.get(),
                     "key": key_var.get(), "fpcalc": fpcalc_var.get(), "contact": contact_var.get()})
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.configure(state="disabled")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(command_for(args), cwd=process_cwd(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                    creationflags=flags)
        except OSError as exc:
            messagebox.showerror("musictools", f"Could not start: {exc}")
            return
        state["proc"], state["stopped"] = proc, False
        status_var.set(("Applying changes..." if apply else "Preview running...") + " (this can take a while)")
        set_running(True)
        threading.Thread(target=reader, args=(proc,), daemon=True).start()

    def stop():
        proc = state.get("proc")
        if proc and proc.poll() is None:
            state["stopped"] = True
            proc.terminate()

    def open_reports():
        folder = folder_var.get().strip().strip('"')
        target = reports_folder(folder) if folder else None
        if target and target.exists():
            open_in_file_manager(target)
        else:
            messagebox.showinfo("musictools", "No reports yet: run a preview first.")

    preview_btn.configure(command=lambda: start(False))
    apply_btn.configure(command=lambda: start(True))
    stop_btn.configure(command=stop)
    reports_btn.configure(command=open_reports)

    def on_close():
        stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    log_write("Choose your music folder, pick a tab and press Preview.\n"
              "Nothing is changed until you press Apply (and confirm).\n")
    poll()
    root.mainloop()
    return root


if __name__ == "__main__":
    run_gui()
