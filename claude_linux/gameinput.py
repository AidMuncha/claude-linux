"""Fast, batched keyboard and mouse input for playing games and driving apps: one call carries a whole little plan (hold W for two seconds while turning
left and swinging) instead of one round trip per key. Keys go through ydotool (Linux key codes); relative mouse motion and buttons go through the pointer.
Actions are plain dicts, run in order:
  {"key": "w", "hold": 1.5}                         hold a key down for 1.5 s (default: a quick tap)
  {"keys": ["ctrl", "l"]}                            a chord, pressed together then released
  {"hold": ["w", "shift"], "for": 2, "do": [...]}    keep these keys down for the time while doing the nested actions
  {"look": [dx, dy], "ms": 150}                      turn the camera: relative mouse motion in pixels, spread over ms
  {"click": "left", "hold": 0.1}                     press a mouse button (left, right, middle), optionally holding it
  {"move": [x, y]}  {"scroll": 3}  {"type": "text"}  {"wait": 0.3}"""
import subprocess
import time

CODES = {
    "esc": 1, "escape": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11, "minus": 12, "-": 12, "equal": 13, "=": 13,
    "backspace": 14, "tab": 15, "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25, "[": 26, "]": 27,
    "enter": 28, "return": 28, "ctrl": 29, "control": 29, "lctrl": 29, "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38,
    ";": 39, "'": 40, "`": 41, "shift": 42, "lshift": 42, "\\": 43, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50, ",": 51, ".": 52, "/": 53,
    "rshift": 54, "alt": 56, "lalt": 56, "space": 57, " ": 57, "capslock": 58, "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65,
    "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88, "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106, "end": 107, "down": 108,
    "pagedown": 109, "insert": 110, "delete": 111, "super": 125, "meta": 125, "win": 125, "ralt": 100, "rctrl": 97,
}


class GameInput:
    def __init__(self, pointer, env):
        self.pointer = pointer
        self.env = env
        self.down = set()

    # ---------- keys ----------
    def _code(self, name):
        c = CODES.get(str(name).lower())
        if c is None:
            raise ValueError("unknown key %r (use letters, digits, space, shift, ctrl, alt, enter, esc, tab, up/down/left/right, f1-f12...)" % name)
        return c

    def _ydo(self, *args):
        subprocess.run(["ydotool"] + list(args), env=self.env, capture_output=True, timeout=5)

    def key_down(self, names):
        codes = [self._code(n) for n in names]
        self._ydo("key", *["%d:1" % c for c in codes])
        self.down.update(codes)

    def key_up(self, names):
        codes = [self._code(n) for n in names]
        self._ydo("key", *["%d:0" % c for c in reversed(codes)])
        self.down.difference_update(codes)

    def release_all(self):
        """Never leave a key or button stuck down."""
        if self.down:
            self._ydo("key", *["%d:0" % c for c in sorted(self.down)])
            self.down.clear()
        for b in ("left", "right", "middle"):
            try:
                self.pointer._button(b, False)
            except Exception:
                pass

    # ---------- mouse ----------
    def look(self, dx, dy, ms=0):
        self.pointer.ensure()
        if self.pointer.backend != "portal":
            self._ydo("mousemove", "-x", str(int(dx)), "-y", str(int(dy)))
            return
        steps = max(1, int(ms / 8)) if ms else 1
        sx, sy = dx / steps, dy / steps
        t0 = time.perf_counter()
        for i in range(steps):
            self.pointer._notify("NotifyPointerMotion", "(oa{sv}dd)", float(sx), float(sy))
            lag = t0 + (i + 1) * ms / 1000.0 / steps - time.perf_counter()
            if lag > 0:
                time.sleep(lag)

    def button(self, name, down):
        self.pointer.ensure()
        self.pointer._button(name, down)

    # ---------- the plan ----------
    def run(self, actions, budget=60.0):
        """Runs the actions in order; returns a short report. Everything pressed is released at the end, whatever happens."""
        if isinstance(actions, dict):
            actions = [actions]
        start, done = time.time(), 0
        try:
            for a in actions:
                if time.time() - start > budget:
                    raise RuntimeError("stopped after %d s (that is the most one plan may take)" % budget)
                self._one(a)
                done += 1
        finally:
            self.release_all()
        return "did %d action%s in %.1f s" % (done, "" if done == 1 else "s", time.time() - start)

    def _one(self, a):
        if isinstance(a, str):
            a = {"key": a}
        if "wait" in a:
            time.sleep(min(float(a["wait"]), 30))
        elif "hold" in a and isinstance(a["hold"], list):
            keys = a["hold"]
            self.key_down(keys)
            try:
                end = time.time() + min(float(a.get("for", 0.5)), 30)
                for sub in a.get("do") or []:
                    self._one(sub)
                left = end - time.time()
                if left > 0:
                    time.sleep(left)
            finally:
                self.key_up(keys)
        elif "key" in a:
            h = min(float(a.get("hold", 0.04)), 30)
            self.key_down([a["key"]])
            try:
                time.sleep(h)
            finally:
                self.key_up([a["key"]])
        elif "keys" in a:
            self.key_down(a["keys"])
            time.sleep(0.05)
            self.key_up(a["keys"])
        elif "look" in a:
            self.look(a["look"][0], a["look"][1], float(a.get("ms", 0)))
        elif "click" in a:
            b = str(a["click"])
            self.button(b, True)
            try:
                time.sleep(min(float(a.get("hold", 0.05)), 30))
            finally:
                self.button(b, False)
        elif "move" in a:
            self.pointer.move_to(float(a["move"][0]), float(a["move"][1]))
        elif "scroll" in a:
            self.pointer.scroll(float(a["scroll"]))
        elif "type" in a:
            self._ydo("type", "-d", "8", str(a["type"]))
        else:
            raise ValueError("unknown action %r" % (a,))
