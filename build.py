"""Builds ui/index.html from ui/index.tpl.html: inlines the css/ and js/ parts and the logo path from ui/logo.svg."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "ui")


PAGES = ("index", "hud", "screen")  # hud.html: Jarvis' always-on-top window (orb, captions); screen.html: the see-through overlay for the reading highlight


def build():
    logo = re.search(r'd="([^"]+)"', open(os.path.join(UI, "logo.svg")).read()).group(1)
    for name in PAGES:
        tpl = open(os.path.join(UI, name + ".tpl.html")).read()
        out = re.sub(r"<!--#include (\S+?)-->\n", lambda m: open(os.path.join(UI, m.group(1))).read(), tpl)
        out = out.replace("%%LOGO%%", logo)
        with open(os.path.join(UI, name + ".html"), "w") as f:
            f.write(out)
    return os.path.join(UI, "index.html")


def stale():
    """True when ui/index.html is missing or older than any file it is built from."""
    outs = [os.path.join(UI, n + ".html") for n in PAGES]
    if not all(os.path.exists(o) for o in outs):
        return True
    newest = 0
    for base, _dirs, files in os.walk(UI):
        for f in files:
            path = os.path.join(base, f)
            if path not in outs:
                newest = max(newest, os.path.getmtime(path))
    return newest > min(os.path.getmtime(o) for o in outs)


def ensure():
    """Rebuild only when something changed, so editing ui/css or ui/js and relaunching just works."""
    if stale():
        build()


if __name__ == "__main__":
    print("built", build(), file=sys.stderr)
