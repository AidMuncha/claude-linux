"""Starting things: Steam games (read straight from Steam's own library files) and installed desktop apps. Used both by Jarvis' fast path
(\"launch Marvel Rivals\" starts at once, without waiting for Claude) and by the `games`/`game`/`apps`/`launch` commands Claude can run."""
import difflib
import glob
import os
import re
import subprocess

from gi.repository import Gio

HOME = os.path.expanduser("~")
STEAM_ROOTS = [os.path.join(HOME, ".local/share/Steam"), os.path.join(HOME, ".steam/steam"), os.path.join(HOME, ".var/app/com.valvesoftware.Steam/.local/share/Steam")]
SKIP = re.compile(r"proton|steam linux runtime|steamworks common|steamvr|redistributable|dedicated server|\bsdk\b", re.I)
LAUNCH_RE = re.compile(r"^\W*(?:jarvis\W+)?(?:please\W+)?(?:launch|start|run|play|open|boot up|fire up)\s+(?:up\s+)?(?:the\s+)?(.+?)(?:\s+(?:on steam|for me|please|now|game))*\W*$", re.I)


def norm(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def _libraries():
    libs, seen = [], set()
    for root in STEAM_ROOTS:
        if not os.path.isdir(root):
            continue
        paths = [root]
        try:
            paths += re.findall(r'"path"\s+"([^"]+)"', open(os.path.join(root, "steamapps", "libraryfolders.vdf")).read())
        except OSError:
            pass
        for p in paths:
            real = os.path.realpath(p)
            if real not in seen and os.path.isdir(os.path.join(real, "steamapps")):
                seen.add(real)
                libs.append(real)
    return libs


def installed_games():
    """[{'appid', 'name'}] of fully installed Steam games (tools such as Proton are left out), sorted by name."""
    games, seen = [], set()
    for lib in _libraries():
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                text = open(acf, errors="replace").read()
                appid = re.search(r'"appid"\s+"(\d+)"', text).group(1)
                name = re.search(r'"name"\s+"([^"]*)"', text).group(1)
                flags = int(re.search(r'"StateFlags"\s+"(\d+)"', text).group(1))
            except (OSError, AttributeError, ValueError):
                continue
            if flags & 4 and appid not in seen and not SKIP.search(name):
                seen.add(appid)
                games.append({"appid": appid, "name": name})
    return sorted(games, key=lambda g: g["name"].lower())


def _best(items, query, key, threshold):
    q = " ".join(w for w in norm(query).split() if w not in ("the", "game", "please"))
    if not q:
        return None
    scored = []
    for it in items:
        n = norm(key(it))
        if n == q:
            s = 1.0
        elif n.startswith(q) or q.startswith(n) and len(n) >= 4:
            s = 0.95
        elif all(w in n.split() for w in q.split()):
            s = 0.9
        else:
            s = difflib.SequenceMatcher(None, q, n).ratio()
        scored.append((s, it))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored and scored[0][0] >= threshold else None


def find_game(query, threshold=0.8):
    return _best(installed_games(), query, lambda g: g["name"], threshold)


def launch_game(game):
    subprocess.Popen(["steam", "steam://rungameid/%s" % game["appid"]], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apps():
    out = []
    for a in Gio.AppInfo.get_all():
        try:
            if a.should_show():
                out.append({"name": a.get_display_name() or a.get_name(), "id": a.get_id() or ""})
        except Exception:
            continue
    return sorted(out, key=lambda a: a["name"].lower())


def find_app(query, strict=True):
    q = norm(query)
    items = apps()
    if strict:                          # the fast path only acts on a clear match: the whole name, or the name starting with what was said
        tiers = [lambda n: n == q, lambda n: len(q) >= 4 and n.startswith(q + " "), lambda n: len(q) >= 4 and q in n.split()]
        for ok in tiers:                # the whole name, then the name starting with it, then it as a word in the name; act only if exactly one app fits
            hits = [a for a in items if ok(norm(a["name"]))]
            if hits:
                return hits[0] if len(hits) == 1 else None
        return None
    return _best(items, query, lambda a: a["name"], 0.6)


def launch_app(app):
    subprocess.Popen(["gtk-launch", app["id"]], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(cmd, argv):
    """The commands Claude can run through jarvis_ctl.py."""
    arg = " ".join(argv).strip()
    if cmd == "games":
        g = [x for x in installed_games() if not arg or norm(arg) in norm(x["name"])]
        return {"out": "\n".join("%s  %s" % (x["appid"], x["name"]) for x in g) or "No installed Steam games found" + (" matching that" if arg else "")}
    if cmd == "game":
        if not arg:
            return {"error": "usage: game NAME"}
        g = find_game(arg, 0.6)
        if not g:
            names = ", ".join(x["name"] for x in installed_games()[:15])
            return {"error": "No installed Steam game matches \"%s\". Installed: %s" % (arg, names or "none")}
        launch_game(g)
        return {"out": "Launching %s (Steam app %s). It takes a little while to start." % (g["name"], g["appid"])}
    if cmd == "apps":
        a = [x for x in apps() if not arg or norm(arg) in norm(x["name"]) or norm(arg) in norm(x["id"])]
        return {"out": "\n".join("%s  (%s)" % (x["name"], x["id"]) for x in a[:80]) or "No installed apps match"}
    if cmd == "launch":
        if not arg:
            return {"error": "usage: launch NAME"}
        a = find_app(arg, strict=False)
        if not a:
            return {"error": "No installed app matches \"%s\". Try `apps` to list them." % arg}
        launch_app(a)
        return {"out": "Launched %s" % a["name"]}
    return {"error": "unknown command"}
