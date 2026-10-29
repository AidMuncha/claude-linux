"""Test helpers for updates: a throw-away copy of the project, a test signing key, a release in dist/, and a local web server."""
import env  # noqa: F401  (must be first)

import functools
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(env.HERE)
sys.path.insert(0, ROOT)
import release  # noqa: E402


class World:
    """A fake author: temp project copy at version 1.0.0 + its own key. make(version) publishes into self.dist and serves it."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="cl-upd-")
        self.root = os.path.join(self.tmp, "project")
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "dist", "tests", "__pycache__", "*.backup*", "claude-linux-installer.sh"))
        self.key = os.path.join(self.tmp, "test-private.pem")
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", self.key], check=True, capture_output=True)
        self.pub = os.path.join(self.tmp, "test-public.pem")
        open(self.pub, "w").write(release.derive_public(self.key))
        shutil.copy(self.pub, os.path.join(self.root, "claude_linux/update_pubkey.pem"))
        open(os.path.join(self.root, "claude_linux/version.py"), "w").write('"""x"""\nVERSION = "1.0.0"\n')
        self.dist = os.path.join(self.tmp, "dist")
        os.makedirs(self.dist)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=self.dist))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/latest.json" % self.server.server_address[1]

    def make(self, version, notes="Faster and prettier", required=True):
        return release.make_package(version, self.dist, key=self.key, notes=notes, required=required, root=self.root)

    def installed_copy(self, name="installed"):
        """A copy of the 1.0.0 app, like ~/.local/share/claude-linux-app, that an update may replace."""
        dest = os.path.join(self.tmp, name)
        shutil.copytree(self.root, dest, ignore=shutil.ignore_patterns("__pycache__"))
        open(os.path.join(dest, "claude_linux/version.py"), "w").write('"""x"""\nVERSION = "1.0.0"\n')      # the project itself moves on with each release
        return dest

    def close(self):
        self.server.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass
