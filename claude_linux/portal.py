"""Desktop integration over D-Bus: a global shortcut (xdg-desktop-portal GlobalShortcuts) and taskbar badge/progress."""
import os

from gi.repository import Gio, GLib

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"


class GlobalShortcut:
    """Registers one system-wide shortcut. KDE shows it under System Settings > Shortcuts, where the user can rebind it."""

    def __init__(self, shortcut_id, description, preferred, on_activated, on_result=None):
        self.id, self.description, self.preferred = shortcut_id, description, preferred
        self.on_activated, self.on_result = on_activated, on_result or (lambda ok, msg: None)
        self.session = None
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._sender = self.conn.get_unique_name()[1:].replace(".", "_")
        self._n = 0
        self._subs = []

    def _token(self):
        self._n += 1
        return "claudelinux%d_%d" % (os.getpid(), self._n)

    def _request(self, method, build_params, done):
        """Calls a portal method that answers through a Request object's Response signal."""
        token = self._token()
        path = "%s/request/%s/%s" % (PORTAL_PATH, self._sender, token)

        def on_response(_c, _s, _p, _i, _n, params):
            code, results = params.unpack()
            self.conn.signal_unsubscribe(sub)
            done(code, results)
        sub = self.conn.signal_subscribe(PORTAL, "org.freedesktop.portal.Request", "Response", path, None,
                                         Gio.DBusSignalFlags.NONE, on_response)

        def called(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                self.conn.signal_unsubscribe(sub)
                self.on_result(False, e.message)
        self.conn.call(PORTAL, PORTAL_PATH, "org.freedesktop.portal.GlobalShortcuts", method, build_params(token),
                       None, Gio.DBusCallFlags.NONE, 5000, None, called)

    def start(self):
        v = GLib.Variant

        def create(token):
            return v("(a{sv})", ({"handle_token": v("s", token), "session_handle_token": v("s", self._token())},))

        def created(code, results):
            if code != 0 or "session_handle" not in results:
                return self.on_result(False, "The desktop declined to create a shortcut session")
            self.session = results["session_handle"]
            self._subs.append(self.conn.signal_subscribe(
                PORTAL, "org.freedesktop.portal.GlobalShortcuts", "Activated", PORTAL_PATH, None, Gio.DBusSignalFlags.NONE,
                lambda *a: a[5].unpack()[1] == self.id and self.on_activated()))
            self._request("BindShortcuts", bind, bound)

        def bind(token):
            return v("(oa(sa{sv})sa{sv})", (self.session, [(self.id, {"description": v("s", self.description),
                                                                      "preferred_trigger": v("s", self.preferred)})],
                                            "", {"handle_token": v("s", token)}))

        def bound(code, results):
            if code != 0 and not self._retried:
                self._retried = True  # the very first bind after login is sometimes refused; it works a moment later
                return GLib.timeout_add(1200, lambda: self._request("BindShortcuts", bind, bound) and False)
            keys = [s[1].get("trigger_description", "") for s in results.get("shortcuts", [])]
            self.on_result(code == 0, "" if code != 0 else (keys[0] if keys else ""))
        self._retried = False
        self._request("CreateSession", create, created)

    def configure(self):
        """Opens the desktop's own dialog for choosing the key."""
        if self.session:
            self.conn.call(PORTAL, PORTAL_PATH, "org.freedesktop.portal.GlobalShortcuts", "ConfigureShortcuts",
                           GLib.Variant("(osa{sv})", (self.session, "", {})), None, Gio.DBusCallFlags.NONE, 3000, None, None)

    def stop(self):
        for s in self._subs:
            self.conn.signal_unsubscribe(s)
        self._subs = []
        if self.session:
            self.conn.call(PORTAL, self.session, "org.freedesktop.portal.Session", "Close", None, None,
                           Gio.DBusCallFlags.NONE, 1000, None, None)
            self.session = None


class Launcher:
    """Taskbar badge, urgency and progress through the com.canonical.Unity.LauncherEntry signal that Plasma's task manager shows."""

    def __init__(self, desktop_id):
        self.uri = "application://%s.desktop" % desktop_id
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.last = None

    def update(self, count=0, progress=None, urgent=False):
        state = (count, None if progress is None else round(progress, 3), urgent)
        if state == self.last:
            return
        self.last = state
        v = GLib.Variant
        props = {"count": v("x", count), "count-visible": v("b", count > 0), "urgent": v("b", urgent),
                 "progress": v("d", progress or 0.0), "progress-visible": v("b", progress is not None)}
        self.conn.emit_signal(None, "/com/canonical/unity/launcherentry/1", "com.canonical.Unity.LauncherEntry", "Update",
                              v("(sa{sv})", (self.uri, props)))
