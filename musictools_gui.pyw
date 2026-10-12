# SPDX-License-Identifier: GPL-3.0-or-later
"""Double-click this file (Windows) to open the musictools window without a console."""
try:
    from musictools.gui_ctk import run_gui      # modern look (pip install customtkinter)
except ImportError:
    from musictools.gui import run_gui          # plain tkinter

run_gui()
