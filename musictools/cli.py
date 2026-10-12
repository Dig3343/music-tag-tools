"""Command line interface: musictools tags | online | covers | id3v23 (or no arguments for a menu)."""

import argparse
import os
import sys
from pathlib import Path

from . import __version__, covers, id3v23, online, tags
from .common import REPORTS_DIRNAME, default_out_dir

# (name, module, one-line description)  -- in the suggested order of use
COMMANDS = (
    ("tags", tags, "Fix artist / album artist / album names, find duplicates"),
    ("online", online, "Fill in missing info, covers and lyrics from the internet"),
    ("covers", covers, "Find missing or broken covers and copy them from the same album"),
    ("id3v23", id3v23, "Make covers show up in Windows Explorer / Media Player"),
)
NAMES = [name for name, _m, _d in COMMANDS]


def welcome(prog="python main.py"):
    lines = [f"musictools {__version__} - tidy up your mp3/flac library", "",
             "Commands (each one only PREVIEWS until you add --apply):"]
    lines += [f"  {name:<8}{text}" for name, _m, text in COMMANDS]
    lines += ["",
              "Suggested order: " + " -> ".join(NAMES),
              "",
              "Examples:",
              f'  {prog} tags "D:/Music"            preview, changes nothing',
              f'  {prog} tags "D:/Music" --apply    really changes the files',
              f"  {prog} tags --help                all options of a command",
              "",
              "",
              "Back up your music before using --apply."]
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="musictools", description=welcome(), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, module, text in COMMANDS:
        sp = sub.add_parser(name, help=text, description=text + ". It only previews until you add --apply.")
        module.add_arguments(sp)
        sp.set_defaults(func=module.run, command_text=text)
    return parser


# ------------------------------------------------------------------ interactive ---

def ask(question, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip().strip('"').strip("'")
    return answer or default


def wizard():
    """Tiny menu for people who just double-click or run the program with no arguments."""
    print()
    for number, (name, _m, text) in enumerate(COMMANDS, 1):
        print(f"  {number}) {name:<8}{text}")
    print("  q) quit\n")
    while True:
        choice = ask("What do you want to do? (number or name)").lower()
        if choice in ("q", "quit", "exit"):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(COMMANDS):
            command = NAMES[int(choice) - 1]
            break
        if choice in NAMES:
            command = choice
            break
        print("Please type one of the numbers above.")

    while True:
        folder = ask("Music folder (paste or drag the path here)")
        if folder and Path(folder).exists():
            break
        print("That folder wasn't found, try again.")

    argv = [command, folder]
    if command == "online":
        print("\nHow should tracks be identified?")
        print("  1) tags   - fast, but wrong tags can give wrong results")
        print("  2) audio  - audio fingerprint: slow, safest (needs fpcalc + AcoustID key)")
        print("  3) both   - fingerprint first, tags as fallback")
        mode = {"1": "tags", "2": "audio", "3": "both"}.get(ask("Choice", "1"), "tags")
        argv += ["--match", mode]
        if mode != "tags" and not os.environ.get("ACOUSTID_API_KEY"):
            argv += ["--acoustid-key", ask("Your AcoustID key")]
        contact = ask("Your email (optional, MusicBrainz likes to know who is asking)")
        if contact:
            argv += ["--contact", contact]
    preview = ask("Preview only, without changing anything? (y/n)", "y").lower().startswith("y")
    if not preview:
        argv.append("--apply")
    return argv


# ------------------------------------------------------------------------ main ---

def main(argv=None):
    parser = build_parser()
    for stream in (sys.stdout, sys.stderr):      # avoid crashes on non-UTF-8 Windows consoles
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    interactive = False
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print(welcome())
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return 0
        argv = wizard()
        if argv is None:
            return 0
        interactive = True

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        print(welcome())
        return 0
    if hasattr(args, "out_dir") and args.out_dir is None:
        args.out_dir = str(default_out_dir(args.folder))

    print()
    print(f"=== {args.command}: {args.command_text} ===")
    if args.apply:
        print("MODE: APPLY - your files WILL be changed")
        if not args.yes and sys.stdin.isatty():
            if input("Did you back up your music? Type YES to continue: ").strip() != "YES":
                print("Cancelled, nothing was changed.")
                return 1
    else:
        print("MODE: PREVIEW - your files will not be changed")
    if args.command == "online":
        print("This command uses the internet; it can take a while.")
    print()

    code = 0
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        code = 130
    else:
        print()
        reports = Path(args.out_dir)
        if reports.exists():
            print(f"Reports (open the .csv files with Excel): {reports}")
        if args.apply:
            position = NAMES.index(args.command)
            if position + 1 < len(NAMES):
                print(f"Done. Next in the suggested order: {NAMES[position + 1]}")
    if interactive:
        input("\nPress Enter to close...")
    return code
