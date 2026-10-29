import env  # noqa: F401  (must be first)

import os
import shutil
import subprocess
import unittest

from uiharness import Page

from claude_linux.pdf import print_pdf

LONG = "\n\n".join("Paragraph %d about migrating the database to the new schema." % i for i in range(60))
CHAT = {"id": "p", "title": "PDF chat", "kind": "code", "session": None, "t": 1000, "cwd": "/home/test", "mode": "acceptEdits",
        "items": [{"k": "user", "text": "Please export <this> chat & keep unicode: éè ✓"},
                  {"k": "text", "text": "Here is code:\n\n```python\ndef hello():\n    return 'world'\n```\n\n" + LONG},
                  {"k": "tool", "id": "t", "name": "Bash", "input": {"command": "ls -la"}, "result": "file-one\nfile-two"}]}


class Pdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page().boot({"chats": {"p": CHAT}})

    def make(self):
        out = os.path.join(os.environ["CL_EXPORT_DIR"], "t.pdf")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out):
            os.unlink(out)
        self.page.run("exportChat('pdf')")
        done = []
        print_pdf(self.page.web, out, lambda ok, msg: done.append((ok, msg)))
        self.assertTrue(self.page.wait_for(lambda: done, 30000), "printing never finished")
        self.assertEqual(done[0][0], True, done[0][1])
        return out

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext not installed")
    def test_pdf_contains_the_conversation_and_nothing_of_the_app_chrome(self):
        out = self.make()
        info = subprocess.run(["pdfinfo", out], capture_output=True, text=True).stdout
        pages = int([l for l in info.splitlines() if l.startswith("Pages:")][0].split()[1])
        self.assertGreaterEqual(pages, 2, "a long chat must flow onto more than one page")
        text = subprocess.run(["pdftotext", "-layout", out, "-"], capture_output=True, text=True).stdout
        for want in ("PDF chat", "YOU", "Please export <this> chat & keep unicode", "def hello():", "Paragraph 59", "Bash", "file-two"):
            self.assertIn(want, text)
        for banned in ("New session", "Search chats", "Settings"):
            self.assertNotIn(banned, text, "app chrome leaked into the PDF")
        self.assertIn("(A4)", info)

    def test_print_document_is_removed_after_export(self):
        self.page.run("exportChat('pdf')")
        self.assertEqual(self.page.run("return document.querySelectorAll('#printdoc').length"), 1)
        self.page.send("pdf_done", {"ok": True, "text": "done"})
        self.assertEqual(self.page.run("return document.querySelectorAll('#printdoc, #printstyle').length"), 0)


if __name__ == "__main__":
    unittest.main()
