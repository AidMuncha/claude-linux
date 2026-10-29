"""Checking for, downloading, verifying and installing updates.

An update is a .tar.gz plus a small manifest (latest.json) next to it:
    {"version": "1.2.0", "url": "claude-linux-1.2.0.tar.gz", "sha256": "...", "signature": "<base64 Ed25519>",
     "size": 123456, "notes": "What changed", "required": true}
The signature is made with a private key only the author holds; the matching public key ships inside the app
(update_pubkey.pem). Nothing is installed unless the checksum AND the signature are correct.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

from .paths import HERE
from .version import VERSION

PUBKEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "update_pubkey.pem")
URL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "update_url.txt")
INSTALLED_DIR = os.path.expanduser("~/.local/share/claude-linux-app")
MAX_BYTES = 60 * 1024 * 1024
REQUIRED_FILES = ("app.py", "claude_linux/__init__.py", "claude_linux/version.py", "ui/index.html")


class UpdateError(Exception):
    """A problem the user can be told about in plain words."""


def manifest_url():
    """Where to look for updates; empty means this copy never checks (nothing is contacted)."""
    url = os.environ.get("CL_UPDATE_URL")
    if url is None:
        try:
            url = open(URL_FILE).read().strip()
        except OSError:
            url = ""
    return url.strip()


def target_dir():
    """The folder an update may replace: the installed copy only, never a development checkout."""
    forced = os.environ.get("CL_UPDATE_TARGET")
    if forced:
        return forced
    return INSTALLED_DIR if os.path.realpath(HERE) == os.path.realpath(INSTALLED_DIR) else None


def parse_version(text):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text).strip())
    if not m:
        raise UpdateError("Unreadable version: %r" % (text,))
    return tuple(int(x) for x in m.groups())


def is_newer(remote, local=VERSION):
    return parse_version(remote) > parse_version(local)


def check_url(url):
    """https only; plain http is allowed just for this computer (used by the tests)."""
    p = urllib.parse.urlparse(url)
    local = p.hostname in ("localhost", "127.0.0.1", "::1")
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise UpdateError("Updates must come from an https address")
    return url


def fetch_manifest(url, timeout=8):
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "claude-linux/" + VERSION, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(200000)
    try:
        m = json.loads(raw)
        parse_version(m["version"])
        for k in ("url", "sha256", "signature"):
            if not isinstance(m[k], str) or not m[k]:
                raise KeyError(k)
    except (ValueError, KeyError, TypeError, UpdateError) as e:
        raise UpdateError("The update information is not valid (%s)" % e)
    m["url"] = check_url(urllib.parse.urljoin(url, m["url"]))
    m["required"] = bool(m.get("required", True))
    m["notes"] = str(m.get("notes", ""))[:1500]
    return m


def verify_signature(path, signature_b64, pubkey=None):
    """True only for a correct Ed25519 signature of the file, made by the key matching `pubkey`."""
    pubkey = pubkey or os.environ.get("CL_UPDATE_PUBKEY") or PUBKEY
    if not shutil.which("openssl"):
        raise UpdateError("openssl is needed to check updates and was not found")
    with tempfile.NamedTemporaryFile() as sig:
        try:
            sig.write(base64.b64decode(signature_b64, validate=True))
        except ValueError:
            return False
        sig.flush()
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", pubkey, "-rawin", "-in", path, "-sigfile", sig.name],
                           capture_output=True, text=True)
    return r.returncode == 0


def download(url, dest, expected_size=None, progress=None):
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "claude-linux/" + VERSION})
    done, sha = 0, hashlib.sha256()
    with urllib.request.urlopen(req, timeout=20) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or expected_size or 0)
        if total > MAX_BYTES:
            raise UpdateError("The update is unexpectedly large")
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_BYTES:
                raise UpdateError("The update is unexpectedly large")
            out.write(chunk)
            sha.update(chunk)
            if progress:
                progress(done, total)
    return sha.hexdigest()


def safe_extract(tar_path, dest):
    """Unpacks into dest, refusing anything that would land outside it (absolute paths, .., links)."""
    os.makedirs(dest)
    root = os.path.realpath(dest)
    with tarfile.open(tar_path, "r:gz") as t:
        for m in t.getmembers():
            if not (m.isfile() or m.isdir()):
                raise UpdateError("The update contains something unexpected (%s)" % m.name)
            name = os.path.normpath(m.name)
            if os.path.isabs(name) or name == ".." or name.startswith("../") or not os.path.realpath(os.path.join(dest, name)).startswith(root):
                raise UpdateError("The update tries to write outside its folder")
        t.extractall(dest, filter="data")
    for f in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(dest, f)):
            raise UpdateError("The update is incomplete (missing %s)" % f)


def swap_in(staged, target):
    """Replaces target with staged; the previous copy stays beside it as <target>.old until the next start."""
    old = target + ".old"
    shutil.rmtree(old, ignore_errors=True)
    os.rename(target, old)
    try:
        os.rename(staged, target)
    except OSError:
        os.rename(old, target)           # put the working copy back
        raise


def cleanup_old(target):
    if target:
        shutil.rmtree(target + ".old", ignore_errors=True)
        shutil.rmtree(target + ".new", ignore_errors=True)


def download_and_install(manifest, target, progress=None):
    """Downloads, verifies checksum and signature, unpacks and swaps. Raises UpdateError with a readable message."""
    if not target:
        raise UpdateError("This copy was not installed with the installer, so it will not update itself")
    tmp = tempfile.mkdtemp(prefix="claude-linux-update-")
    try:
        tgz = os.path.join(tmp, "update.tar.gz")
        try:
            digest = download(manifest["url"], tgz, manifest.get("size"), progress)
        except OSError as e:
            raise UpdateError("The download failed: %s" % e)
        if digest != manifest["sha256"].lower():
            raise UpdateError("The download is damaged (checksum does not match)")
        if not verify_signature(tgz, manifest["signature"]):
            raise UpdateError("The update is not signed by the Claude Linux author, so it was not installed")
        staged = target + ".new"
        shutil.rmtree(staged, ignore_errors=True)
        try:
            safe_extract(tgz, staged)
            swap_in(staged, target)
        except (OSError, tarfile.TarError) as e:
            shutil.rmtree(staged, ignore_errors=True)
            raise UpdateError("Could not install the update: %s" % e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
