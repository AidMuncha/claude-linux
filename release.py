#!/usr/bin/env python3
"""Pushes a new update: bumps the version, builds the signed package and the manifest into dist/.

    python3 release.py 1.1.0 --notes "Faster startup, new themes"          # users must update (default)
    python3 release.py 1.1.0 --notes "..." --optional                      # users may choose "Later"

Then upload everything in dist/ to the address in claude_linux/update_url.txt (the manifest, latest.json, is the file
users' apps look at). The private key never leaves ~/.local/share/claude-linux-release/ - back it up: without it nobody
can be updated any more and everyone would have to reinstall.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEY = os.path.expanduser("~/.local/share/claude-linux-release/private.pem")
PACKAGE = ("app.py", "build.py", "icon.svg", "install.sh", "claude_linux")
UI_PARTS = ("index.html", "index.tpl.html", "logo.svg", "css", "js")


def read_version(root=ROOT):
    return re.search(r'VERSION = "([^"]+)"', open(os.path.join(root, "claude_linux/version.py")).read()).group(1)


def tuple_of(v):
    return tuple(int(x) for x in v.split("."))


def derive_public(key):
    return subprocess.run(["openssl", "pkey", "-in", key, "-pubout"], capture_output=True, text=True, check=True).stdout


def sign(path, key):
    sig = tempfile.NamedTemporaryFile(delete=False)
    sig.close()
    try:
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", key, "-rawin", "-in", path, "-out", sig.name], check=True, capture_output=True)
        return base64.b64encode(open(sig.name, "rb").read()).decode()
    finally:
        os.unlink(sig.name)


def make_package(version, out_dir, key=DEFAULT_KEY, notes="", required=True, root=ROOT, bump=True, force=False):
    """Returns the manifest dict. Writes claude-linux-<version>.tar.gz and latest.json into out_dir."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Version must look like 1.2.3")
    if not os.path.exists(key):
        raise SystemExit("No signing key at %s" % key)
    shipped = open(os.path.join(root, "claude_linux/update_pubkey.pem")).read().strip()
    if derive_public(key).strip() != shipped:
        raise SystemExit("The signing key does not match claude_linux/update_pubkey.pem: apps already installed would reject this update")
    if not force and tuple_of(version) <= tuple_of(read_version(root)) and bump:
        raise SystemExit("Version %s is not newer than the current %s (use --force to override)" % (version, read_version(root)))
    if bump:
        p = os.path.join(root, "claude_linux/version.py")
        s = open(p).read()
        open(p, "w").write(re.sub(r'VERSION = "[^"]+"', 'VERSION = "%s"' % version, s))
    subprocess.run([sys.executable, os.path.join(root, "build.py")], check=True, capture_output=True)
    os.makedirs(out_dir, exist_ok=True)
    stage = tempfile.mkdtemp()
    try:
        for f in PACKAGE:
            src = os.path.join(root, f)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(stage, f))
        os.makedirs(os.path.join(stage, "ui"))
        for f in UI_PARTS:
            src = os.path.join(root, "ui", f)
            (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(stage, "ui", f))
        for base, dirs, _files in os.walk(stage):
            for d in [d for d in dirs if d == "__pycache__"]:
                shutil.rmtree(os.path.join(base, d))
                dirs.remove(d)
        for old in os.listdir(out_dir):                      # only the newest package is kept in dist/
            if re.fullmatch(r"claude-linux-\d+\.\d+\.\d+\.tar\.gz", old):
                os.unlink(os.path.join(out_dir, old))
        tgz = os.path.join(out_dir, "claude-linux-%s.tar.gz" % version)
        with tarfile.open(tgz, "w:gz") as t:
            for name in sorted(os.listdir(stage)):
                t.add(os.path.join(stage, name), arcname=name)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    data = open(tgz, "rb").read()
    manifest = {"version": version, "url": os.path.basename(tgz), "sha256": hashlib.sha256(data).hexdigest(), "signature": sign(tgz, key),
                "size": len(data), "notes": notes, "required": required}
    with open(os.path.join(out_dir, "latest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest


def publish(version, root=ROOT):
    """Commits the release (dist/ and sources) and pushes it, so everyone's apps see it. Needs a git remote called origin."""
    def git(*a, check=True):
        r = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)
        if check and r.returncode:
            raise SystemExit("git %s failed:\n%s" % (" ".join(a[:2]), (r.stderr or r.stdout).strip()))
        return r
    if git("rev-parse", "--git-dir", check=False).returncode:
        raise SystemExit("This folder is not a git repository yet (run: git init, then add your GitHub repo as 'origin').")
    if git("remote", "get-url", "origin", check=False).returncode:
        raise SystemExit("No 'origin' remote: add your GitHub repo with  git remote add origin <url>")
    git("add", "-A")
    git("commit", "-m", "Release %s" % version, "--allow-empty")
    git("push", "origin", "HEAD")


def write_get_script(out_dir, root=ROOT):
    """dist/get.sh: the text-only script behind the one-line install. Built from update_url.txt, so it needs no editing."""
    url = open(os.path.join(root, "claude_linux/update_url.txt")).read().strip()
    if not url:
        return None
    base = url.rsplit("/", 1)[0]
    body = open(os.path.join(root, "get.sh.in")).read()
    body = body.replace("@@BASE@@", base).replace("@@MANIFEST@@", url).replace("@@PUBKEY@@", open(os.path.join(root, "claude_linux/update_pubkey.pem")).read().strip())
    path = os.path.join(out_dir, "get.sh")
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return base


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version")
    ap.add_argument("--notes", default="")
    ap.add_argument("--optional", action="store_true", help="let users pick Later instead of requiring the update")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--publish", action="store_true", help="also git commit and push (this is what makes it live)")
    a = ap.parse_args()
    m = make_package(a.version, a.out, notes=a.notes, required=not a.optional, force=a.force)
    subprocess.run(["bash", os.path.join(ROOT, "make-installer.sh"), os.path.join(a.out, "claude-linux-installer.sh")], check=True)
    base = write_get_script(a.out)
    url = open(os.path.join(ROOT, "claude_linux/update_url.txt")).read().strip()
    print("\nVersion %s is ready in %s (%d KB, %s)" % (m["version"], a.out, m["size"] // 1024, "required" if m["required"] else "optional"))
    if base:
        print("One-line install for friends:  curl -fsSL %s/get.sh | bash" % base)
    if a.publish:
        publish(a.version)
        print("Published. Installed copies will offer the update within a few hours (or at their next start).")
        return
    print("Upload to:", url or "(no update address set yet: put one in claude_linux/update_url.txt, then rebuild the installer)")


if __name__ == "__main__":
    main()
