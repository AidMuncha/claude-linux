"""Builds ui/index.html from ui/index.tpl.html: inlines the css/ and js/ parts and the logo path from ui/logo.svg."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "ui")


def build():
    logo = re.search(r'd="([^"]+)"', open(os.path.join(UI, "logo.svg")).read()).group(1)
    tpl = open(os.path.join(UI, "index.tpl.html")).read()
    out = re.sub(r"<!--#include (\S+?)-->\n", lambda m: open(os.path.join(UI, m.group(1))).read(), tpl)
    out = out.replace("%%LOGO%%", logo)
    path = os.path.join(UI, "index.html")
    with open(path, "w") as f:
        f.write(out)
    return path


def stale():
    """True when ui/index.html is missing or older than any file it is built from."""
    out = os.path.join(UI, "index.html")
    if not os.path.exists(out):
        return True
    newest = 0
    for base, _dirs, files in os.walk(UI):
        for f in files:
            path = os.path.join(base, f)
            if path != out:
                newest = max(newest, os.path.getmtime(path))
    return newest > os.path.getmtime(out)


def ensure():
    """Rebuild only when something changed, so editing ui/css or ui/js and relaunching just works."""
    if stale():
        build()


if __name__ == "__main__":
    print("built", build(), file=sys.stderr)
