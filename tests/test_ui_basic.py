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

    def test_code_sessions_grouped_under_their_project_folder(self):
        self.assertEqual(self.page.run("return document.querySelector('#list .grp.proj .pn').textContent"), "test")
        self.assertEqual(self.page.run("return document.querySelectorAll('#list .grp.proj ~ .chat.inproj').length"), 1)

    def test_streamed_first_word_is_not_split_into_two_lines(self):
        out = self.page.run("""const el = document.createElement('div'); document.body.appendChild(el);
          st[cur] = {item:{k:'text', text:'Hello there'}, raw:'Hello there', shown:0, el}; for (let i = 0; i < 3; i++) typeTick();
          const r = [el.textContent, el.querySelectorAll('p').length]; delete st[cur]; el.remove(); return r;""")
        self.assertEqual(out[1], 1)

    def test_grid_is_behind_the_app_and_follows_the_theme(self):
        self.assertEqual(self.page.run("return !!document.querySelector('canvas#gridfx') && document.documentElement.classList.contains('grid')"), True)
        self.assertEqual(self.page.run("return getComputedStyle(document.querySelector('#main')).backgroundColor"), "rgba(0, 0, 0, 0)")
        px = "const c = document.querySelector('#gridfx'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4) if (d[i]) return true; return false"
        for theme in ("dark", "light", "dracula"):
            self.page.run("applyTheme(%r)" % theme)
            self.assertTrue(self.page.run(px), theme)

    def test_grid_glows_near_the_mouse_and_can_be_turned_off(self):
        self.page.run("GRID.mx = GRID.x = 300; GRID.my = GRID.y = 300; GRID.glow = 1; gridDraw()")
        near = self.page.run("const c = document.querySelector('#gridfx'), g = c.getContext('2d'); let m = 0; const d = g.getImageData(250, 250, 100, 100).data; for (let i = 3; i < d.length; i += 4) m = Math.max(m, d[i]); return m")
        far = self.page.run("const c = document.querySelector('#gridfx'), g = c.getContext('2d'); let m = 0; const d = g.getImageData(c.width - 120, c.height - 120, 100, 100).data; for (let i = 3; i < d.length; i += 4) m = Math.max(m, d[i]); return m")
        self.assertGreater(near, far)
        self.page.run("GRID.mx = GRID.my = -1e4; GRID.glow = 0; setSetting('grid', false)")
        self.assertEqual(self.page.run("return document.querySelector('#gridfx')"), None)
        self.page.run("setSetting('grid', true)")

    def test_a_new_session_must_pick_a_folder_or_universal(self):
        r = self.page.run("""tab = 'code'; newChat(); const c = chats[cur]; const first = c.cwd;
          $('#in').value = 'hi'; send(); const blocked = [c.items.length, c.busy || false, !!document.querySelector('.hero .pick')];
          setCwd(UNIVERSAL); const uni = [dirName(c), document.querySelector('#dirbtn').textContent.trim(), cwdOf(c) === home, projectOf(c)];
          delete chats[c.id]; select('c1'); return [first, blocked, uni];""")
        self.assertEqual(r[0], "")
        self.assertEqual(r[1], [0, False, True])
        self.assertEqual(r[2], ["Universal", "Universal", True, "Universal"])

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
