"""The mouse, moved the way a hand moves it: a curved path, a smooth start and stop, a little overshoot on long trips, a hint of tremor.

Positions are exact because they go through the desktop's RemoteDesktop portal (the same mechanism remote-desktop tools use): the first
time, KDE asks once which screen Jarvis may control, and remembers. Without the portal, `ydotool` is used instead (its absolute moves are
only as exact as your pointer-acceleration setting allows). Coordinates everywhere are global logical screen pixels."""
import math
import os
import random
import shutil
import subprocess
import threading
import time

from gi.repository import Gio, GLib

from .paths import DATA

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
RD = "org.freedesktop.portal.RemoteDesktop"
CAST = "org.freedesktop.portal.ScreenCast"
TOKEN_FILE = os.path.join(DATA, "jarvis", "remote.token")
BTN = {"left": 272, "right": 273, "middle": 274}
HZ = 100.0


def min_jerk(t):
    """0 to 1 with a gentle start and stop: the speed profile of a reaching hand."""
    return t * t * t * (10 - 15 * t + 6 * t * t)


def human_path(p0, p1, rng=random):
    """A list of (time offset, x, y) from p0 to p1, ending exactly on p1."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1:
        return [(0.0, x1, y1)]
    nx, ny = -dy / dist, dx / dist                              # sideways, for the arc
    over = dist > 260 and rng.random() < 0.55                   # long trips often overshoot a little and settle back
    tx, ty = (x1 + dx / dist * rng.uniform(4, 10), y1 + dy / dist * rng.uniform(4, 10)) if over else (x1, y1)
    bend = dist * rng.uniform(0.04, 0.11) * rng.choice((-1, 1))
    c1 = (x0 + (tx - x0) * 0.30 + nx * bend, y0 + (ty - y0) * 0.30 + ny * bend)
    c2 = (x0 + (tx - x0) * 0.72 + nx * bend * rng.uniform(0.2, 0.9), y0 + (ty - y0) * 0.72 + ny * bend * rng.uniform(0.2, 0.9))
    total = min(0.9, 0.16 + 0.09 * math.log2(1 + dist / 60.0)) * rng.uniform(0.92, 1.12)
    steps = max(6, int(total * HZ))
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        s = min_jerk(t)
        u = 1 - s
        x = u ** 3 * x0 + 3 * u * u * s * c1[0] + 3 * u * s * s * c2[0] + s ** 3 * tx
        y = u ** 3 * y0 + 3 * u * u * s * c1[1] + 3 * u * s * s * c2[1] + s ** 3 * ty
        tremor = 0.7 * (1 - t) * math.sin(i * 1.7)
        pts.append((t * total, x + nx * tremor, y + ny * tremor))
    if over:                                                    # the small correction back onto the target
        settle = rng.uniform(0.08, 0.16)
        n = max(3, int(settle * HZ))
        for i in range(1, n + 1):
            s = min_jerk(i / n)
            pts.append((total + settle * i / n, tx + (x1 - tx) * s, ty + (y1 - ty) * s))
    else:
        pts[-1] = (pts[-1][0], x1, y1)
    return pts


class Pointer:
    def __init__(self, cursor_pos):
        self.cursor_pos = cursor_pos             # () -> (x, y) of the real pointer, or None
        self.lock = threading.Lock()
        self.conn = None
        self.session = None
        self.node = None
        self.origin = (0, 0)
        self.size = (1920, 1080)
        self.pos = None                          # where we last put it
        self.pos_t = 0.0
        self._n = 0
        self._sender = ""
        self._ready = threading.Event()
        self._error = ""
        self.backend = None                      # "portal" or "ydotool"

    # ---------- permission (asks once, through the portal) ----------
    def ensure(self, timeout=150):
        with self.lock:
            if self.backend:
                return
            self._ready.clear()
            self._error = ""
            GLib.idle_add(lambda: self._begin() and False)
            self._ready.wait(timeout)
            if self.backend:
                return
            if self._error and not shutil.which("ydotool"):
                raise RuntimeError(self._error)
            if not shutil.which("ydotool"):
                raise RuntimeError("Mouse control was not allowed, and ydotool is not installed")
            self.backend = "ydotool"

    def _tok(self):
        self._n += 1
        return "jarvisptr%d_%d" % (os.getpid(), self._n)

    def _request(self, iface, method, build, handler):
        token = self._tok()
        path = "%s/request/%s/%s" % (PORTAL_PATH, self._sender, token)

        def on_response(_c, _s, _p, _i, _n, params):
            code, results = params.unpack()
            self.conn.signal_unsubscribe(sub)
            handler(code, results)
        sub = self.conn.signal_subscribe(PORTAL, "org.freedesktop.portal.Request", "Response", path, None, Gio.DBusSignalFlags.NONE, on_response)

        def called(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                self.conn.signal_unsubscribe(sub)
                self._fail("The desktop refused mouse control (%s)" % e.message)
        self.conn.call(PORTAL, PORTAL_PATH, iface, method, build(token), None, Gio.DBusCallFlags.NONE, 150000, None, called)

    def _fail(self, msg):
        self._error = msg
        self._ready.set()

    def _begin(self):
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._sender = self.conn.get_unique_name()[1:].replace(".", "_")
        except GLib.Error as e:
            return self._fail("No desktop connection (%s)" % e.message)
        v = GLib.Variant
        self._request(RD, "CreateSession", lambda t: v("(a{sv})", ({"handle_token": v("s", t), "session_handle_token": v("s", self._tok())},)), self._created)

    def _created(self, code, res):
        if code != 0 or "session_handle" not in res:
            return self._fail("The desktop would not start mouse control")
        self.session = res["session_handle"]
        v = GLib.Variant

        def build(t):
            opts = {"handle_token": v("s", t), "types": v("u", 2), "persist_mode": v("u", 2)}
            try:
                tok = open(TOKEN_FILE).read().strip()
                if tok:
                    opts["restore_token"] = v("s", tok)
            except OSError:
                pass
            return v("(oa{sv})", (self.session, opts))
        self._request(RD, "SelectDevices", build, self._devices)

    def _devices(self, code, res):
        if code != 0:
            return self._fail("Mouse control was not allowed")
        v = GLib.Variant
        self._request(CAST, "SelectSources", lambda t: v("(oa{sv})", (self.session, {"handle_token": v("s", t), "types": v("u", 1), "multiple": v("b", False),
                                                                                    "cursor_mode": v("u", 2)})), self._sources)

    def _sources(self, code, res):
        if code != 0:
            return self._fail("Mouse control was not allowed")
        v = GLib.Variant
        self._request(RD, "Start", lambda t: v("(osa{sv})", (self.session, "", {"handle_token": v("s", t)})), self._started)

    def _started(self, code, res):
        streams = res.get("streams") or []
        if code != 0 or not streams:
            return self._fail("Mouse control was cancelled")
        self.node, props = streams[0][0], streams[0][1]
        self.origin = tuple(props.get("position") or (0, 0))
        self.size = tuple(props.get("size") or (1920, 1080))
        tok = res.get("restore_token")
        if tok:
            try:
                os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                with open(TOKEN_FILE, "w") as f:
                    f.write(tok)
            except OSError:
                pass
        self.backend = "portal"
        self._ready.set()

    # ---------- raw actions ----------
    def _notify(self, method, sig, *args):
        self.conn.call_sync(PORTAL, PORTAL_PATH, RD, method, GLib.Variant(sig, (self.session, {}) + args), None, Gio.DBusCallFlags.NONE, 2000, None)

    def _warp(self, x, y):
        if self.backend == "portal":
            lx, ly = x - self.origin[0], y - self.origin[1]
            if not (-2 <= lx <= self.size[0] + 2 and -2 <= ly <= self.size[1] + 2):
                raise RuntimeError("That point is not on the screen Jarvis may control (%dx%d at %d,%d)" % (self.size[0], self.size[1], self.origin[0], self.origin[1]))
            self._notify("NotifyPointerMotionAbsolute", "(oa{sv}udd)", self.node, float(lx), float(ly))
        else:
            subprocess.run(["ydotool", "mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y))], capture_output=True, timeout=5)
        self.pos, self.pos_t = (x, y), time.time()

    def _button(self, name, down):
        code = BTN.get(name, 272)
        if self.backend == "portal":
            self._notify("NotifyPointerButton", "(oa{sv}iu)", code, 1 if down else 0)
        else:
            n = {"left": 0, "right": 1, "middle": 2}.get(name, 0)
            subprocess.run(["ydotool", "click", "0x%x" % ((0x40 if down else 0x80) + n)], capture_output=True, timeout=5)

    # ---------- what Jarvis uses ----------
    def start_point(self):
        if self.pos and time.time() - self.pos_t < 5:      # we just put it there; asking KWin where it is costs a script round trip
            return self.pos
        p = self.cursor_pos()
        if p:
            return p
        return self.pos or (self.origin[0] + self.size[0] / 2, self.origin[1] + self.size[1] / 2)

    def move_to(self, x, y):
        self.ensure()
        t0 = time.perf_counter()
        for dt, px, py in human_path(self.start_point(), (float(x), float(y))):
            lag = t0 + dt - time.perf_counter()
            if lag > 0:
                time.sleep(lag)
            self._warp(px, py)

    def click(self, button="left", double=False):
        self.ensure()
        time.sleep(random.uniform(0.07, 0.16))                   # a beat to settle, then a natural press
        for i in range(2 if double else 1):
            self._button(button, True)
            time.sleep(random.uniform(0.05, 0.11))
            self._button(button, False)
            if double and i == 0:
                time.sleep(random.uniform(0.07, 0.12))

    def drag(self, x0, y0, x1, y1):
        self.move_to(x0, y0)
        time.sleep(random.uniform(0.08, 0.15))
        self._button("left", True)
        time.sleep(random.uniform(0.08, 0.14))
        self.pos = (x0, y0)
        t0 = time.perf_counter()
        for dt, px, py in human_path((x0, y0), (float(x1), float(y1))):
            lag = t0 + dt - time.perf_counter()
            if lag > 0:
                time.sleep(lag)
            self._warp(px, py)
        time.sleep(random.uniform(0.06, 0.12))
        self._button("left", False)

    def scroll(self, steps):
        """Positive scrolls down. Done a notch at a time, with natural pauses."""
        self.ensure()
        n = int(steps)
        for _ in range(abs(n)):
            if self.backend == "portal":
                self._notify("NotifyPointerAxisDiscrete", "(oa{sv}ui)", 0, 1 if n > 0 else -1)
            else:
                subprocess.run(["ydotool", "mousemove", "--wheel", "-x", "0", "-y", "-1" if n > 0 else "1"], capture_output=True, timeout=5)
            time.sleep(random.uniform(0.05, 0.13))

    def close(self):
        if self.conn and self.session:
            try:
                self.conn.call(PORTAL, self.session, "org.freedesktop.portal.Session", "Close", None, None, Gio.DBusCallFlags.NONE, 1000, None, None)
            except Exception:
                pass
        self.session = self.backend = None

