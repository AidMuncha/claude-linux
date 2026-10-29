import env  # noqa: F401  (must be first)

import os
import sys
import shutil
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(env.HERE))

from gi.repository import GLib

from claude_linux import paths
from claude_linux.core import Core
from uiharness import Page


def pump_until(cond, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end and not cond():
        if not GLib.MainContext.default().iteration(False):
            time.sleep(0.01)
    return cond()


class CoreLogin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.auth, self.go = os.path.join(self.tmp, "auth"), os.path.join(self.tmp, "go")
        for k, v in (("FAKE_AUTH", self.auth), ("FAKE_AUTH_GO", self.go), ("CL_LOGIN_POLL", "0.5")):
            os.environ[k] = v
            self.addCleanup(os.environ.pop, k, None)
        self.pushed = []
        self.shown = []

        class App:
            def show_window(s2):
                self.shown.append(1)
        self.core = Core(lambda n, p: self.pushed.append((n, p)), App())

    def states(self):
        return [p["state"] for n, p in self.pushed if n == "login"]

    def test_full_sign_in_flow_ends_by_bringing_the_window_back(self):
        self.core.h_login({})
        self.assertTrue(pump_until(lambda: any(n == "login" and p.get("url") for n, p in self.pushed)))
        url = [p["url"] for n, p in self.pushed if n == "login" and p.get("url")][0]
        self.assertTrue(url.startswith("https://claude.ai/oauth/authorize"))
        self.assertIn("claudeai", url)
        open(self.go, "w").close()                                   # the user finishes in the browser
        self.assertTrue(pump_until(lambda: "done" in self.states()))
        self.assertTrue(pump_until(lambda: any(n == "account" and p.get("loggedIn") for n, p in self.pushed)), "the account must be refreshed")
        self.assertTrue(pump_until(lambda: self.shown), "the window must be raised")
        self.assertTrue(os.path.exists(self.auth))

    def test_paste_code_fallback(self):
        os.environ["FAKE_NEEDS_CODE"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_NEEDS_CODE", None)
        open(self.go, "w").close()
        self.core.h_login({})
        self.assertTrue(pump_until(lambda: any(p.get("needCode") for n, p in self.pushed if n == "login")), "the prompt has no newline and must still be noticed")
        self.core.h_login_code({"code": "short"})                                    # rejected before it reaches the CLI
        self.assertTrue([p for n, p in self.pushed if n == "toast" and p.get("err")])
        self.assertNotIn("done", self.states())
        self.core.h_login_code({"code": "good-code-123"})
        self.assertTrue(pump_until(lambda: "done" in self.states()))
        self.assertTrue(os.path.exists(self.auth))

    def test_wrong_code_fails_cleanly(self):
        os.environ["FAKE_NEEDS_CODE"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_NEEDS_CODE", None)
        self.core.h_login({})
        pump_until(lambda: any(p.get("needCode") for n, p in self.pushed if n == "login"))
        self.core.h_login_code({"code": "wrong-code-999"})
        self.assertTrue(pump_until(lambda: "error" in self.states()))
        self.assertNotIn("done", self.states())

    def test_codes_with_control_characters_are_refused(self):
        self.core.h_login({})
        pump_until(lambda: "waiting" in self.states())
        before = len(self.pushed)
        self.core.h_login_code({"code": "abcdefgh\nrm -rf /"})
        self.assertTrue([p for n, p in self.pushed[before:] if n == "toast" and p.get("err")])
        self.core.h_login_cancel({})

    def test_console_mode_is_passed_on(self):
        self.core.h_login({"mode": "console"})
        self.assertTrue(pump_until(lambda: any(p.get("url") for n, p in self.pushed if n == "login")))
        self.assertIn("console", [p["url"] for n, p in self.pushed if n == "login" and p.get("url")][0])
        self.core.h_login_cancel({})

    def test_cancel_stops_the_login_and_goes_back_to_idle(self):
        self.core.h_login({})
        pump_until(lambda: "waiting" in self.states())
        self.core.h_login_cancel({})
        self.assertEqual(self.states()[-1], "idle")
        time.sleep(1.5)
        pump_until(lambda: False, 0.3)
        self.assertNotIn("done", self.states())
        self.assertFalse(os.path.exists(self.auth))

    def test_a_failed_login_reports_an_error(self):
        os.environ["FAKE_LOGIN_FAIL"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_LOGIN_FAIL", None)
        self.core.h_login({})
        self.assertTrue(pump_until(lambda: "error" in self.states()))
        self.assertNotIn("done", self.states())
        self.assertEqual(self.shown, [])

    def test_a_timeout_reports_an_error_and_stops_the_process(self):
        os.environ["CL_LOGIN_TIMEOUT"] = "1.2"
        self.addCleanup(os.environ.pop, "CL_LOGIN_TIMEOUT", None)
        self.core.h_login({})
        self.assertTrue(pump_until(lambda: "error" in self.states(), 10))
        self.assertIn("timed out", [p for n, p in self.pushed if n == "login"][-1]["message"])

    def test_starting_twice_does_not_start_two_logins(self):
        self.core.h_login({})
        self.core.h_login({})
        pump_until(lambda: False, 0.5)
        self.assertEqual(self.states().count("waiting"), 1 + len([1 for n, p in self.pushed if n == "login" and p.get("url")]))
        self.core.h_login_cancel({})

    def test_missing_cli_is_flagged_on_the_account(self):
        old = paths.CLAUDE
        import claude_linux.core as c
        c.CLAUDE = "/nonexistent/claude"
        self.addCleanup(setattr, c, "CLAUDE", old)
        self.core.h_account({})
        self.assertTrue(pump_until(lambda: any(n == "account" for n, p in self.pushed)))
        acct = [p for n, p in self.pushed if n == "account"][-1]
        self.assertEqual((acct["loggedIn"], acct["missing"]), (None, True))

    def test_install_runs_the_installer_and_reports_progress(self):
        target = os.path.join(self.tmp, "bin-claude")
        os.environ["CL_INSTALL_CMD"] = "echo Downloading; echo Installing; cp '%s' '%s'; echo Done" % (os.path.join(env.HERE, "fake_claude.py"), target)
        self.addCleanup(os.environ.pop, "CL_INSTALL_CMD", None)
        import claude_linux.core as c
        old = c.CLAUDE
        c.CLAUDE = target
        self.addCleanup(setattr, c, "CLAUDE", old)
        self.core.h_install_cli({})
        self.assertTrue(pump_until(lambda: any(n == "toast" for n, p in self.pushed) or "error" in self.states()))
        lines = [p["line"] for n, p in self.pushed if n == "login" and p["state"] == "installing"]
        self.assertTrue({"Downloading", "Installing"} <= set(lines), lines)
        self.assertEqual(self.states()[-1], "idle")

    def test_failed_install_is_reported_with_a_retry(self):
        os.environ["CL_INSTALL_CMD"] = "echo Network is down; exit 3"
        self.addCleanup(os.environ.pop, "CL_INSTALL_CMD", None)
        self.core.h_install_cli({})
        self.assertTrue(pump_until(lambda: "error" in self.states()))
        last = [p for n, p in self.pushed if n == "login"][-1]
        self.assertIn("Network is down", last["message"])
        self.assertEqual(last["retry"], "install")


class LoginPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page().boot()

    def setUp(self):
        self.page.run("LG.s='idle'; LG.url=''; S.account={loggedIn:true}; renderLogin()")
        self.page.posts.clear()
        self.page.errors.clear()

    def tearDown(self):
        self.assertEqual(self.page.errors, [])

    def on(self):
        return self.page.run("return document.getElementById('loginpage').classList.contains('on')")

    def text(self):
        return self.page.run("return document.getElementById('loginbox').innerText")

    def acct(self, **kw):
        self.page.send("account", kw)

    def click(self, a):
        self.page.run("document.querySelector('#loginbox [data-lg=%s]').click()" % a)

    def test_hidden_when_signed_in_or_unknown(self):
        self.assertFalse(self.on())
        self.acct(loggedIn=None, error="network down")                 # an unknown state must not lock people out
        self.assertFalse(self.on())

    def test_signed_out_shows_the_welcome_page_and_blocks_the_app(self):
        self.acct(loggedIn=False)
        self.assertTrue(self.on())
        t = self.text()
        self.assertIn("Welcome to Claude Linux", t)
        self.assertIn("Sign in with Claude", t)
        self.assertIn("land right back here", t)
        self.assertEqual(self.page.run("return document.elementFromPoint(300, 300).closest('#loginpage') !== null"), True)

    def test_sign_in_button_starts_the_login_and_shows_waiting(self):
        self.acct(loggedIn=False)
        self.click("login")
        self.assertEqual(self.page.sent("login")[-1]["mode"], "claudeai")
        self.assertIn("Finish signing in", self.text())
        self.page.send("login", {"state": "waiting", "url": "https://claude.ai/oauth/authorize?x=1"})
        self.assertIn("Open the page again", self.text())
        self.click("open")
        self.assertEqual(self.page.sent("open_url")[-1]["url"], "https://claude.ai/oauth/authorize?x=1")
        self.click("cancel")
        self.assertEqual(len(self.page.sent("login_cancel")), 1)

    def test_code_box_appears_only_when_needed_and_sends_the_code(self):
        self.acct(loggedIn=False)
        self.click("login")
        self.page.send("login", {"state": "waiting", "url": "https://claude.ai/x"})
        self.assertEqual(self.page.run("return !!document.getElementById('lgcode')"), False)
        self.page.send("login", {"state": "waiting", "url": "https://claude.ai/x", "needCode": True})
        self.assertIn("paste it here", self.text())
        self.page.run("document.getElementById('lgcode').value = '  good-code-123 '")
        self.page.send("login", {"state": "waiting", "url": "https://claude.ai/x", "needCode": True})     # a re-render must keep what was typed
        self.assertEqual(self.page.run("return document.getElementById('lgcode').value"), "  good-code-123 ")
        self.click("code")
        self.assertEqual(self.page.sent("login_code")[-1]["code"], "good-code-123")
        self.page.run("document.getElementById('lgcode').value = ''; document.querySelector('#loginbox [data-lg=code]').click()")
        self.assertEqual(len(self.page.sent("login_code")), 1, "an empty box sends nothing")
        self.page.run("document.getElementById('lgcode').value = 'abcdefgh'; document.getElementById('lgcode').dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}))")
        self.assertEqual(len(self.page.sent("login_code")), 2)

    def test_console_option(self):
        self.acct(loggedIn=False)
        self.click("console")
        self.assertEqual(self.page.sent("login")[-1]["mode"], "console")

    def test_success_thanks_then_fades_back_to_the_app(self):
        self.acct(loggedIn=False)
        self.click("login")
        self.page.send("login", {"state": "done"})
        self.assertIn("You're signed in", self.text())
        self.assertTrue(self.on())
        self.page.spin(2200)
        self.assertFalse(self.on())
        self.assertEqual(self.page.run("return S.account.loggedIn"), True)

    def test_error_offers_try_again(self):
        self.acct(loggedIn=False)
        self.page.send("login", {"state": "error", "message": "Sign-in timed out."})
        self.assertIn("Sign-in timed out.", self.text())
        self.click("login")
        self.assertEqual(len(self.page.sent("login")), 1)

    def test_missing_cli_offers_the_one_click_install(self):
        self.acct(loggedIn=None, error="nope", missing=True)
        self.assertTrue(self.on())
        t = self.text()
        self.assertIn("Install Claude Code", t)
        self.assertIn("claude.ai/install.sh", t)
        self.click("install")
        self.assertEqual(len(self.page.sent("install_cli")), 1)
        self.page.send("login", {"state": "installing", "line": "Downloading claude 2.1"})
        self.assertIn("Installing Claude Code", self.text())
        self.assertIn("Downloading claude 2.1", self.text())
        self.page.send("login", {"state": "error", "message": "The install did not finish: boom", "retry": "install"})
        self.assertIn("boom", self.text())
        self.click("install")
        self.assertEqual(len(self.page.sent("install_cli")), 2)

    def test_signing_out_later_shows_the_page_again(self):
        self.acct(loggedIn=True, plan="max")
        self.assertFalse(self.on())
        self.acct(loggedIn=False)
        self.assertTrue(self.on())

    def test_text_from_python_cannot_inject_html(self):
        self.acct(loggedIn=False)
        self.page.send("login", {"state": "error", "message": "<img src=x onerror=alert(1)>"})
        self.assertEqual(self.page.run("return document.querySelectorAll('#loginbox img').length"), 0)

    def test_works_with_reduced_motion(self):
        self.page.run("S.settings.motion='reduced'; applyAppearance()")
        self.acct(loggedIn=False)
        self.page.send("login", {"state": "done"})
        self.page.spin(500)
        self.assertFalse(self.on())
        self.page.run("S.settings.motion='full'; applyAppearance()")


if __name__ == "__main__":
    unittest.main()
