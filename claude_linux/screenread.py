"""Reading what is actually on your screen: take a picture of the monitor the pointer is on, find the words in it (OCR, with the box of
every word), and read them aloud while a blue hologram, drawn by a see-through window over the real screen, sweeps through the words as
they are spoken. When he is done it turns green and fades. The picture is deleted as soon as the words have been found.

Everything returned to Jarvis (positions) is in picture pixels: the pixels of the pictures he sees of the screen (VIEW_W wide), the same space the
mouse commands take. He reads a spot off a picture and clicks it as is; turning that into real screen pixels is done here, never by him."""
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from .paths import DATA
from .screenshare import WIDTH as VIEW_W

JDIR = os.path.join(DATA, "jarvis")
VENV = os.path.join(JDIR, "venv")
PY = os.path.join(VENV, "bin", "python")
OCR_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_ocr.py")
MARKER = os.path.join(JDIR, "ocr.ok")


def norm(text):
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


_mon = {"t": 0.0, "v": []}


def monitors():
    """[(x, y, width, height)] in logical pixels, from KDE. Cached for a few seconds: every click converts coordinates."""
    if _mon["v"] and time.time() - _mon["t"] < 10:
        return _mon["v"]
    try:
        out = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=5).stdout
        res = []
        for o in json.loads(out)["outputs"]:
            if o.get("enabled"):
                sc = float(o.get("scale") or 1)
                res.append((o["pos"]["x"], o["pos"]["y"], o["size"]["width"] / sc, o["size"]["height"] / sc))
        _mon.update(t=time.time(), v=res)
        return res
    except Exception:
        return []


def monitor_at(pt):
    ms = monitors() or [(0, 0, 1920, 1080)]
    if pt:
        for m in ms:
            if m[0] <= pt[0] < m[0] + m[2] and m[1] <= pt[1] < m[1] + m[3]:
                return m
    return ms[0]


def view(pt):
    """(gx, gy, k, picture width, picture height) for the monitor at pt: one picture pixel is k screen pixels, counted from the monitor's corner gx,gy.
    The pictures Jarvis sees are scaled down (a 1920x1080 screen arrives 1280x720), so a spot he reads off one has to be scaled back up."""
    gx, gy, gw, gh = monitor_at(pt)
    k = gw / float(VIEW_W)
    return gx, gy, k, VIEW_W, int(round(gh / k))


def to_screen(pt, x, y):
    gx, gy, k, _w, _h = view(pt)
    return gx + x * k, gy + y * k


def to_view(pt, x, y):
    gx, gy, k, _w, _h = view(pt)
    return (x - gx) / k, (y - gy) / k


def sentence_ranges(words):
    """[(first word, one past the last)] split where a person would pause."""
    out, start, chars = [], 0, 0
    for i, w in enumerate(words):
        chars += len(w["t"]) + 1
        last = i + 1 == len(words)
        line_end = not last and words[i + 1]["l"] != w["l"]
        if last or re.search(r"[.!?:;][\"')\]]*$", w["t"]) or (line_end and chars >= 45) or i + 1 - start >= 26:
            out.append((start, i + 1))
            start, chars = i + 1, 0
    return out


class ScreenReader:
    def __init__(self, jarvis):
        self.j = jarvis
        self.proc = None
        self.lock = threading.Lock()
        self.overlay_ready = threading.Event()
        self.busy = False
        self.token = 0

    # ---------- the text finder ----------
    def ensure_ocr(self):
        if os.path.isfile(MARKER) and os.path.isfile(PY):
            return
        self.j.emit("setup", text="Installing the screen reader (first run only, a few minutes)…")
        try:
            if not os.path.isfile(PY):
                subprocess.run([sys.executable, "-m", "venv", VENV], check=True, capture_output=True, text=True)
            r = subprocess.run([PY, "-m", "pip", "install", "--quiet", "rapidocr", "onnxruntime"], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "pip failed")
            open(MARKER, "w").close()
        finally:
            self.j.emit("setup", text="")

    def _start(self):
        self.ensure_ocr()
        self.proc = subprocess.Popen([PY, "-I", OCR_SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        first = self._readline(60)
        if not first or "ready" not in first:
            err = json.loads(first).get("error") if first else "no answer"
            self._kill()
            raise RuntimeError(err)

    def _readline(self, timeout):
        if select.select([self.proc.stdout], [], [], timeout)[0]:
            return self.proc.stdout.readline()
        return ""

    def _kill(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.kill()

    def close(self):
        self._kill()

    def ocr(self, path):
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(path + "\n")
            self.proc.stdin.flush()
            line = self._readline(60)
            if not line:
                self._kill()
                raise RuntimeError("the screen reader did not answer")
        res = json.loads(line)
        if res.get("error"):
            raise RuntimeError(res["error"])
        return res

    # ---------- looking at the screen ----------
    def scan(self):
        """{'geo': (x, y, w, h), 'lines': [{'x','y','w','h','text','words':[{'t','x','y','w','h'}]}]} in reading order, global logical pixels."""
        if not shutil.which("spectacle"):
            raise RuntimeError("spectacle (the screenshot tool) was not found")
        pt = self.j.activity.cursor_pos()
        gx, gy, gw, gh = monitor_at(pt)
        shots = os.path.join(tempfile.gettempdir(), "jarvis-shots")
        os.makedirs(shots, exist_ok=True)
        img = os.path.join(shots, "read-%d.png" % int(time.time() * 1000))
        try:
            subprocess.run(["spectacle", "-b", "-n", "-m", "-o", img], capture_output=True, timeout=20)
            if not os.path.isfile(img):
                raise RuntimeError("the screenshot did not work")
            data = self.ocr(img)
        finally:
            try:
                os.remove(img)
            except OSError:
                pass
        sx, sy = gw / data["w"], gh / data["h"]
        lines = []
        for ln in data["lines"]:
            ws = [{"t": w["t"], "x": gx + w["x"] * sx, "y": gy + w["y"] * sy, "w": w["w"] * sx, "h": w["h"] * sy} for w in ln["words"]]
            x0, y0 = min(w["x"] for w in ws), min(w["y"] for w in ws)
            lines.append({"x": x0, "y": y0, "w": max(w["x"] + w["w"] for w in ws) - x0, "h": max(w["y"] + w["h"] for w in ws) - y0,
                          "text": " ".join(w["t"] for w in ws), "words": ws})
        lines.sort(key=lambda l: l["y"])
        rows = []
        for l in lines:                                       # lines side by side count as one row, read left to right
            if rows and abs((l["y"] + l["h"] / 2) - rows[-1][0]) < 0.5 * min(l["h"], rows[-1][1]):
                rows[-1][2].append(l)
            else:
                rows.append([l["y"] + l["h"] / 2, l["h"], [l]])
        ordered = [l for r in rows for l in sorted(r[2], key=lambda l: l["x"])]
        return {"geo": (gx, gy, gw, gh), "lines": ordered}

    @staticmethod
    def in_region(l, region):
        x, y, w, h = region
        return x <= l["x"] + l["w"] / 2 <= x + w and y <= l["y"] + l["h"] / 2 <= y + h

    @staticmethod
    def parse_region(text, geo):
        """X,Y,W,H in picture pixels, as screen pixels."""
        parts = [float(p) for p in text.split(",")]
        if len(parts) != 4:
            raise ValueError
        k = geo[2] / float(VIEW_W)
        return (geo[0] + parts[0] * k, geo[1] + parts[1] * k, parts[2] * k, parts[3] * k)

    @staticmethod
    def pic(geo, x, y, w, h):
        """A box in screen pixels, in picture pixels."""
        k = geo[2] / float(VIEW_W)
        return (x - geo[0]) / k, (y - geo[1]) / k, w / k, h / k

    def find(self, scan, phrase):
        """Words of the first place on screen that spells `phrase`, or None."""
        want = norm(phrase).split()
        flat = [(norm(w["t"]), w) for l in scan["lines"] for w in l["words"]]
        flat = [(n, w) for n, w in flat if n]
        for i in range(len(flat)):
            if flat[i][0] == want[0] or (len(want) == 1 and want[0] in flat[i][0]):
                run = flat[i:i + len(want)]
                if len(run) == len(want) and all(r[0] == t or (k == len(want) - 1 and t in r[0]) for k, (r, t) in enumerate(zip(run, want))):
                    return [w for _n, w in run]
        return None

    @staticmethod
    def box(words):
        x0, y0 = min(w["x"] for w in words), min(w["y"] for w in words)
        x1, y1 = max(w["x"] + w["w"] for w in words), max(w["y"] + w["h"] for w in words)
        return x0, y0, x1 - x0, y1 - y0

    # ---------- commands (what jarvis_ctl.py sends) ----------
    def run(self, cmd, argv):
        if cmd == "ocr":
            return self.cmd_ocr(argv)
        if cmd == "find":
            return self.cmd_find(" ".join(argv))
        if cmd == "highlight":
            return self.cmd_highlight(" ".join(argv))
        return self.cmd_read(argv)

    def cmd_ocr(self, argv):
        scan = self.scan()
        geo = scan["geo"]
        region = self.parse_region(argv[argv.index("--region") + 1], geo) if "--region" in argv else None
        rows = ["picture %dx%d (the same pixels as the pictures you see and the mouse commands). Each line: x,y,w,h text" % (VIEW_W, round(geo[3] * VIEW_W / geo[2]))]
        for l in scan["lines"]:
            if region is None or self.in_region(l, region):
                rows.append("%d,%d,%d,%d %s" % (self.pic(geo, l["x"], l["y"], l["w"], l["h"]) + (l["text"],)))
        return {"out": "\n".join(rows[:400])}

    def cmd_find(self, phrase):
        if not phrase.strip():
            return {"error": "usage: find TEXT"}
        scan = self.scan()
        words = self.find(scan, phrase)
        if not words:
            return {"error": "I can't see \"%s\" on the screen" % phrase}
        x, y, w, h = self.pic(scan["geo"], *self.box(words))
        return {"out": "found at %d,%d size %dx%d, center %d %d" % (x, y, w, h, x + w / 2, y + h / 2)}

    def cmd_highlight(self, phrase):
        if not phrase.strip():
            return {"error": "usage: highlight TEXT"}
        scan = self.scan()
        words = self.find(scan, phrase)
        if not words:
            return {"error": "I can't see \"%s\" on the screen" % phrase}
        x, y, w, h = self.box(words)
        flat = [dict(t=wd["t"], x=wd["x"], y=wd["y"], w=wd["w"], h=wd["h"], l=0) for wd in words]
        self._show(scan, flat)
        self._item(0, len(flat), 0.15, 0.5 + 0.12 * len(flat))
        time.sleep(0.5 + 0.12 * len(flat))
        self._finish()
        x, y, w, h = self.pic(scan["geo"], x, y, w, h)
        return {"out": "highlighted at %d,%d size %dx%d, center %d %d" % (x, y, w, h, x + w / 2, y + h / 2)}

    def cmd_read(self, argv):
        opts, i = {}, 0
        while i < len(argv):
            if argv[i] in ("--from", "--to", "--region", "--max-chars") and i + 1 < len(argv):
                opts[argv[i]] = argv[i + 1]
                i += 2
            else:
                i += 1
        scan = self.scan()
        lines = scan["lines"]
        if "--region" in opts:
            lines = [l for l in lines if self.in_region(l, self.parse_region(opts["--region"], scan["geo"]))]
        first, last = 0, len(lines) - 1
        if "--from" in opts:
            key = norm(opts["--from"])
            hit = [k for k, l in enumerate(lines) if key in norm(l["text"])]
            if not hit:
                return {"error": "I can't find \"%s\" on the screen" % opts["--from"]}
            first = hit[0]
        if "--to" in opts:
            key = norm(opts["--to"])
            hit = [k for k, l in enumerate(lines) if k >= first and key in norm(l["text"])]
            if hit:
                last = hit[0]
        words = []
        for k, l in enumerate(lines[first:last + 1]):
            words += [dict(wd, l=k) for wd in l["words"]]
        if not words:
            return {"error": "I can't see any text there"}
        limit = int(opts.get("--max-chars", 900))
        ranges, total, keep = sentence_ranges(words), 0, 0
        for a, b in ranges:
            total += sum(len(w["t"]) + 1 for w in words[a:b])
            keep = b
            if total >= limit:
                break
        words = words[:keep]
        ranges = [r for r in ranges if r[1] <= keep]
        j = self.j
        gen = j.gen
        self._show(scan, words)
        for a, b in ranges:
            j._say(" ".join(w["t"] for w in words[a:b]), screen=(a, b))
        deadline = time.time() + 180
        while time.time() < deadline and j.gen == gen and j.mode and (j.pending > 0 or j.voice.busy()):
            time.sleep(0.05)
        done = j.gen == gen
        if done:
            time.sleep(0.15)
            self._finish()
        else:
            self.abort()
        text = " ".join(w["t"] for w in words)
        return {"out": ("Read aloud: " if done else "Interrupted while reading: ") + text}

    # ---------- the overlay window (see gtkapp.show_screen and ui/js/screen.js) ----------
    def _show(self, scan, words):
        gx, gy, _gw, _gh = scan["geo"]
        self.overlay_ready.clear()
        self.busy = True
        self.token += 1
        self.j.push("jarvis_screen", {"ev": "words", "words": [dict(w, x=w["x"] - gx, y=w["y"] - gy) for w in words]})
        self.overlay_ready.wait(4)

    def _item(self, a, b, delay, dur):
        self.j.push("jarvis_screen", {"ev": "read", "a": a, "b": b, "delay": delay, "dur": dur})

    def _finish(self):
        self.j.push("jarvis_screen", {"ev": "finish"})
        threading.Timer(2.6, self._close, args=(self.token,)).start()

    def _close(self, token):
        if self.busy and token == self.token:
            self.busy = False
            self.j.push("jarvis_screen", {"ev": "close"})

    def abort(self):
        if self.busy:
            self.j.push("jarvis_screen", {"ev": "abort"})
            self.busy = False
            self.j.push("jarvis_screen", {"ev": "close"})
