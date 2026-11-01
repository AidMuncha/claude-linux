"""Google Lens, used out of sight: a headless Brave (no window, its own throw-away profile) opens Lens, hands it the picture, waits for the results
and reads the text and links off the page. Nothing appears on screen. The browser is driven over the DevTools protocol with a tiny WebSocket client,
so no extra packages are needed."""
import base64
import json
import os
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

BROWSERS = ("brave-browser", "brave", "google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "microsoft-edge", "microsoft-edge-stable", "vivaldi", "vivaldi-stable", "opera")


class Cdp:
    """Just enough of a WebSocket client to talk to the browser's DevTools endpoint."""

    def __init__(self, url):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                           % (u.path, u.hostname, u.port, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("the browser closed the connection")
            head += chunk
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    def _read(self, size):
        while len(self.buf) < size:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("the browser closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:size], self.buf[size:]
        return out

    def _frame(self):
        msg = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            msg += data
            if b1 & 0x80:
                return b1 & 0x0F, msg

    def send(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        return self.n

    def call(self, method, timeout=30, **params):
        want = self.send(method, **params)
        end = time.time() + timeout
        self.sock.settimeout(timeout)
        while time.time() < end:
            op, msg = self._frame()
            if op != 1:
                continue
            ev = json.loads(msg)
            if ev.get("id") == want:
                if "error" in ev:
                    raise RuntimeError(ev["error"].get("message", "browser error"))
                return ev.get("result") or {}
        raise RuntimeError("the browser did not answer")

    def evaluate(self, js):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return (r.get("result") or {}).get("value")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


CHROMIUM = ("brave", "chrome", "chromium", "edge", "vivaldi", "opera", "thorium", "ungoogled")


def desktop_command(desktop_id):
    """The command line (list) a .desktop file launches, without the %U-style placeholders."""
    dirs = [os.path.expanduser("~/.local/share/applications"), "/usr/share/applications", "/usr/local/share/applications",
            "/var/lib/flatpak/exports/share/applications", os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]
    for d in dirs:
        path = os.path.join(d, desktop_id)
        if os.path.isfile(path):
            for line in open(path, errors="replace"):
                if line.startswith("Exec="):
                    return [t for t in shlex.split(line[5:].strip()) if not t.startswith("%") and t != "env" and "=" not in t.split("/")[0]]
    return None


def browser():
    """The command to start the user's own default browser if it can be driven in the background (Chrome, Brave, Edge, Vivaldi, Chromium...);
    otherwise any such browser that is installed. Firefox cannot be driven this way."""
    try:
        default = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        default = ""
    if default and any(k in default.lower() for k in CHROMIUM):
        cmd = desktop_command(default)
        if cmd and (shutil.which(cmd[0]) or os.path.isfile(cmd[0])):
            return cmd
    for name in BROWSERS:
        p = shutil.which(name)
        if p:
            return [p]
    return None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


EXTRACT = """(() => {
  const text = document.body ? document.body.innerText : '';
  const links = [...document.querySelectorAll('a[href^="http"]')].map(a => ({t: (a.innerText || a.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').slice(0, 110), u: a.href}))
    .filter(l => l.t && !/(^https?:\\/\\/(www\\.)?(google|gstatic|accounts\\.google)\\.)/.test(l.u));
  return {title: document.title, url: location.href, text: text.slice(0, 4000), links: links.slice(0, 40)};
})()"""


def search(target, wait=12):
    """Runs Google Lens on a web address or a local picture. Returns {title, text, links} or raises RuntimeError."""
    exe = browser()
    if not exe:
        raise RuntimeError("the default browser cannot be driven in the background and no Chrome-type browser is installed")
    is_url = target.startswith(("http://", "https://"))
    if not is_url and not os.path.isfile(target):
        raise RuntimeError("no such file: %s" % target)
    prof, port = tempfile.mkdtemp(prefix="jarvis-lens-"), free_port()
    proc = subprocess.Popen(exe + ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--mute-audio", "--window-size=1280,900",
                             "--user-data-dir=" + prof, "--remote-debugging-port=%d" % port, "--lang=en-US", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    cdp = None
    try:
        ws = None
        for _ in range(60):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2))
                ws = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"), None)
                if ws:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws:
            raise RuntimeError("the hidden browser did not start")
        cdp = Cdp(ws)
        cdp.call("Page.enable")
        cdp.call("Network.enable")
        cdp.call("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
                 acceptLanguage="en-US,en")
        if is_url:
            cdp.call("Page.navigate", url="https://lens.google.com/uploadbyurl?hl=en&url=" + urllib.parse.quote(target, safe=""))
        else:
            cdp.call("Page.navigate", url="https://lens.google.com/?hl=en")
            deadline = time.time() + 20
            node = None
            while time.time() < deadline and not node:
                time.sleep(1)
                doc = cdp.call("DOM.getDocument", depth=-1, pierce=True)
                found = cdp.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="input[type=file]")
                node = found.get("nodeId") or None
            if not node:
                raise RuntimeError("Lens showed no upload box (Google may be asking for a consent or robot check)")
            cdp.call("DOM.setFileInputFiles", nodeId=node, files=[os.path.abspath(target)])
        time.sleep(wait)
        info = cdp.evaluate(EXTRACT) or {}
        low = (info.get("text") or "").lower() + (info.get("url") or "").lower()
        if "unusual traffic" in low or "/sorry/" in low or "captcha" in low:
            raise RuntimeError("Google asked for a robot check")
        if "consent.google" in low:
            raise RuntimeError("Google asked for cookie consent")
        return info
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)


def run(target):
    info = search(target)
    lines = ["Google Lens results:", "page: %s" % info.get("title", "")]
    text = " ".join((info.get("text") or "").split())
    if text:
        lines.append("text on the results page: " + text[:1500])
    seen = set()
    for l in info.get("links") or []:
        if l["u"] in seen:
            continue
        seen.add(l["u"])
        lines.append("- %s  %s" % (l["t"], l["u"]))
        if len(seen) >= 12:
            break
    return "\n".join(lines)
