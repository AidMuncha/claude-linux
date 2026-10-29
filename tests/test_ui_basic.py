import unittest

from uiharness import Page

CHAT = {"id": "c1", "title": "Hello chat", "kind": "code", "session": None, "t": 1000, "cwd": "/home/test", "mode": "acceptEdits",
        "items": [{"k": "user", "text": "hi there", "uid": "u1"},
                  {"k": "text", "text": "Hello! Here is code:\n\n```python\nprint('x')\n```\n"},
                  {"k": "tool", "id": "t1", "name": "Edit", "input": {"file_path": "/a.py", "old_string": "a", "new_string": "b"}, "result": "ok"}]}


class Basic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page().boot({"chats": {"c1": CHAT}})

    def test_no_js_errors(self):
        self.assertEqual(self.page.errors, [])

    def test_chat_rendered(self):
        self.assertEqual(self.page.run("return document.querySelectorAll('#col .msg').length"), 3)
        self.assertEqual(self.page.run("return document.querySelector('#list .chat .t').textContent"), "Hello chat")

    def test_code_block_and_tool(self):
        self.assertEqual(self.page.run("return document.querySelectorAll('.cb').length"), 1)
        self.assertEqual(self.page.run("return document.querySelectorAll('.tool .dr.add').length"), 1)

    def test_every_theme_applies(self):
        names = self.page.run("return THEMES.map(t=>t[0])")
        self.assertIn("dark", names)
        for n in names:
            self.assertEqual(self.page.run("setTheme(%r); return document.documentElement.dataset.theme" % n), n)
        self.page.run("setTheme('dark')")


if __name__ == "__main__":
    unittest.main()
