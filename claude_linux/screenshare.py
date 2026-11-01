"""Screen sharing the way Discord does it: the desktop's ScreenCast portal shows its own "what do you want to share?" picker and
hands over a PipeWire stream; GStreamer turns that stream into a rolling folder of small JPEG frames that Jarvis looks at.
The portal remembers the choice (restore token), so after the first time the picker is skipped.
All portal calls run on the GTK main loop; `frames()` can be called from any thread."""
import glob
import os
import shutil
import subprocess
import tempfile
import time

from gi.repository import Gio, GLib

from .paths import DATA

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
CAST = "org.freedesktop.portal.ScreenCast"
TOKEN_FILE = os.path.join(DATA, "jarvis", "screencast.token")
FPS = int(os.environ.get("JARVIS_FPS") or 10)   # frames captured per second. Each costs a JPEG encode: 4 is ~9% of a core, 20 is ~35%, 60 is a whole core
KEEP = FPS * 10                           # about 10 seconds of history
WIDTH = 1280


class ScreenShare:
    def __init__(self):
        self.conn = None
        self.session = None
        self.proc = None
        self.dir = None
        self.node = None
        self._n = 0
        self._sender = ""
        self._done = None
        self._stopped = False
        self.own = True                       # False when the stream belongs to the mouse-control session, which must stay open

    # ---------- start (asks the desktop, then starts GStreamer) ----------
    def start(self, done):
        """done(ok, message) is called on the main loop when frames are flowing or it failed."""
        self._done = done
        GLib.idle_add(lambda: self._begin() and False)

    def attach(self, conn, session, node, done):
        """Watches through the screen the mouse-control session was already allowed (entire screen), so nothing more is asked. Runs on the main loop."""
        self.conn, self.session, self.node, self.own, self._done = conn, session, node, False, done
        self._open_remote()

    def _fail(self, msg):
        done, self._done = self._done, None
        self.stop()
        if done:
            done(False, msg)

    def _tok(self):
        self._n += 1
        return "jarvis%d_%d" % (os.getpid(), self._n)

    def _request(self, method, build, handler):
        """A portal call that answers through a Request object's Response signal."""
        token = self._tok()
        path = "%s/request/%s/%s" % (PORTAL_PATH, self._sender, token)

        def on_response(_c, _s, _p, _i, _n, params):
            code, results = params.unpack()
            self.conn.signal_unsubscribe(sub)
            if not self._stopped:
                handler(code, results)
        sub = self.conn.signal_subscribe(PORTAL, "org.freedesktop.portal.Request", "Response", path, None, Gio.DBusSignalFlags.NONE, on_response)

        def called(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                self.conn.signal_unsubscribe(sub)
                self._fail("The desktop refused the screen share (%s)" % e.message)
        self.conn.call(PORTAL, PORTAL_PATH, CAST, method, build(token), None, Gio.DBusCallFlags.NONE, 120000, None, called)

    def _begin(self):
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._sender = self.conn.get_unique_name()[1:].replace(".", "_")
        except GLib.Error as e:
            return self._fail("No desktop connection for screen sharing (%s)" % e.message)
        v = GLib.Variant
        self._request("CreateSession", lambda t: v("(a{sv})", ({"handle_token": v("s", t), "session_handle_token": v("s", self._tok())},)), self._created)

    def _created(self, code, res):
        if code != 0 or "session_handle" not in res:
            return self._fail("The desktop would not start a screen share")
        self.session = res["session_handle"]
        v = GLib.Variant

        def build(t):
            opts = {"handle_token": v("s", t), "types": v("u", 1), "multiple": v("b", False), "cursor_mode": v("u", 2), "persist_mode": v("u", 2)}
            try:
                tok = open(TOKEN_FILE).read().strip()
                if tok:
                    opts["restore_token"] = v("s", tok)
            except OSError:
                pass
            return v("(oa{sv})", (self.session, opts))
        self._request("SelectSources", build, self._selected)

    def _selected(self, code, res):
        if code != 0:
            return self._fail("Screen sharing was not allowed")
        v = GLib.Variant
        self._request("Start", lambda t: v("(osa{sv})", (self.session, "", {"handle_token": v("s", t)})), self._started)

    def _started(self, code, res):
        streams = res.get("streams") or []
        if code != 0 or not streams:
            return self._fail("Screen sharing was cancelled")
        self.node = streams[0][0]
        tok = res.get("restore_token")
        if tok:
            try:
                os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                with open(TOKEN_FILE, "w") as f:
                    f.write(tok)
            except OSError:
                pass
        self._open_remote()

    def _open_remote(self):
        v = GLib.Variant
        self.conn.call_with_unix_fd_list(PORTAL, PORTAL_PATH, CAST, "OpenPipeWireRemote", v("(oa{sv})", (self.session, {})), GLib.VariantType("(h)"),
                                         Gio.DBusCallFlags.NONE, 5000, None, None, self._remote)

    def _remote(self, conn, res, _data=None):
        try:
            out, fds = conn.call_with_unix_fd_list_finish(res)
            fd = fds.get(out.unpack()[0])
        except Exception as e:
            return self._fail("Could not open the screen stream (%s)" % e)
        self.dir = tempfile.mkdtemp(prefix="jarvis-share-")
        # KWin's stream claims pixel-aspect-ratio=1/2147483647; videoscale keeps that "shape" and squashes the picture to 1 pixel high, so it is reset to square.
        # The video/x-raw in front matters: without it capssetter lets any format through and pipewiresrc fails with "target not found"
        pipe = ("pipewiresrc fd=%d path=%d do-timestamp=true keepalive-time=500 ! video/x-raw ! capssetter caps=video/x-raw,pixel-aspect-ratio=1/1 ! videoconvert ! videorate ! "
                "video/x-raw,framerate=%d/1 ! videoscale ! video/x-raw,width=%d,pixel-aspect-ratio=1/1 ! jpegenc quality=65 ! multifilesink location=%s/f%%06d.jpg max-files=%d" % (fd, self.node, FPS, WIDTH, self.dir, KEEP))
        try:
            self.proc = subprocess.Popen(["gst-launch-1.0", "-q"] + pipe.split(), pass_fds=(fd,), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError as e:
            os.close(fd)
            return self._fail("GStreamer is needed for screen sharing (%s)" % e)
        os.close(fd)
        GLib.timeout_add(500, self._check, time.time())

    def _check(self, since):
        """Waits for the first frame; reports a failed pipeline in plain words."""
        if self._stopped or not self._done:
            return False
        if self.proc and self.proc.poll() is not None:
            err = (self.proc.stderr.read() or "").strip().splitlines()
            self._fail("The screen stream stopped: %s" % (err[-1][:120] if err else "unknown error"))
            return False
        if glob.glob(os.path.join(self.dir, "f*.jpg")):
            done, self._done = self._done, None
            done(True, "")
            return False
        if time.time() - since > 8:
            self._fail("No picture arrived from the screen share")
            return False
        return True

    # ---------- the frames ----------
    def frames(self, count=4, gap=1.2):
        """Up to `count` recent frames, oldest first, at least `gap` seconds apart. Returns [(jpeg bytes, seconds ago)]."""
        if not self.dir:
            return []
        files = sorted(glob.glob(os.path.join(self.dir, "f*.jpg")))
        now, picked, last = time.time(), [], None
        for p in reversed(files):
            try:
                t = os.path.getmtime(p)
            except OSError:
                continue
            if last is None and now - t < 0.15:
                continue                      # the newest file may still be being written
            if last is not None and last - t < gap:
                continue
            try:
                with open(p, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if len(data) < 500:
                continue
            picked.append((data, max(0.0, now - t)))
            last = t
            if len(picked) >= count:
                break
        return picked[::-1]

    def motion(self, back=0.6):
        """How much the screen changed over the last `back` seconds, 0 to 1 (from the frames' file sizes: a still screen compresses to the same size)."""
        if not self.dir:
            return 0.0
        files = sorted(glob.glob(os.path.join(self.dir, "f*.jpg")))
        if len(files) < 4:
            return 0.0
        try:
            new = os.path.getsize(files[-2])
            n_back = max(2, int(back * FPS))
            old = os.path.getsize(files[-1 - n_back]) if len(files) > n_back + 1 else new
        except OSError:
            return 0.0
        return min(1.0, abs(new - old) / max(new, old, 1) * 8)

    def frames_at(self, times):
        """For each wanted time (epoch seconds) the frame that was on screen then, as [(jpeg bytes, seconds ago)]. Duplicates collapse."""
        if not self.dir:
            return []
        stamped = []
        for p in glob.glob(os.path.join(self.dir, "f*.jpg")):
            try:
                stamped.append((os.path.getmtime(p), p))
            except OSError:
                pass
        stamped.sort()
        if len(stamped) < 2:
            return []
        stamped = stamped[:-1]                    # the newest file may still be being written
        now, out, used = time.time(), [], set()
        for want in times:
            t, p = min(stamped, key=lambda tp: abs(tp[0] - want))
            if p in used:
                continue
            try:
                with open(p, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if len(data) < 500:
                continue
            used.add(p)
            out.append((data, max(0.0, now - t)))
        return out

    def stop(self):
        self._stopped = True
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
        if self.conn and self.session and self.own:
            try:
                self.conn.call(PORTAL, self.session, "org.freedesktop.portal.Session", "Close", None, None, Gio.DBusCallFlags.NONE, 1000, None, None)
            except Exception:
                pass
        self.session = None
        if self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None
