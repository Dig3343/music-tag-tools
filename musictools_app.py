# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point for the frozen GUI program on Windows, Linux, and macOS.

Double-click: opens the window. With arguments (used by the window itself, or from a terminal):
runs the command line version.
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "gui":
        from musictools.cli import main
        sys.exit(main())
    try:
        from musictools.gui_ctk import run_gui
    except ImportError:
        from musictools.gui import run_gui
    run_gui()
