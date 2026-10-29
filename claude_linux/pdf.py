"""Prints the current page to a PDF file without showing any dialog."""
from gi.repository import GLib

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gtk, WebKit  # noqa: E402

_running = set()  # keeps the print operation alive until it finishes


def print_pdf(web, path, on_done):
    """on_done(ok: bool, message: str) is called once, on the main loop."""
    ps = Gtk.PrintSettings.new()
    ps.set_printer("Print to File")
    ps.set(Gtk.PRINT_SETTINGS_OUTPUT_URI, GLib.filename_to_uri(path, None))
    ps.set(Gtk.PRINT_SETTINGS_OUTPUT_FILE_FORMAT, "pdf")
    setup = Gtk.PageSetup.new()
    setup.set_paper_size(Gtk.PaperSize.new(Gtk.PAPER_NAME_A4))
    for side in ("top", "bottom", "left", "right"):
        getattr(setup, "set_%s_margin" % side)(16, Gtk.Unit.MM)
    op = WebKit.PrintOperation.new(web)
    op.set_print_settings(ps)
    op.set_page_setup(setup)
    _running.add(op)

    def finish(ok, msg):
        _running.discard(op)
        on_done(ok, msg)
    op.connect("finished", lambda _op: finish(True, path))
    op.connect("failed", lambda _op, err: finish(False, err.message))
    op.print_()
