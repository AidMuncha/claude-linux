import env  # noqa: F401  (must be first)

import base64
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import unittest

from gi.repository import GLib

import updsrv
from claude_linux import update
from claude_linux.core import Core


def pump_until(cond, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end and not cond():
        if not GLib.MainContext.default().iteration(False):
            time.sleep(0.01)
    return cond()


def make_tar(path, members):
    """members: [(name, bytes|None(dir)|('link', target))]"""
    with tarfile.open(path, "w:gz") as t:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            if data is None:
                ti.type = tarfile.DIRTYPE
                t.addfile(ti)
            elif isinstance(data, tuple):
                ti.type, ti.linkname = tarfile.SYMTYPE, data[1]
                t.addfile(ti)
            else:
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))


class Versions(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(update.parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(update.parse_version("v10.0.1"), (10, 0, 1))
        for bad in ("1.2", "a.b.c", "", "1.2.3.4", "1.2.3-beta"):
            with self.assertRaises(update.UpdateError):
                update.parse_version(bad)
        self.assertTrue(update.is_newer("1.0.1", "1.0.0"))
        self.assertTrue(update.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(update.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(update.is_newer("0.9.9", "1.0.0"))

    def test_only_https_or_this_computer(self):
        update.check_url("https://example.com/x.json")
        update.check_url("http://127.0.0.1:8000/x.json")
        update.check_url("http://localhost/x.json")
        for bad in ("http://example.com/x.json", "ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "//example.com/x"):
            with self.assertRaises(update.UpdateError, msg=bad):
                update.check_url(bad)


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = updsrv.World()
        cls.m = cls.w.make("1.0.1", notes="Notes here")
        os.environ["CL_UPDATE_PUBKEY"] = cls.w.pub

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("CL_UPDATE_PUBKEY", None)
        cls.w.close()

    def tgz(self):
        return os.path.join(self.w.dist, "claude-linux-1.0.1.tar.gz")


class Manifest(World):
    def test_release_output(self):
        m = json.load(open(os.path.join(self.w.dist, "latest.json")))
        self.assertEqual((m["version"], m["url"], m["required"], m["notes"]), ("1.0.1", "claude-linux-1.0.1.tar.gz", True, "Notes here"))
        self.assertEqual(m["size"], os.path.getsize(self.tgz()))
        with tarfile.open(self.tgz()) as t:
            names = t.getnames()
        for need in ("app.py", "claude_linux/update.py", "claude_linux/update_pubkey.pem", "ui/index.html", "ui/js/update.js"):
            self.assertIn(need, names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.startswith("tests") or "private" in n])
        self.assertIn('VERSION = "1.0.1"', open(os.path.join(self.w.root, "claude_linux/version.py")).read())

    def test_fetch_valid_manifest_resolves_relative_url(self):
        m = update.fetch_manifest(self.w.url)
        self.assertEqual(m["version"], "1.0.1")
        self.assertEqual(m["url"], self.w.url.replace("latest.json", "claude-linux-1.0.1.tar.gz"))
        self.assertTrue(m["required"])

    def test_fetch_rejects_bad_manifests(self):
        good = json.load(open(os.path.join(self.w.dist, "latest.json")))
        path = os.path.join(self.w.dist, "bad.json")
        for label, doc in (("not json", "{nope"), ("no sha", json.dumps({k: v for k, v in good.items() if k != "sha256"})),
                           ("bad version", json.dumps(dict(good, version="soon"))), ("remote http url", json.dumps(dict(good, url="http://evil.example/x.tgz"))),
                           ("list", "[]")):
            open(path, "w").write(doc)
            with self.assertRaises(update.UpdateError, msg=label):
                update.fetch_manifest(self.w.url.replace("latest.json", "bad.json"))

    def test_unreachable_server_is_an_oserror_not_a_crash(self):
        with self.assertRaises(OSError):
            update.fetch_manifest("http://127.0.0.1:1/latest.json", timeout=2)


class Signatures(World):
    def sig(self):
        return json.load(open(os.path.join(self.w.dist, "latest.json")))["signature"]

    def test_good_signature_verifies(self):
        self.assertTrue(update.verify_signature(self.tgz(), self.sig()))

    def test_tampered_file_is_rejected(self):
        bad = tempfile.NamedTemporaryFile(delete=False)
        bad.write(open(self.tgz(), "rb").read() + b"x")
        bad.close()
        self.addCleanup(os.unlink, bad.name)
        self.assertFalse(update.verify_signature(bad.name, self.sig()))

    def test_signature_from_a_different_key_is_rejected(self):
        other = updsrv.World()
        self.addCleanup(other.close)
        m = other.make("1.0.1")
        self.assertFalse(update.verify_signature(self.tgz(), m["signature"]))

    def test_garbage_signatures_are_rejected(self):
        for s in ("", "not base64!!", base64.b64encode(b"short").decode(), base64.b64encode(os.urandom(64)).decode()):
            self.assertFalse(update.verify_signature(self.tgz(), s), s)

    def test_the_shipped_public_key_matches_the_real_signing_key_if_it_exists(self):
        import release
        if os.path.exists(release.DEFAULT_KEY):
            shipped = open(update.PUBKEY).read().strip()
            self.assertEqual(release.derive_public(release.DEFAULT_KEY).strip(), shipped)


class Extraction(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def extract(self, members):
        tar = os.path.join(self.d, "t.tgz")
        make_tar(tar, members)
        update.safe_extract(tar, os.path.join(self.d, "out"))

    FULL = [("app.py", b"x"), ("claude_linux", None), ("claude_linux/__init__.py", b""), ("claude_linux/version.py", b""), ("ui", None), ("ui/index.html", b"")]

    def test_a_complete_package_unpacks(self):
        self.extract(self.FULL)
        self.assertTrue(os.path.isfile(os.path.join(self.d, "out/ui/index.html")))

    def test_path_traversal_is_refused(self):
        for evil in ("../escape.txt", "/tmp/escape.txt", "a/../../escape.txt"):
            shutil.rmtree(os.path.join(self.d, "out"), True)
            with self.assertRaises(update.UpdateError, msg=evil):
                self.extract(self.FULL + [(evil, b"pwned")])
        self.assertFalse(os.path.exists(os.path.join(self.d, "escape.txt")))

    def test_links_are_refused(self):
        with self.assertRaises(update.UpdateError):
            self.extract(self.FULL + [("evil", ("link", "/etc/passwd"))])

    def test_incomplete_packages_are_refused(self):
        with self.assertRaises(update.UpdateError):
            self.extract([("app.py", b"x")])


class Install(World):
    def setUp(self):
        self.target = self.w.installed_copy("t-%d" % time.time_ns())
        self.addCleanup(shutil.rmtree, self.target, True)
        self.addCleanup(shutil.rmtree, self.target + ".old", True)
        self.manifest = update.fetch_manifest(self.w.url)

    def version_of(self, d):
        return open(os.path.join(d, "claude_linux/version.py")).read()

    def test_full_update_replaces_the_app_and_keeps_the_old_copy(self):
        seen = []
        update.download_and_install(self.manifest, self.target, lambda d, t: seen.append((d, t)))
        self.assertIn('"1.0.1"', self.version_of(self.target))
        self.assertIn('"1.0.0"', self.version_of(self.target + ".old"))
        self.assertTrue(seen and seen[-1][0] == seen[-1][1] == self.manifest["size"])
        self.assertFalse(os.path.exists(self.target + ".new"))
        update.cleanup_old(self.target)
        self.assertFalse(os.path.exists(self.target + ".old"))

    def test_damaged_download_leaves_the_app_untouched(self):
        with self.assertRaisesRegex(update.UpdateError, "damaged"):
            update.download_and_install(dict(self.manifest, sha256="0" * 64), self.target)
        self.assertIn('"1.0.0"', self.version_of(self.target))
        self.assertFalse(os.path.exists(self.target + ".old"))

    def test_unsigned_update_is_not_installed_even_with_a_correct_checksum(self):
        other = updsrv.World()
        self.addCleanup(other.close)
        evil = other.make("1.0.1")
        evil_tgz = os.path.join(other.dist, "claude-linux-1.0.1.tar.gz")
        mf = dict(self.manifest, url="http://127.0.0.1:%d/claude-linux-1.0.1.tar.gz" % other.server.server_address[1], sha256=evil["sha256"], signature=evil["signature"])
        self.assertTrue(os.path.exists(evil_tgz))
        with self.assertRaisesRegex(update.UpdateError, "not signed"):
            update.download_and_install(mf, self.target)
        self.assertIn('"1.0.0"', self.version_of(self.target))

    def test_dev_checkouts_never_update_themselves(self):
        with self.assertRaisesRegex(update.UpdateError, "installer"):
            update.download_and_install(self.manifest, None)

    def test_oversized_updates_are_refused(self):
        old = update.MAX_BYTES
        update.MAX_BYTES = 1000
        self.addCleanup(setattr, update, "MAX_BYTES", old)
        with self.assertRaisesRegex(update.UpdateError, "large"):
            update.download_and_install(self.manifest, self.target)
        self.assertIn('"1.0.0"', self.version_of(self.target))

    def test_download_failure_is_reported(self):
        with self.assertRaisesRegex(update.UpdateError, "download failed"):
            update.download_and_install(dict(self.manifest, url="http://127.0.0.1:1/x.tgz"), self.target)

    def test_swap_failure_restores_the_working_copy(self):
        staged = self.target + ".new"
        os.makedirs(staged)
        real = os.rename

        def flaky(a, b):
            if a == staged:
                raise OSError("disk full")
            return real(a, b)
        os.rename = flaky
        try:
            with self.assertRaises(OSError):
                update.swap_in(staged, self.target)
        finally:
            os.rename = real
        self.assertIn('"1.0.0"', self.version_of(self.target))


class CoreChecks(World):
    def core(self, url, env_extra=None):
        os.environ["CL_UPDATE_URL"] = url
        os.environ["CL_UPDATE_DELAY"] = "0"
        self.addCleanup(os.environ.pop, "CL_UPDATE_URL", None)
        self.addCleanup(os.environ.pop, "CL_UPDATE_DELAY", None)
        self.pushed = []
        return Core(lambda n, p: self.pushed.append((n, p)), None)

    def updates(self):
        return [p for n, p in self.pushed if n == "update"]

    def test_background_check_announces_a_newer_version(self):
        c = self.core(self.w.url)
        c.start_update_checks()
        self.assertTrue(pump_until(self.updates))
        u = self.updates()[0]
        self.assertEqual((u["state"], u["version"], u["current"], u["notes"], u["required"]), ("available", "1.0.1", "1.0.0", "Notes here", True))

    def test_background_check_is_silent_when_up_to_date_or_offline_or_unconfigured(self):
        old = os.path.join(self.w.dist, "latest.json")
        for url in ("http://127.0.0.1:1/latest.json", ""):
            c = self.core(url)
            c.check_update(manual=False)
            self.assertEqual(self.updates(), [], url)
        saved = open(old).read()
        try:
            doc = json.loads(saved)
            doc["version"] = "1.0.0"
            open(old, "w").write(json.dumps(doc))
            c = self.core(self.w.url)
            c.check_update(manual=False)
            self.assertEqual(self.updates(), [])
        finally:
            open(old, "w").write(saved)

    def test_manual_check_always_answers(self):
        c = self.core("")
        c.check_update(manual=True)
        self.assertEqual(self.updates()[-1]["state"], "disabled")
        c = self.core("http://127.0.0.1:1/latest.json")
        c.check_update(manual=True)
        self.assertEqual(self.updates()[-1]["state"], "error")
        c = self.core(self.w.url)
        c.check_update(manual=True)
        self.assertEqual(self.updates()[-1]["state"], "available")

    def test_download_pushes_progress_then_ready(self):
        target = self.w.installed_copy("core-%d" % time.time_ns())
        self.addCleanup(shutil.rmtree, target, True)
        self.addCleanup(shutil.rmtree, target + ".old", True)
        os.environ["CL_UPDATE_TARGET"] = target
        self.addCleanup(os.environ.pop, "CL_UPDATE_TARGET", None)
        c = self.core(self.w.url)
        c.check_update(manual=False)
        c.h_update_download({})
        self.assertTrue(pump_until(lambda: any(u["state"] in ("ready", "error") for u in self.updates())))
        states = [u["state"] for u in self.updates()]
        self.assertEqual(states[-1], "ready", self.updates()[-1])
        self.assertIn("downloading", states)
        self.assertIn('"1.0.1"', open(os.path.join(target, "claude_linux/version.py")).read())

    def test_download_without_an_announced_update_does_nothing(self):
        c = self.core(self.w.url)
        c.h_update_download({})
        time.sleep(0.3)
        self.assertEqual(self.updates(), [])


class GetScript(World):
    """The one-line installer (dist/get.sh), run for real against a local server with a throw-away HOME."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        open(os.path.join(cls.w.root, "claude_linux/update_url.txt"), "w").write(cls.w.url)
        import release
        release.write_get_script(cls.w.dist, root=cls.w.root)
        cls.get = os.path.join(cls.w.dist, "get.sh")

    def run_get(self, *args, piped=False, home=None):
        home = home or tempfile.mkdtemp(prefix="cl-get-home-")
        self.addCleanup(shutil.rmtree, home, True)
        e = dict(os.environ, HOME=home)
        cmd = ["bash", "-s", "--", *args] if piped else ["bash", self.get, *args]
        import subprocess
        r = subprocess.run(cmd, env=e, capture_output=True, text=True, timeout=120, stdin=open(self.get) if piped else subprocess.DEVNULL)
        return r, home

    def installed_version(self, home):
        return open(os.path.join(home, ".local/share/claude-linux-app/claude_linux/version.py")).read()

    def test_script_is_text_with_the_right_address_and_key(self):
        body = open(self.get).read()
        self.assertIn(self.w.url, body)
        self.assertIn(open(self.w.pub).read().strip(), body)
        self.assertNotIn("@@", body)
        self.assertNotIn("PRIVATE", body)

    def test_installs_the_latest_signed_release(self):
        r, home = self.run_get()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"1.0.1"', self.installed_version(home))
        self.assertTrue(os.access(os.path.join(home, ".local/bin/claude-linux"), os.X_OK))
        self.assertTrue(os.path.exists(os.path.join(home, ".local/share/applications/dev.nein.ClaudeLinux.desktop")))

    def test_works_when_piped_like_curl_pipe_bash(self):
        r, home = self.run_get(piped=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"1.0.1"', self.installed_version(home))

    def test_running_it_again_updates_in_place_and_keeps_user_data(self):
        r, home = self.run_get()
        data = os.path.join(home, ".local/share/claude-linux")
        os.makedirs(data)
        open(os.path.join(data, "settings.json"), "w").write("{}")
        r2, _ = self.run_get(home=home)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue(os.path.exists(os.path.join(data, "settings.json")))

    def test_uninstall_through_the_same_script(self):
        r, home = self.run_get()
        r2, _ = self.run_get("--uninstall", home=home)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertFalse(os.path.exists(os.path.join(home, ".local/share/claude-linux-app")))

    def refuse(self, mutate):
        saved = open(os.path.join(self.w.dist, "latest.json")).read()
        tgz = os.path.join(self.w.dist, "claude-linux-1.0.1.tar.gz")
        saved_tgz = open(tgz, "rb").read()
        try:
            mutate(saved, tgz)
            r, home = self.run_get()
        finally:
            open(os.path.join(self.w.dist, "latest.json"), "w").write(saved)
            open(tgz, "wb").write(saved_tgz)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(home, ".local/share/claude-linux-app")), "nothing may be installed")
        return r.stdout + r.stderr

    def test_refuses_a_damaged_download(self):
        out = self.refuse(lambda saved, tgz: open(tgz, "ab").write(b"x"))
        self.assertIn("checksum", out)

    def test_refuses_a_package_signed_by_someone_else(self):
        other = updsrv.World()
        self.addCleanup(other.close)
        m = other.make("1.0.1")
        evil = open(os.path.join(other.dist, "claude-linux-1.0.1.tar.gz"), "rb").read()

        def mutate(saved, tgz):
            open(tgz, "wb").write(evil)
            open(os.path.join(self.w.dist, "latest.json"), "w").write(json.dumps(dict(json.loads(saved), sha256=m["sha256"], signature=m["signature"])))
        self.assertIn("not signed", self.refuse(mutate))

    def test_refuses_garbage_release_information(self):
        out = self.refuse(lambda saved, tgz: open(os.path.join(self.w.dist, "latest.json"), "w").write(json.dumps(dict(json.loads(saved), sha256="zz"))))
        self.assertIn("looks wrong", out)

    def test_refuses_an_unreachable_address(self):
        import subprocess
        body = open(self.get).read().replace(self.w.url, "http://127.0.0.1:1/latest.json")
        p = os.path.join(self.w.tmp, "get-bad.sh")
        open(p, "w").write(body)
        home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, home, True)
        r = subprocess.run(["bash", p], env=dict(os.environ, HOME=home), capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Could not reach", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
