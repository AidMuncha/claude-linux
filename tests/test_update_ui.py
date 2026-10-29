import env  # noqa: F401  (must be first)

import unittest

from uiharness import Page


class UpdateDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page().boot({"appVersion": "1.0.0"})

    def setUp(self):
        self.page.run("UPD.p = null; renderUpdate()")
        self.page.posts.clear()
        self.page.errors.clear()

    def tearDown(self):
        self.assertEqual(self.page.errors, [])

    def text(self):
        return self.page.run("return document.getElementById('updbox').innerText")

    def shown(self):
        return self.page.run("return document.getElementById('updmodal').classList.contains('on')")

    def click(self, action):
        self.page.run("document.querySelector('#updbox [data-upd=%s]').click()" % action)

    def available(self, **kw):
        self.page.send("update", dict({"state": "available", "version": "1.2.0", "current": "1.0.0", "notes": "New themes\nFaster", "required": True, "size": 5242880, "canInstall": True}, **kw))

    def test_hidden_until_an_update_arrives(self):
        self.assertFalse(self.shown())

    def test_required_update_shows_the_headline_download_button_and_no_way_out(self):
        self.available()
        self.assertTrue(self.shown())
        t = self.text()
        self.assertIn("New Update Required", t)
        self.assertIn("Claude Linux 1.2.0 is ready (you have 1.0.0)", t)
        self.assertIn("New themes", t)
        self.assertIn("Download now", t)
        self.assertNotIn("Later", t)
        self.page.run("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        self.assertTrue(self.shown())

    def test_optional_update_can_be_postponed(self):
        self.available(required=False)
        self.assertIn("New update available", self.text())
        self.click("later")
        self.assertFalse(self.shown())

    def test_download_now_asks_python_and_progress_fills_the_bar(self):
        self.available()
        self.click("download")
        self.assertEqual(len(self.page.sent("update_download")), 1)
        self.page.send("update", {"state": "downloading", "done": 0, "total": 5242880})
        self.assertIn("Downloading update", self.text())
        self.assertEqual(self.page.run("return document.querySelector('#updbox .ubar i').style.width"), "0%")
        self.page.send("update", {"state": "downloading", "done": 2621440, "total": 5242880})
        self.assertEqual(self.page.run("return document.querySelector('#updbox .ubar i').style.width"), "50%")
        t = self.text()
        self.assertIn("50%", t)
        self.assertIn("2.5 MB of 5.0 MB", t)
        self.assertIn("Claude Linux 1.2.0", t)                             # remembers which version it is fetching
        self.assertTrue(self.page.run("return document.querySelector('#updbox .btn').disabled"))
        self.page.spin(300)
        self.assertEqual(self.page.run("return Math.round(document.querySelector('#updbox .ubar i').getBoundingClientRect().width / document.querySelector('#updbox .ubar').getBoundingClientRect().width * 100)"), 50)

    def test_ready_offers_restart(self):
        self.available()
        self.page.send("update", {"state": "ready", "version": "1.2.0"})
        t = self.text()
        self.assertIn("Update installed", t)
        self.assertIn("100%", t)
        self.click("restart")
        self.assertEqual(len(self.page.sent("update_restart")), 1)

    def test_errors_offer_retry_and_for_required_updates_a_quit(self):
        self.available()
        self.page.send("update", {"state": "error", "message": "The download failed: boom", "retry": "download"})
        t = self.text()
        self.assertIn("The download failed: boom", t)
        self.assertIn("Try again", t)
        self.assertIn("Quit", t)
        self.click("download")
        self.assertEqual(len(self.page.sent("update_download")), 1)
        self.click("quit")
        self.assertEqual(len(self.page.sent("quit")), 1)

    def test_optional_errors_can_be_dismissed(self):
        self.available(required=False)
        self.page.send("update", {"state": "error", "message": "nope", "retry": "download"})
        self.assertIn("Later", self.text())

    def test_message_text_cannot_inject_html(self):
        self.available(notes="<img src=x onerror=alert(1)>", version="1.2.0<b>")
        self.assertEqual(self.page.run("return document.querySelectorAll('#updbox img, #updbox b').length"), 0)

    def test_copies_that_cannot_self_update_say_so(self):
        self.available(canInstall=False)
        t = self.text()
        self.assertIn("cannot update itself", t)
        self.assertNotIn("Download now", t)

    def test_up_to_date_and_disabled_are_only_toasts(self):
        self.page.send("update", {"state": "current", "version": "1.0.0"})
        self.assertFalse(self.shown())
        self.assertIn("latest version (1.0.0)", self.page.run("return document.getElementById('toast').textContent"))
        self.page.send("update", {"state": "disabled"})
        self.assertIn("not set up", self.page.run("return document.getElementById('toast').textContent"))

    def test_about_page_shows_the_version_and_checks(self):
        self.page.run("openPanel('about')")
        self.page.spin(80)
        self.assertIn("1.0.0", self.page.run("return document.getElementById('pbody').innerText"))
        self.page.run("document.querySelector('#pbody [data-upd=check]').click()")
        self.assertEqual(len(self.page.sent("update_check")), 1)
        self.page.run("closePanel()")

    def test_dialog_sits_above_everything_and_blocks_clicks_beneath(self):
        self.available()
        self.assertEqual(self.page.run("const r = document.getElementById('updbox').getBoundingClientRect(); return document.elementFromPoint(r.left + 20, r.top + 20).closest('#updmodal') !== null"), True)
        self.assertEqual(self.page.run("return document.elementFromPoint(5, 5).id"), "updmodal")

    def test_works_in_light_and_reduced_motion(self):
        self.page.run("S.settings.theme='light'; S.settings.motion='reduced'; applyAppearance()")
        self.available()
        self.assertIn("Download now", self.text())
        self.page.run("S.settings.theme='dark'; S.settings.motion='full'; applyAppearance()")


if __name__ == "__main__":
    unittest.main()
