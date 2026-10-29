"""The GTK window: a WebKit view that hosts ui/index.html and bridges messages to Core."""
import json
import os
import sys
import threading

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402

from . import kde  # noqa: E402
from .core import Core  # noqa: E402
from .paths import APP_ID, EXPORT_DIR, HERE, HOME  # noqa: E402
from .pdf import print_pdf  # noqa: E402
from .portal import GlobalShortcut, Launcher  # noqa: E402
from .tray import Tray  # noqa: E402

sys.path.insert(0, HERE)
import build  # noqa: E402  (rebuilds ui/index.html when the css/js sources changed)

ICON_DIR = os.path.join(HOME, ".local/share/icons")


def rgba(hexcolor, alpha=1.0):
    c = Gdk.RGBA()
    if not (isinstance(hexcolor, str) and c.parse(hexcolor)):
        c.parse("#262624")
    c.alpha = alpha
    return c


def css_color(hexcolor, alpha=1.0):
    c = rgba(hexcolor, alpha)
    return "rgba(%d,%d,%d,%.3f)" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255), alpha)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.core = self.win = self.web = self.tray = self.hotkey = self.launcher = None
        self.add_main_option("new", ord("n"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Start a new session", None)
        self._want_new = self._held = False
        self._kde_last = self._kde_timer = None
        self._chrome_css = Gtk.CssProvider()

    # ---------- command line: `--new` opens a fresh session in the running instance ----------
    def do_handle_local_options(self, options):
        if options.contains("new"):
            try:
                self.register(None)
            except GLib.Error:
                return -1
            if self.get_is_remote():
                self.activate_action("new-session", None)
                return 0
            self._want_new = True
        return -1

    def do_startup(self):
        Gtk.Application.do_startup(self)
        for name, fn in (("present", self.show_window), ("new-session", self.new_session), ("quit", lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, f=fn: f())
            self.add_action(act)

    def do_activate(self):
        if self.core:
            self.show_window()
            return
        build.ensure()
        display = Gdk.Display.get_default()
        Gtk.IconTheme.get_for_display(display).add_search_path(ICON_DIR)
        Gtk.StyleContext.add_provider_for_display(display, self._chrome_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = win = Gtk.ApplicationWindow(application=self, title="Claude Linux")
        self.bar = Gtk.HeaderBar()
        self.bar.set_decoration_layout(kde.window_buttons())
        self.heading = Gtk.Label(label="Claude Linux", ellipsize=3, css_classes=["title"])
        self.bar.set_title_widget(self.heading)
        win.set_titlebar(self.bar)
        win.connect("close-request", self.on_close)
        win.set_default_size(int(os.environ.get("CL_W", "1240")), int(os.environ.get("CL_H", "820")))
        ucm = WebKit.UserContentManager()
        ucm.register_script_message_handler("bridge", None)
        ucm.connect("script-message-received::bridge", self.on_msg)
        self.web = WebKit.WebView(user_content_manager=ucm)
        ws = self.web.get_settings()
        ws.set_enable_developer_extras(True)
        ws.set_enable_smooth_scrolling(True)
        self._q, self._lock, self._sched = [], threading.Lock(), False
        self.web.set_background_color(Gdk.RGBA(0.15, 0.15, 0.14, 1))
        self.core = Core(self.js, self)
        self.apply_chrome({"bg": "#262624", "side": "#1f1e1d", "fg": "#faf9f5", "line": "#34332f"})
        self.web.load_uri("file://" + os.path.join(HERE, "ui", "index.html"))
        win.set_child(self.web)
        Gtk.Window.set_default_icon_name("dev.nein.ClaudeLinux")
        win.present()
        self.apply_settings(self.core.settings)
        if os.environ.get("CL_SNAP"):
            GLib.timeout_add_seconds(int(os.environ.get("CL_WAIT", "4")), self.snap)

    # ---------- window ----------
    def show_window(self):
        if self.win:
            self.win.set_visible(True)
            self.win.present()

    def toggle_window(self):
        if self.win.is_visible() and self.win.is_active():
            self.win.set_visible(False)
        else:
            self.show_window()

    def new_session(self):
        self.show_window()
        self.js("newsession", {})

    def on_close(self, _win):
        if self.core and self.core.settings.get("closeToTray") and self.tray and self.tray.registered:
            self.win.set_visible(False)
            if not self._held:
                self.hold()
                self._held = True
            return True
        return False

    def apply_chrome(self, c):
        """Makes the title bar, window and web view match the page's colors; glass makes them see-through."""
        glass = bool(c.get("glass"))
        a = max(0.3, min(1.0, float(c.get("opacity", 0.85)))) if glass else 1.0
        bg, side, fg, line = c.get("bg"), c.get("side"), c.get("fg"), c.get("line") or c.get("side")
        self._chrome_css.load_from_string(f"""
            window.background {{ background-color: {css_color(bg, a) if glass else css_color(bg)}; color: {css_color(fg)}; }}
            headerbar {{ background: {css_color(side, a)}; color: {css_color(fg)}; box-shadow: none;
                         border-bottom: 1px solid {css_color(line, a)}; min-height: 38px; }}
            headerbar label.title {{ color: {css_color(fg)}; font-weight: 600; font-size: 13px; }}
            headerbar button {{ color: {css_color(fg)}; background: transparent; box-shadow: none; border: none; }}
            headerbar button:hover {{ background: {css_color(fg, 0.12)}; }}
            headerbar button:active {{ background: {css_color(fg, 0.2)}; }}
        """)
        self.web.set_background_color(Gdk.RGBA(0, 0, 0, 0) if glass else rgba(bg))

    # ---------- settings that need the desktop ----------
    def apply_settings(self, s):
        want_tray = bool(s.get("tray", True))
        if want_tray and not self.tray:
            self.tray = Tray(APP_ID, "Claude Linux", "dev.nein.ClaudeLinux", ICON_DIR, self.show_window, self.new_session, self.quit)
        elif not want_tray and self.tray:
            self.tray.close()
            self.tray = None
            if self._held:
                self.release()
                self._held = False
        if s.get("hotkey") and not self.hotkey:
            self.hotkey = GlobalShortcut("toggle-window", "Show or hide Claude Linux", "CTRL+ALT+C", self.toggle_window,
                                         lambda ok, msg: self.js("hotkey", {"ok": ok, "msg": msg}))
            self.hotkey.start()
        elif not s.get("hotkey") and self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        if not s.get("taskbar", True) and self.launcher:
            self.launcher.update(0, None, False)

    # ---------- KDE colors, pushed to the page whenever Plasma changes them ----------
    def push_kde(self, force=False):
        data = {"scheme": kde.scheme(), "buttons": kde.window_buttons()}
        if force or data != self._kde_last:
            self._kde_last = data
            self.js("kde", data)

    def watch_kde(self):
        def changed(*_):
            if self._kde_timer:
                GLib.source_remove(self._kde_timer)

            def go():
                self._kde_timer = None
                self.push_kde()
                return False
            self._kde_timer = GLib.timeout_add(400, go)
        try:
            self._kde_mon = Gio.File.new_for_path(kde.KDEGLOBALS).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._kde_mon.connect("changed", changed)
        except GLib.Error:
            pass

    # ---------- messages from the page ----------
    def on_msg(self, _ucm, value):
        m = json.loads(value.to_json(0))
        kind = m.get("type")
        if kind == "jserr":
            print("JS ERROR:", m.get("text"), file=sys.stderr, flush=True)
            return
        fn = getattr(self, "ui_" + str(kind), None)
        if fn:
            fn(m)
            if kind != "ready":
                return
        self.core.handle(m)

    def ui_ready(self, _m):
        script = os.environ.get("CL_TEST_JS")        # tests: run a script inside the page shortly after startup
        if script:
            GLib.timeout_add(int(os.environ.get("CL_TEST_JS_DELAY", "1500")),
                             lambda: self.web.evaluate_javascript(script, -1, None, None, None, None, None) and False)
        self.push_kde(force=True)
        if not hasattr(self, "_kde_mon"):
            self.watch_kde()
        if self._want_new:
            self._want_new = False
            GLib.timeout_add(500, lambda: self.js("newsession", {}) or False)

    def ui_chrome(self, m):
        self.apply_chrome(m)

    def ui_title(self, m):
        title = (m.get("text") or "").strip()
        self.heading.set_label(title or "Claude Linux")
        self.win.set_title((title + " - " if title else "") + "Claude Linux")

    def ui_status(self, m):
        busy, waiting = int(m.get("busy") or 0), int(m.get("waiting") or 0)
        if self.core.settings.get("taskbar", True):
            if not self.launcher:
                self.launcher = Launcher(APP_ID)
            self.launcher.update(busy, m.get("progress"), waiting > 0)
        if self.tray:
            tip = "Waiting for you" if waiting else (f"{busy} running" if busy else "Claude Linux")
            self.tray.set_attention(waiting > 0, tip)

    def ui_log(self, m):
        """Lets tests (and curious people) read state out of the page: LOG lines go to stderr."""
        print("LOG:", m.get("text"), file=sys.stderr, flush=True)

    def ui_close(self, _m):
        self.win.close()          # goes to the tray instead when "Close to the tray" is on

    def ui_appstate(self, _m):
        self.js("appstate", {"visible": self.win.is_visible(), "fullscreen": self.win.is_fullscreen(),
                             "tray": bool(self.tray and self.tray.registered), "hotkey": bool(self.hotkey)})

    def ui_fullscreen(self, _m):
        if self.win.is_fullscreen():
            self.win.unfullscreen()
        else:
            self.win.fullscreen()

    def ui_hotkey_configure(self, _m):
        if self.hotkey:
            self.hotkey.configure()

    def ui_pdf(self, m):
        path = Core.unique_path(EXPORT_DIR, Core.safe_name(m.get("name", "")), ".pdf")

        def done(ok, msg):
            self.js("pdf_done", {"ok": ok, "text": ("Exported to " + msg) if ok else ("PDF failed: " + msg)})
        print_pdf(self.web, path, done)

    def ui_pickimage(self, _m):
        dlg = Gtk.FileDialog(title="Choose a background image")
        flt = Gtk.FileFilter()
        flt.set_name("Images")
        flt.add_mime_type("image/*")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def done(d, res):
            try:
                self.js("bgimage", {"path": d.open_finish(res).get_path()})
            except GLib.Error:
                pass
        dlg.open(self.win, None, done)

    def ui_pickjson(self, _m):
        dlg = Gtk.FileDialog(title="Import a theme")
        flt = Gtk.FileFilter()
        flt.set_name("Theme files (JSON)")
        flt.add_suffix("json")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(flt)
        dlg.set_filters(store)

        def done(d, res):
            try:
                path = d.open_finish(res).get_path()
                with open(path, encoding="utf-8") as f:
                    text = f.read(200000)
                self.js("themefile", {"text": text})
            except (GLib.Error, OSError, UnicodeDecodeError) as e:
                self.js("toast", {"text": "Could not read that file: %s" % e, "err": True})
        dlg.open(self.win, None, done)

    # ---------- test hook: save a PNG of the page ----------
    def snap(self):
        js = os.environ.get("CL_EVAL")
        if js and not getattr(self, "_evald", False):
            self._evald = True
            self.web.evaluate_javascript(js, -1, None, None, None, None, None)
            GLib.timeout_add_seconds(int(os.environ.get("CL_WAIT2", "6")), self.snap)
            return False

        def done(web, res):
            tex = web.get_snapshot_finish(res)
            tex.save_to_png(os.environ["CL_SNAP"])
            self.quit()
        self.web.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE, None, done)
        return False

    def notify(self, title, body, nid):
        def go():
            w = self.get_active_window()
            if w and w.is_active():
                return False
            n = Gio.Notification.new(title)
            n.set_body(body)
            n.set_default_action("app.present")
            self.send_notification(nid, n)
            return False
        GLib.idle_add(go)

    def js(self, name, payload):
        """Queue a message for the page; everything queued within ~16ms goes over as one call."""
        with self._lock:
            q = self._q
            if q and name == "event" and q[-1][0] == "event":
                a, b = q[-1][1], payload
                ea, eb = a["ev"].get("event") or {}, b["ev"].get("event") or {}
                da, db = ea.get("delta") or {}, eb.get("delta") or {}
                if (a["chat"] == b["chat"] and a["ev"].get("type") == b["ev"].get("type") == "stream_event"
                        and da.get("type") == db.get("type") == "text_delta" and ea.get("index") == eb.get("index")
                        and not a["ev"].get("parent_tool_use_id") and not b["ev"].get("parent_tool_use_id")):
                    da["text"] += db["text"]
                    return
            q.append([name, payload])
            if self._sched:
                return
            self._sched = True
        GLib.idle_add(lambda: GLib.timeout_add(16, self.flush) and False)

    def flush(self):
        with self._lock:
            items, self._q, self._sched = self._q, [], False
        if items:
            self.web.evaluate_javascript(f"window.fromPyBatch({json.dumps(items)})", -1, None, None, None, None, None)
        return False

    def pickdir(self, start=""):
        dlg = Gtk.FileDialog(title="Choose working folder")
        if os.path.isdir(start):
            dlg.set_initial_folder(Gio.File.new_for_path(start))

        def done(d, res):
            try:
                self.js("cwd", {"path": d.select_folder_finish(res).get_path()})
            except GLib.Error:
                pass
        dlg.select_folder(self.win, None, done)
        return False

    def restart(self):
        """Starts a fresh copy a moment from now (after this one has released its single-instance name), then quits."""
        import shlex
        import subprocess
        wrapper = os.path.expanduser("~/.local/bin/claude-linux")
        target = os.environ.get("CL_UPDATE_TARGET") or HERE
        cmd = os.environ.get("CL_RESTART_CMD") or ("exec " + shlex.quote(wrapper) if os.path.exists(wrapper)
                                                  else "cd %s && exec %s app.py" % (shlex.quote(target), shlex.quote(sys.executable)))
        subprocess.Popen(["/bin/sh", "-c", "sleep 1.5; " + cmd], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.quit()

    def do_shutdown(self):
        if self.hotkey:
            self.hotkey.stop()
        if self.tray:
            self.tray.close()
        if self.core:
            self.core.kill_all()
            self.core.dirty.update(self.core.chats)
            self.core.flush_chats()
        Gtk.Application.do_shutdown(self)


def main():
    sys.exit(App().run(sys.argv))
