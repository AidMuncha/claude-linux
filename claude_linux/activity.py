"""Keeps track of what you are doing on the PC: which window is in front, tab or page title changes, windows opening and closing.
A small KWin script (kwin_activity.js, Plasma 6) calls this app over D-Bus whenever something changes; the last few minutes are kept as
plain text that Jarvis gets with every message. Only window titles are recorded, never contents. Nothing leaves the PC except what Jarvis
is sent along with your messages."""
import os
import threading
import time

from gi.repository import Gio, GLib

NAME = "dev.nein.ClaudeLinux.Jarvis"
PATH = "/jarvis"
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kwin_activity.js")
SCRIPT_NAME = "claude-linux-jarvis-activity"
CURSOR_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kwin_cursor.js")
CURSOR_NAME = "claude-linux-jarvis-cursor"
XML = ('<node><interface name="%s"><method name="Event"><arg type="s" name="kind" direction="in"/><arg type="s" name="id" direction="in"/>'
       '<arg type="s" name="cls" direction="in"/><arg type="s" name="caption" direction="in"/></method></interface></node>' % NAME)


def label(cls, caption):
    app = (cls or "app").split(".")[-1].lower()
    cap = " ".join((caption or "").split())
    return '%s "%s"' % (app, cap[:70]) if cap else app


class Activity:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []                     # (time, text)
        self.open = {}                       # window id -> (class, caption)
        self.active = None
        self.count = 0                       # grows with every event, so others can ask "anything new?"
        self.conn = None
        self.reg = self.own = None
        self.running = False
        self.cursor = None                   # (x, y, time) of the real pointer, from the last one-shot query
        self._cursor_evt = threading.Event()

    # ---------- start / stop (the D-Bus parts run on the GTK main loop) ----------
    def start(self):
        if not self.running:
            self.running = True
            GLib.idle_add(lambda: self._begin() and False)

    def _begin(self):
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            info = Gio.DBusNodeInfo.new_for_xml(XML)
            self.reg = self.conn.register_object(PATH, info.interfaces[0], self._call, None, None)
            self.own = Gio.bus_own_name_on_connection(self.conn, NAME, Gio.BusNameOwnerFlags.NONE, None, None)
            self._kwin("unloadScript", GLib.Variant("(s)", (SCRIPT_NAME,)), lambda *_: self._load())
        except Exception:
            self.running = False

    def _kwin(self, method, params, done, path="/Scripting", iface="org.kde.kwin.Scripting"):
        def finished(conn, res):
            try:
                out = conn.call_finish(res)
            except GLib.Error:
                out = None
            done(out)
        self.conn.call("org.kde.KWin", path, iface, method, params, None, Gio.DBusCallFlags.NONE, 3000, None, finished)

    def _load(self):
        self._run_script(SCRIPT, SCRIPT_NAME, lambda ok: setattr(self, "running", self.running and ok))

    def _run_script(self, path, name, done=None):
        """Loads a KWin script and starts it (on the main loop)."""
        def loaded(out):
            sid = out.unpack()[0] if out else -1
            if sid < 0:
                return done(False) if done else None
            # Plasma 6.7 only runs a loaded script through Scripting.start(); Script.run does nothing there. Older versions: run at /Scripting/Script<id> or /<id>
            def started(r):
                if r is not None:
                    return done(True) if done else None
                self._kwin("run", None, lambda r: (r is None and self._kwin("run", None, lambda *_: None, "/%d" % sid, "org.kde.kwin.Script")) or (done(True) if done else None),
                           "/Scripting/Script%d" % sid, "org.kde.kwin.Script")
            self._kwin("start", None, started)
        self._kwin("loadScript", GLib.Variant("(ss)", (path, name)), loaded)

    def cursor_pos(self, timeout=1.5):
        """Where the real pointer is right now, as global logical pixels, or None. Asks KWin with a one-shot script."""
        if not self.running or not self.conn:
            return None
        self._cursor_evt.clear()
        GLib.idle_add(lambda: self._kwin("unloadScript", GLib.Variant("(s)", (CURSOR_NAME,)), lambda *_: self._run_script(CURSOR_SCRIPT, CURSOR_NAME)) and False)
        if self._cursor_evt.wait(timeout) and self.cursor:
            return self.cursor[0], self.cursor[1]
        return None

    def stop(self):
        if not self.running:
            return
        self.running = False

        def go():
            try:
                if self.conn:
                    self._kwin("unloadScript", GLib.Variant("(s)", (SCRIPT_NAME,)), lambda *_: None)
                    if self.reg:
                        self.conn.unregister_object(self.reg)
                    if self.own:
                        Gio.bus_unown_name(self.own)
            except Exception:
                pass
            self.reg = self.own = None
            return False
        GLib.idle_add(go)
        with self.lock:
            self.events, self.open, self.active = [], {}, None

    # ---------- what KWin tells us ----------
    def _call(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "Event":
            try:
                self._on(*params.unpack())
            except Exception:
                pass
        invocation.return_value(None)

    def _on(self, kind, wid, cls, caption):
        now = time.time()
        if kind == "cursor":
            self.cursor = (float(wid), float(cls), now)
            self._cursor_evt.set()
            return
        with self.lock:
            if kind == "closed":
                gone = self.open.pop(wid, None)
                text = "closed " + label(*(gone or (cls, caption)))
            else:
                self.open[wid] = (cls, caption)
                if kind == "existing":
                    return
                if kind == "active":
                    self.active = wid
                    text = "switched to " + label(cls, caption)
                elif kind == "title":
                    text = "in %s, the title changed to \"%s\" (a new tab or page)" % (label(cls, "").strip(), " ".join(caption.split())[:80])
                else:
                    text = "opened " + label(cls, caption)
            if self.events and self.events[-1][1] == text and now - self.events[-1][0] < 1.0:
                return
            self.events = (self.events + [(now, text)])[-40:]
            self.count += 1

    # ---------- what Jarvis is told ----------
    def summary(self, window=180, limit=8):
        with self.lock:
            if not self.open and not self.events:
                return ""
            now = time.time()
            lines = []
            if self.active in self.open:
                lines.append("In front now: " + label(*self.open[self.active]))
            recent = [(now - t, x) for t, x in self.events if now - t <= window][-limit:]
            if recent:
                lines.append("Recent, oldest first: " + "; ".join("%ds ago %s" % (age, x) for age, x in recent))
            others = [label(*v) for k, v in self.open.items() if k != self.active][:12]
            if others:
                lines.append("Also open: " + ", ".join(others))
            return "\n".join(lines)
