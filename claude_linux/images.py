"""Pictures for Jarvis: `img web|match|onscreen|like|sheet` (see HELP). Web search and opening pages happen here; the picture matching runs in
Jarvis' virtualenv (jarvis_img.py, it needs opencv)."""
import html as html_lib
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

from . import lens
from .screenread import PY, VIEW_W, monitor_at

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_img.py")
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
HELP = ("img web QUERY [-n N] [--download] [--show] | img lens FILE_OR_URL [\"what it shows\"] | img match FILE_OR_URL \"what it shows\" [-n N] | img onscreen FILE [--threshold 0.8] | "
        "img like FILE [DIR] [-n N] | img sheet FILE_OR_DIR...")


def shots_dir():
    d = os.path.join(tempfile.gettempdir(), "jarvis-shots")
    os.makedirs(d, exist_ok=True)
    return d


def get(url, timeout=15, headers=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def opts(argv, flag, default):
    if flag in argv:
        i = argv.index(flag)
        val = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
        return val
    return default


def flag(argv, name):
    if name in argv:
        argv.remove(name)
        return True
    return False


def opn(url):
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def search(query):
    """Picture results [{title, image, thumbnail, url, width, height}]: DuckDuckGo first, Bing when DuckDuckGo refuses."""
    try:
        found = search_ddg(query)
    except Exception:
        found = None
    return found or search_bing(query)


def search_bing(query):
    page = get("https://www.bing.com/images/async?" + urllib.parse.urlencode({"q": query, "first": "1", "count": "35", "adlt": "off"})).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'\sm="(\{.*?\})"', page):
        try:
            d = json.loads(html_lib.unescape(m.group(1)))
        except ValueError:
            continue
        if d.get("murl"):
            out.append({"title": d.get("t", ""), "image": d["murl"], "thumbnail": d.get("turl"), "url": d.get("purl"), "width": "?", "height": "?"})
    if not out:
        raise RuntimeError("no picture results")
    return out


def search_ddg(query):
    html = get("https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query})).decode("utf-8", "replace")
    vqd = re.search(r"vqd=[\"']?([\d-]+)", html).group(1)
    data = json.loads(get("https://duckduckgo.com/i.js?" + urllib.parse.urlencode({"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,,,", "p": "1"}),
                          headers={"Referer": "https://duckduckgo.com/"}))
    return data.get("results") or []


def lens_search(argv):
    """Google Lens through a hidden browser (nothing appears on screen). If Google refuses or the browser is missing, Jarvis' own matching does the job."""
    if not argv:
        return {"error": "usage: img lens FILE_OR_URL [\"what it shows\"]"}
    target, desc = os.path.expanduser(argv[0]), " ".join(argv[1:]).strip()
    try:
        return {"out": lens.run(target)}
    except Exception as e:
        why = str(e)
    if not desc:
        return {"error": "Google Lens was not available (%s). Run `img lens FILE_OR_URL \"a few words about what it shows\"` or `img match` so Jarvis' own matching can do it" % why}
    out = match([argv[0], desc])
    if "out" in out:
        out["out"] = "Google Lens was not available (%s), so this is Jarvis' own matching instead:\n%s" % (why, out["out"])
    return out


def match(argv):
    """Finds the picture (or look-alikes) on the web with our own matching: search for what it shows, fetch the candidates, compare each against the picture."""
    count = int(opts(argv, "-n", 16))
    if len(argv) < 2:
        return {"error": "usage: img match FILE_OR_URL \"what it shows\"  (look at the picture first and describe it in a few words)"}
    target, query = os.path.expanduser(argv[0]), " ".join(argv[1:])
    work = tempfile.mkdtemp(prefix="match-", dir=shots_dir())
    try:
        if re.match(r"https?://", target):
            ref = os.path.join(work, "ref.jpg")
            try:
                data = get(target)
            except Exception as e:
                return {"error": "could not download the picture (%s)" % e}
            with open(ref, "wb") as f:
                f.write(data)
        elif os.path.isfile(target):
            ref = target
        else:
            return {"error": "no such file: %s" % target}
        try:
            results = search(query)[:count]
        except Exception as e:
            return {"error": "the web search failed (%s)" % e}
        def fetch(item):
            i, r = item
            for url in (r.get("thumbnail"), r.get("image")):          # the small copy is quicker, the real one is the fallback
                if not url:
                    continue
                try:
                    data = get(url, timeout=10)
                except Exception:
                    continue
                if len(data) > 500:
                    path = os.path.join(work, "c%d.jpg" % i)
                    with open(path, "wb") as f:
                        f.write(data)
                    return path, r
            return None
        with ThreadPoolExecutor(8) as pool:
            files = dict(x for x in pool.map(fetch, enumerate(results)) if x)
        if not files:
            return {"error": "no candidate pictures could be fetched for \"%s\"" % query}
        out = run_script(["rank", ref] + list(files))
        if "error" in out:
            return out
        rows = []
        for line in out["out"].splitlines():
            score, n, path = line.split(" ", 2)
            rows.append((float(score), int(n), files[path]))
        rows.sort(key=lambda r: r[0], reverse=True)
        lines = ["Compared %d web pictures for \"%s\". Best first (1.00 identical; 0.8+ with many matching details is the same picture):" % (len(rows), query)]
        for score, n, r in rows[:8]:
            lines.append("%.2f (%d details)  %s  image: %s  page: %s" % (score, n, (r.get("title") or "").strip()[:60], r.get("image"), r.get("url")))
        return {"out": "\n".join(lines)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def web(argv):
    count, download, show = int(opts(argv, "-n", 8)), flag(argv, "--download"), flag(argv, "--show")
    query = " ".join(argv).strip()
    if not query:
        return {"error": "usage: img web QUERY [-n N] [--download] [--show]"}
    page = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query, "iax": "images", "ia": "images"})
    if show:
        opn(page)
    try:
        results = search(query)
    except Exception as e:
        if show:
            return {"out": "image search opened in the browser (the results could not be read here: %s)" % e}
        return {"error": "the image search failed (%s). Try `img web \"%s\" --show` to open it in the browser" % (e, query)}
    if not results:
        return {"error": "no pictures found for \"%s\"" % query}
    out, folder = [], None
    if download:
        folder = tempfile.mkdtemp(prefix="web-", dir=shots_dir())
    for i, r in enumerate(results[:count], 1):
        line = "%d. %s (%sx%s) image: %s  page: %s" % (i, (r.get("title") or "").strip()[:80], r.get("width", "?"), r.get("height", "?"), r.get("image"), r.get("url"))
        if folder:
            try:
                ext = os.path.splitext(urllib.parse.urlparse(r["image"]).path)[1].lower()
                path = os.path.join(folder, "%d%s" % (i, ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") else ".jpg"))
                with open(path, "wb") as f:
                    f.write(get(r.get("thumbnail") or r["image"], timeout=10))
                line += "  saved: " + path
            except Exception:
                line += "  (could not download)"
        out.append(line)
    if folder:
        out.append("Saved in %s. Read the ones you need, then delete the folder (rm -r) when done." % folder)
    return {"out": "\n".join(out)}


def screenshot():
    if not shutil.which("spectacle"):
        raise RuntimeError("spectacle (the screenshot tool) was not found")
    img = os.path.join(shots_dir(), "img-%d.png" % int(time.time() * 1000))
    subprocess.run(["spectacle", "-b", "-n", "-m", "-o", img], capture_output=True, timeout=20)
    if not os.path.isfile(img):
        raise RuntimeError("the screenshot did not work")
    return img


def snapshot(pt):
    """One fresh screenshot of the monitor the pointer is on, for when the live view is off."""
    try:
        path = screenshot()
    except RuntimeError as e:
        return {"error": str(e)}
    try:                                                   # the same size as the live view, so its pixels are the ones the mouse commands take
        from PIL import Image
        with Image.open(path) as im:
            small = im.convert("RGB").resize((VIEW_W, round(im.height * VIEW_W / im.width)), Image.LANCZOS)
        os.remove(path)
        path = path[:-4] + ".jpg"
        small.save(path, quality=85)
    except Exception:
        pass
    return {"out": "The live view is off, so this is a single screenshot. Read it, then rm it:\n" + path}


def run_script(args, timeout=120):
    if not os.path.isfile(PY):
        return {"error": "the image tools are not installed yet (Jarvis installs them with his voice and screen reading); say something to him first"}
    r = subprocess.run([PY, "-I", SCRIPT] + args, capture_output=True, text=True, timeout=timeout)
    out = r.stdout.strip()
    if r.returncode == 1 and out:
        return {"error": out}
    if r.returncode != 0:
        return {"error": (r.stderr.strip().splitlines() or ["image tool failed"])[-1]}
    return {"out": out}


def onscreen(argv, jarvis):
    thr = opts(argv, "--threshold", "0.8")
    path = os.path.expanduser(" ".join(argv).strip())
    if not os.path.isfile(path):
        return {"error": "usage: img onscreen FILE [--threshold 0.8]  (FILE must exist)"}
    _gx, _gy, gw, gh = monitor_at(jarvis.activity.cursor_pos())
    shot = screenshot()
    try:                                                   # answers in picture pixels, like everything else he is told
        return run_script(["onscreen", path, shot, "0,0,%s,%s" % (VIEW_W, VIEW_W * gh / gw), thr])
    finally:
        try:
            os.remove(shot)
        except OSError:
            pass


def like(argv):
    count = int(opts(argv, "-n", 10))
    if not argv or not os.path.isfile(os.path.expanduser(argv[0])):
        return {"error": "usage: img like FILE [DIR] [-n N]"}
    root = os.path.expanduser(argv[1]) if len(argv) > 1 else os.path.expanduser("~/Pictures")
    if not os.path.isdir(root):
        return {"error": "no such folder: %s" % root}
    return run_script(["like", os.path.expanduser(argv[0]), root, str(count)], timeout=300)


def sheet(argv):
    files = []
    for a in argv:
        a = os.path.expanduser(a)
        if os.path.isdir(a):
            files += sorted(os.path.join(a, f) for f in os.listdir(a) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")))
        elif os.path.isfile(a):
            files.append(a)
    files = files[:48]
    if not files:
        return {"error": "usage: img sheet FILE_OR_DIR...  (no pictures found)"}
    out = os.path.join(shots_dir(), "sheet-%d.png" % int(time.time() * 1000))
    r = run_script(["sheet", out] + files)
    if "out" in r:
        r["out"] += "\nRead the first line (the picture), then rm it. Numbers on the tiles match the list."
    return r


def run(argv, jarvis):
    if not argv or argv[0] not in ("web", "lens", "match", "onscreen", "like", "sheet"):
        return {"error": "usage: " + HELP}
    cmd, rest = argv[0], list(argv[1:])
    if cmd == "web":
        return web(rest)
    if cmd == "lens":
        return lens_search(rest)
    if cmd == "match":
        return match(rest)
    if cmd == "onscreen":
        return onscreen(rest, jarvis)
    if cmd == "like":
        return like(rest)
    return sheet(rest)
