#!/usr/bin/env python3
"""Jarvis' eyes and hands as MCP tools, so what he does and what he then sees come back in ONE step: `click` moves the mouse like a hand, clicks, and returns the
live screen a moment later as a picture, with no separate "take a screenshot, then Read the file" round trip. Talks to Jarvis' control socket.
Started by Claude Code itself (stdio, newline-delimited JSON-RPC); nothing here runs on its own."""
import base64
import json
import os
import re
import socket
import sys
import time


def ctl(*argv):
    path = os.environ.get("JARVIS_CTL") or os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "jarvis-ctl.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(120)
    s.connect(path)
    s.sendall((json.dumps({"argv": list(argv)}) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(1 << 20)
        if not chunk:
            break
        buf += chunk
    s.close()
    r = json.loads(buf or b"{}")
    if r.get("error"):
        raise RuntimeError(r["error"])
    return r.get("out", "")


def frames(count=1):
    """[(jpeg base64, seconds old)] of the live view; one fresh screenshot when the live view is off."""
    try:
        got = json.loads(ctl("lookraw", str(count)))
    except Exception:
        got = []
    if got:
        return [(f["data"], f["age"]) for f in got]
    out = ctl("look")
    res = []
    for path in re.findall(r"^(/\S+\.(?:png|jpg))", out, re.M):
        try:
            with open(path, "rb") as f:
                res.append((base64.b64encode(f.read()).decode(), 0.0))
            os.remove(path)
        except OSError:
            pass
    return res


def mark(data, at):
    """The picture with a red crosshair where the click went, so a miss shows and can be corrected."""
    try:
        import io
        from PIL import Image, ImageDraw
        im = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
        x, y = at
        d = ImageDraw.Draw(im)
        d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=(255, 0, 0), width=2)
        d.line((x - 15, y, x - 4, y), fill=(255, 0, 0), width=2)
        d.line((x + 4, y, x + 15, y), fill=(255, 0, 0), width=2)
        d.line((x, y - 15, x, y - 4), fill=(255, 0, 0), width=2)
        d.line((x, y + 4, x, y + 15), fill=(255, 0, 0), width=2)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return data


def view(text, count=1, settle=0.3, at=None):
    time.sleep(settle)                                   # let the screen react before looking
    content = [{"type": "text", "text": text}]
    for data, _age in frames(count):
        if at:
            data = mark(data, at)
        content.append({"type": "image", "data": data, "mimeType": "image/png" if data.startswith("iVBOR") else "image/jpeg"})
    return {"content": content}


def num(a, k):
    return str(float(a[k]))


PLAY_HELP = ("Run a whole plan of keyboard and mouse actions in one call, fast, then get the live screen. Actions run in order. Examples: "
             '{"key":"w","hold":1.5} hold W 1.5 s; {"keys":["ctrl","l"]} chord; {"hold":["w","shift"],"for":2,"do":[{"look":[80,0],"ms":300},{"click":"left"}]} sprint forward 2 s while turning right and clicking; '
             '{"look":[dx,dy],"ms":150} turn the camera (relative mouse pixels); {"click":"left","hold":0.1}; {"move":[x,y]} (picture pixels); {"scroll":3}; {"type":"text"}; {"wait":0.3}. '
             "Keys: letters, digits, space, shift, ctrl, alt, enter, esc, tab, up/down/left/right, f1-f12. Everything pressed is released at the end. Max 60 s per plan.")


def play(a):
    plan = a.get("actions")
    if not isinstance(plan, list):
        raise RuntimeError("actions must be a list")
    report = ctl("play", json.dumps(plan))
    return view(report + ". The screen now:", 1, 0.05)


def click_text(a):
    found = ctl("find", str(a["text"]))
    m = re.search(r"center (-?\d+) (-?\d+)", found)
    if not m:
        raise RuntimeError(found or "I can't see that text on the screen")
    x, y = m.group(1), m.group(2)
    ctl("click", x, y, *(["--right"] if a.get("right") else []), *(["--double"] if a.get("double") else []))
    return view("Clicked \"%s\" at %s %s (red crosshair). The screen now:" % (a["text"], x, y), at=(float(x), float(y)))


TOOLS = {
    "play": (PLAY_HELP, {"actions": {"type": "array", "items": {"type": "object"}}}, ["actions"], play),
    "screen_text": ("Read all the text on the screen with positions (x,y,w,h text), to understand a page, menu or game UI exactly. Faster and more exact than reading small text from a picture.",
                    {}, [], lambda a: {"content": [{"type": "text", "text": ctl("ocr")}]}),
    "find_text": ("Find where some text is on screen; returns its center x y (picture pixels) to click.", {"text": {"type": "string"}}, ["text"],
                  lambda a: {"content": [{"type": "text", "text": ctl("find", str(a["text"]))}]}),
    "look": ("See the screen right now (the live view). count = how many recent moments (1 to 5, default 1).",
             {"count": {"type": "integer"}}, [], lambda a: view("The screen now:", int(a.get("count") or 1), 0.0)),
    "click": ("Move the mouse to x,y like a hand, click, and get the screen right after as a picture. x,y are pixels of the screen pictures you are shown (1280 wide), read straight off the picture or from find_text. right/double optional.",
              {"x": {"type": "number"}, "y": {"type": "number"}, "right": {"type": "boolean"}, "double": {"type": "boolean"}}, ["x", "y"],
              lambda a: (ctl("click", num(a, "x"), num(a, "y"), *(["--right"] if a.get("right") else []), *(["--double"] if a.get("double") else [])),
                         view("Clicked. The red crosshair marks exactly where the click went; if it is not on the button, click again at the button's real center.", at=(float(a["x"]), float(a["y"]))))[1]),
    "click_text": ("Click a button, link, tab or field by the text on it: finds the text on screen and clicks its exact center. The most accurate way to click anything that has words on it; "
                   "use this instead of reading coordinates off the picture whenever the target has text. Returns the screen right after.",
                   {"text": {"type": "string"}, "right": {"type": "boolean"}, "double": {"type": "boolean"}}, ["text"], click_text),
    "move": ("Move the mouse to x,y (picture pixels) like a hand (hover) and get the screen right after.",
             {"x": {"type": "number"}, "y": {"type": "number"}}, ["x", "y"], lambda a: (ctl("move", num(a, "x"), num(a, "y")), view("Moved. The screen now:"))[1]),
    "scroll": ("Scroll at the current pointer (positive = down) and get the screen right after.",
               {"amount": {"type": "number"}}, ["amount"], lambda a: (ctl("scroll", num(a, "amount")), view("Scrolled. The screen now:"))[1]),
    "drag": ("Drag from x1,y1 to x2,y2 (picture pixels) and get the screen right after.",
             {"x1": {"type": "number"}, "y1": {"type": "number"}, "x2": {"type": "number"}, "y2": {"type": "number"}}, ["x1", "y1", "x2", "y2"],
             lambda a: (ctl("drag", num(a, "x1"), num(a, "y1"), num(a, "x2"), num(a, "y2")), view("Dragged. The screen now:"))[1]),
}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return {"protocolVersion": (msg.get("params") or {}).get("protocolVersion") or "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "jarvis", "version": "1"}}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": props, "required": req}} for n, (d, props, req, _f) in TOOLS.items()]}
    if method == "tools/call":
        p = msg.get("params") or {}
        tool = TOOLS.get(p.get("name"))
        if not tool:
            return {"isError": True, "content": [{"type": "text", "text": "unknown tool"}]}
        try:
            return tool[3](p.get("arguments") or {})
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    if method == "ping":
        return {}
    return None if mid is None else {}


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        res = handle(msg)
        if msg.get("id") is not None and res is not None:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
