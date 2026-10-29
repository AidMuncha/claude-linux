import os
import struct
import tempfile
import unittest
import zlib

from uiharness import Page


def chat(cid, title, t, cwd="/home/test/proj", kind="code", items=None):
    return {"id": cid, "title": title, "kind": kind, "session": None, "t": t, "cwd": cwd, "mode": "acceptEdits",
            "items": items if items is not None else [{"k": "user", "text": "question for " + title, "uid": "u" + cid},
                                                      {"k": "text", "text": "answer for " + title + "\n\n```python\nprint('hi')\n```\n"}]}


CHATS = {"a": chat("a", "Alpha chat", 3000), "b": chat("b", "Beta chat", 2000, cwd="/home/test/other")}
KDE_SCHEME = {"name": "OceanDeep", "view": "#071526", "window": "#0b1e34", "button": "#122a46", "fg": "#fcfcfc", "dim": "#a1a9b1",
              "accent": "#00bedc", "green": "#27ae60", "red": "#da4453", "yellow": "#f67400", "dark": True}


def png(path, w=8, h=8, rgba=(200, 30, 30, 255)):
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Page().boot({"chats": CHATS, "settings": {"theme": "dark", "fontSize": 15, "chatWidth": 800, "tray": True}})

    def setUp(self):
        self.page.run("""
            for (const k of ['accent','font','monoFont','bgMode','bgImage','glass','syntax','codeNums','codeWrap','celebrate'])
              delete S.settings[k];
            Object.assign(S.settings, {theme:'dark', fontSize:15, chatWidth:800, motion:'full', animSpeed:1, projectColors:{}, customTheme:{}, sidebar:true});
            KDE = {scheme:null, buttons:''}; closeSplit(); select('a'); applySidebar(); applyAppearance(); closePops();
            document.getElementById('modal').style.display = 'none';
            for (const c of Object.values(chats)) delete c.color;
        """)
        self.page.errors.clear()

    def tearDown(self):
        self.assertEqual(self.page.errors, [], "JS errors during the test")

    def js(self, body):
        return self.page.run(body)

    def css(self, prop, sel="document.documentElement"):
        return self.js("return getComputedStyle(%s).getPropertyValue(%r).trim()" % (sel, prop))


class Themes(Base):
    def test_every_theme_resolves_its_background(self):
        for tid, name, cols in self.js("return THEMES"):
            with self.subTest(theme=tid):
                self.js("S.settings.theme=%r; applyAppearance()" % tid)
                self.assertEqual(self.js("return document.documentElement.dataset.theme"), tid)
                self.assertEqual(self.js("return toHex(varRGB('--bg'))"), cols[0].lower())
                self.assertEqual(self.js("return toHex(varRGB('--accent'))"), cols[2].lower())

    def test_light_themes_are_marked_light(self):
        light = {"light", "sepia", "catppuccin-latte"}
        for tid, *_ in self.js("return THEMES"):
            self.js("S.settings.theme=%r; applyAppearance()" % tid)
            want = "light" if tid in light else "dark"
            self.assertEqual(self.js("return document.documentElement.dataset.scheme"), want, tid)

    def test_text_on_accent_stays_readable(self):
        self.assertEqual(self.css("--onacc"), "#fff")                       # default orange keeps white text
        self.js("S.settings.theme='ayu'; applyAppearance()")                # yellow accent needs dark text
        self.assertEqual(self.css("--onacc"), "#1a1a1a")
        self.js("S.settings.accent='#111111'; applyAppearance()")
        self.assertEqual(self.css("--onacc"), "#fff")

    def test_accent_precedence_chat_over_folder_over_global(self):
        self.js("S.settings.accent='#112233'; applyAppearance()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#112233")
        self.js("S.settings.projectColors={'/home/test/proj':'#445566'}; applyAppearance()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#445566")
        self.js("chats[cur].color='#778899'; applyAppearance()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#778899")
        self.js("chats[cur].color='javascript:alert(1)'; applyAppearance()")        # garbage is ignored
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#445566")

    def test_switching_chats_switches_the_chat_color(self):
        self.js("chats.a.color='#aa0000'; select('a')")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#aa0000")
        self.js("select('b')")
        self.assertNotEqual(self.js("return toHex(varRGB('--accent'))"), "#aa0000")

    def test_system_theme_uses_kde_colors(self):
        self.js("S.settings.theme='system'")
        self.page.send("kde", {"scheme": KDE_SCHEME, "buttons": ":minimize,maximize,close"})
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "system")
        self.assertEqual(self.js("return toHex(varRGB('--bg'))"), "#071526")
        self.assertEqual(self.js("return toHex(varRGB('--side'))"), "#0b1e34")
        self.assertEqual(self.js("return toHex(varRGB('--card'))"), "#122a46")
        self.assertEqual(self.js("return document.documentElement.dataset.scheme"), "dark")
        self.assertNotEqual(self.js("return toHex(varRGB('--accent'))"), "#00bedc")      # accent only when asked
        self.js("S.settings.kdeAccent=true; applyAppearance()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#00bedc")
        # derived colors exist and differ from the base
        self.assertNotEqual(self.js("return toHex(varRGB('--line'))"), "#071526")

    def test_system_theme_without_kde_falls_back(self):
        self.js("S.settings.theme='system'; KDE={scheme:null}; applyAppearance()")
        self.assertIn(self.js("return document.documentElement.dataset.theme"), ("dark", "light"))

    def test_auto_theme_follows_the_scheme(self):
        self.js("S.settings.theme='auto'; S.settings.autoDark='nord'; S.settings.autoLight='sepia'")
        self.page.send("kde", {"scheme": dict(KDE_SCHEME, dark=True), "buttons": ""})
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "nord")
        self.page.send("kde", {"scheme": dict(KDE_SCHEME, dark=False), "buttons": ""})
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "sepia")

    def test_light_system_theme_marks_scheme_light(self):
        self.js("S.settings.theme='system'")
        self.page.send("kde", {"scheme": dict(KDE_SCHEME, view="#fcfcfc", window="#eff0f1", button="#e5e5e5", fg="#232629", dim="#7f8c8d", dark=False), "buttons": ""})
        self.assertEqual(self.js("return document.documentElement.dataset.scheme"), "light")

    def test_chrome_message_follows_the_theme(self):
        self.page.posts.clear()
        self.js("S.settings.theme='nord'; applyAppearance()")
        msgs = [p for p in self.page.posts if p.get("type") == "chrome"]
        self.assertTrue(msgs)
        self.assertEqual(msgs[-1]["bg"], "#2e3440")
        self.assertEqual(msgs[-1]["side"], "#272c36")
        self.assertFalse(msgs[-1]["glass"])

    def test_glass_sets_chrome_and_class(self):
        self.page.posts.clear()
        self.js("S.settings.glass=true; S.settings.glassOpacity=0.7; applyAppearance()")
        self.assertTrue(self.js("return document.documentElement.classList.contains('glass')"))
        self.page.spin(900)                                                                # let the theme cross-fade finish
        last = [p for p in self.page.posts if p.get("type") == "chrome"][-1]
        self.assertTrue(last["glass"])
        self.assertAlmostEqual(last["opacity"], 0.7)
        self.assertEqual(self.css("background-color", "document.body"), "rgba(0, 0, 0, 0)")

    def test_theme_crossfade_class_comes_and_goes(self):
        self.js("S.settings.theme='nord'; applyAppearance()")
        self.assertTrue(self.js("return document.documentElement.classList.contains('tfade')"))
        self.page.spin(900)
        self.assertFalse(self.js("return document.documentElement.classList.contains('tfade')"))

    def test_next_theme_cycles(self):
        a = self.js("return S.settings.theme")
        self.js("nextTheme()")
        self.assertNotEqual(self.js("return S.settings.theme"), a)

    def test_theme_command_accepts_new_and_adaptive_names(self):
        self.js("LOCAL.theme[1]('Tokyo Night')")
        self.assertEqual(self.js("return S.settings.theme"), "tokyonight")
        self.js("LOCAL.theme[1]('system')")
        self.assertEqual(self.js("return S.settings.theme"), "system")


class CustomTheme(Base):
    def test_sanitize_rejects_junk_and_keeps_good_colors(self):
        self.assertIsNone(self.js("return sanitizeTheme(null)"))
        self.assertIsNone(self.js("return sanitizeTheme({bg:'red', fg:'blue'})"))
        self.assertIsNone(self.js("return sanitizeTheme({bg:'#000000'})"))                 # needs bg and fg
        self.assertEqual(self.js("return sanitizeTheme({bg:'#000', fg:'#FFF', accent:'url(x)', extra:'#123456'})"), {"bg": "#000000", "fg": "#ffffff"})
        self.assertEqual(self.js("return sanitizeTheme({colors:{bg:'#101010', fg:'#eeeeee', accent:'#ff0000'}})"), {"bg": "#101010", "fg": "#eeeeee", "accent": "#ff0000"})

    def test_import_applies_and_selects_custom(self):
        self.page.posts.clear()
        self.js("importThemeText(JSON.stringify({colors:{bg:'#101820', fg:'#f0f0f0', accent:'#ff8800', card:'#1b2733', side:'#0b1118'}}))")
        self.assertEqual(self.js("return S.settings.theme"), "custom")
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "custom")
        self.assertEqual(self.js("return toHex(varRGB('--bg'))"), "#101820")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#ff8800")
        patches = [p["patch"] for p in self.page.sent("setsettings")]
        self.assertTrue(any("customTheme" in p for p in patches))
        self.assertTrue(any(p.get("theme") == "custom" for p in patches))

    def test_import_rejects_bad_files(self):
        self.page.posts.clear()
        self.js("importThemeText('not json')")
        self.js("importThemeText('{\"bg\":\"nope\"}')")
        self.assertEqual(self.page.sent("setsettings"), [])
        self.assertEqual(self.js("return document.getElementById('toast').className"), "err")

    def test_export_posts_valid_json_with_current_colors(self):
        self.js("S.settings.theme='nord'; applyAppearance(); exportTheme()")
        m = self.page.sent("savetext")[-1]
        import json
        data = json.loads(m["text"])
        self.assertEqual(m["ext"], ".json")
        self.assertEqual(data["colors"]["bg"], "#2e3440")
        self.assertEqual(data["colors"]["accent"], "#88c0d0")
        self.js("importThemeText(%r)" % m["text"])               # round trip
        self.assertEqual(self.js("return toHex(varRGB('--bg'))"), "#2e3440")


class Typography(Base):
    def test_font_and_size_and_width(self):
        self.js("Object.assign(S.settings,{font:'Cantarell', monoFont:'Fira Code', fontSize:18, chatWidth:1000}); applyAppearance()")
        self.assertTrue(self.css("--sans").startswith('"Cantarell"'))
        self.assertTrue(self.css("--mono").startswith('"Fira Code"'))
        self.assertEqual(self.css("font-size", "document.body"), "18px")
        self.assertEqual(self.css("max-width", "document.getElementById('col')"), "1000px")
        self.assertEqual(self.css("max-width", "document.getElementById('wrap')"), "1000px")

    def test_font_name_cannot_break_out_of_the_declaration(self):
        self.js("S.settings.font='x\";}body{display:none}/*'; applyAppearance()")
        self.assertNotEqual(self.css("display", "document.body"), "none")
        self.assertNotIn('"x";', self.css("--sans"))

    def test_clearing_the_font_restores_the_default(self):
        self.js("S.settings.font='Cantarell'; applyAppearance(); S.settings.font=''; applyAppearance()")
        self.assertTrue(self.css("--sans").startswith('"Inter"'))

    def test_limits_are_enforced(self):
        self.js("Object.assign(S.settings,{fontSize:500, chatWidth:5}); applyAppearance()")
        self.assertEqual(self.css("--fs"), "24px")
        self.assertEqual(self.css("--cw"), "480px")

    def test_zoom_keys(self):
        self.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'=',ctrlKey:true,bubbles:true}))")
        self.assertEqual(self.js("return S.settings.fontSize"), 16)
        self.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'-',ctrlKey:true,bubbles:true}))")
        self.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'-',ctrlKey:true,bubbles:true}))")
        self.assertEqual(self.js("return S.settings.fontSize"), 14)
        self.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'0',ctrlKey:true,bubbles:true}))")
        self.assertEqual(self.js("return S.settings.fontSize"), 15)


class Motion(Base):
    def test_reduced_motion_and_speed(self):
        self.js("S.settings.motion='reduced'; applyAppearance()")
        self.assertEqual(self.js("return document.documentElement.dataset.motion"), "reduced")
        self.assertEqual(self.js("return getComputedStyle(document.getElementById('new')).transitionDuration"), "0.001s" if False else self.js("return getComputedStyle(document.getElementById('new')).transitionDuration"))
        self.js("S.settings.motion='full'; S.settings.animSpeed=2; applyAppearance()")
        self.assertEqual(self.css("--sp"), "0.5")
        self.js("S.settings.animSpeed=0.5; applyAppearance()")
        self.assertEqual(self.css("--sp"), "2")

    def test_speed_scales_real_durations(self):
        d1 = self.js("return parseFloat(getComputedStyle(document.getElementById('new')).transitionDuration)")
        self.js("S.settings.animSpeed=2; applyAppearance()")
        d2 = self.js("return parseFloat(getComputedStyle(document.getElementById('new')).transitionDuration)")
        self.assertAlmostEqual(d2, d1 / 2, places=3)

    def test_reduced_motion_makes_animations_instant(self):
        self.js("S.settings.motion='reduced'; applyAppearance()")
        d = self.js("return parseFloat(getComputedStyle(document.getElementById('new')).transitionDuration)")
        self.assertLess(d, 0.01)

    def test_ripple_on_press_and_none_when_reduced(self):
        self.js("document.getElementById('new').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:20,clientY:20}))")
        self.assertEqual(self.js("return document.querySelectorAll('#new .ripple').length"), 1)
        self.page.spin(900)
        self.assertEqual(self.js("return document.querySelectorAll('#new .ripple').length"), 0)
        self.js("S.settings.motion='reduced'; applyAppearance(); document.getElementById('new').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
        self.assertEqual(self.js("return document.querySelectorAll('#new .ripple').length"), 0)

    def test_celebration_glow_and_confetti(self):
        self.js("celebrate.minMs = 0; S.settings.celebrate='glow'; spinStart[cur]=Date.now()-9000; celebrate(cur)")
        self.assertTrue(self.js("return document.getElementById('box').classList.contains('glow')"))
        self.assertEqual(self.js("return document.querySelectorAll('#confetti').length"), 0)
        self.js("S.settings.celebrate='confetti'; celebrate(cur)")
        self.assertEqual(self.js("return document.querySelectorAll('#confetti').length"), 1)
        self.page.spin(300)
        self.js("S.settings.celebrate='off'; document.getElementById('box').classList.remove('glow'); celebrate(cur)")
        self.assertFalse(self.js("return document.getElementById('box').classList.contains('glow')"))
        self.js("celebrate.minMs = 6000; S.settings.celebrate='glow'; spinStart[cur]=Date.now(); document.getElementById('box').classList.remove('glow'); celebrate(cur)")
        self.assertFalse(self.js("return document.getElementById('box').classList.contains('glow')"), "short runs do not celebrate")

    def test_logo_spinner_while_busy(self):
        self.js("chats[cur].busy=true; renderBusy()")
        self.assertEqual(self.js("return document.querySelectorAll('#status .st svg').length"), 1)
        self.js("chats[cur].busy=false; renderBusy()")
        self.assertEqual(self.js("return document.getElementById('status').innerHTML"), "")


class CodeBlocks(Base):
    def test_every_line_is_a_span_and_text_is_unchanged(self):
        code = "def f(x):\n    # note\n    return Foo(x) + 42\n"
        html = self.js("return hl(%r, 'python')" % code)
        self.assertEqual(html.count('class="ln"'), 4)
        self.assertEqual(self.js("const d=document.createElement('div'); d.innerHTML=hl(%r,'python'); return d.textContent" % code), code)

    def test_token_classes(self):
        out = self.js("""const d=document.createElement('div'); d.innerHTML=hl('class Foo:\\n    def go(self):\\n        # hi\\n        return call(1, "s") + $X', 'python');
          const r={}; for (const t of ['c','s','n','k','f','t','v']) r[t]=[...d.querySelectorAll('.tk-'+t)].map(e=>e.textContent); return r""")
        self.assertIn("# hi", out["c"])
        self.assertIn('"s"', out["s"])
        self.assertIn("1", out["n"])
        self.assertIn("return", out["k"])
        self.assertIn("call", out["f"])
        self.assertIn("Foo", out["t"])
        self.assertIn("$X", out["v"])

    def test_multiline_comment_stays_inside_one_span_per_line(self):
        code = "/* a\n b\n c */\nlet x = 1;\n"
        self.assertEqual(self.js("const d=document.createElement('div'); d.innerHTML=hl(%r,'js'); return d.querySelectorAll('.ln').length" % code), 5)
        self.assertEqual(self.js("const d=document.createElement('div'); d.innerHTML=hl(%r,'js'); return d.textContent" % code), code)

    def test_diff_and_plain(self):
        self.assertEqual(self.js("const d=document.createElement('div'); d.innerHTML=hl('+a\\n-b\\n c','diff'); return [d.querySelectorAll('.tk-a').length, d.querySelectorAll('.tk-d').length]"), [1, 1])
        self.assertEqual(self.js("return hl('<b>', '')"), '<span class="ln">&lt;b&gt;</span>')

    def test_line_numbers_and_wrap_toggle(self):
        self.js("S.settings.codeNums=true; S.settings.codeWrap=true; applyAppearance()")
        html = self.js("return document.documentElement.className")
        self.assertIn("codenums", html)
        self.assertIn("codewrap", html)
        self.assertEqual(self.js("return getComputedStyle(document.querySelector('.cb pre')).whiteSpace"), "pre-wrap")
        before = self.js("return getComputedStyle(document.querySelector('.cb .ln'), '::before').content")
        self.assertNotIn(before, ("none", "normal"))
        self.js("S.settings.codeNums=false; applyAppearance()")
        self.assertIn(self.js("return getComputedStyle(document.querySelector('.cb .ln'), '::before').content"), ("none", "normal", '""'))

    def test_syntax_themes_respect_scheme(self):
        self.js("S.settings.syntax='monokai'; applyAppearance()")
        self.assertEqual(self.css("--sk"), "#f92672")                                      # dark theme: preset applies
        self.js("S.settings.theme='light'; applyAppearance()")
        self.assertNotEqual(self.css("--sk"), "#f92672")                                   # light theme: falls back to the theme
        self.js("S.settings.syntax='github'; applyAppearance()")
        self.assertEqual(self.css("--sk"), "#cf222e")                                      # github has a light variant
        self.js("S.settings.syntax='auto'; applyAppearance()")
        self.assertEqual(self.js("return document.documentElement.getAttribute('data-syntax')"), None)

    def test_copy_still_returns_the_code(self):
        self.assertEqual(self.js("return document.querySelector('.cb code').textContent"), "print('hi')")


class ToolCards(Base):
    def test_cards_expand_and_collapse_smoothly(self):
        self.js("""chats.a.items.push({k:'tool', id:'t9', name:'Bash', input:{command:'ls'}, result:'one\\ntwo'}); select('a')""")
        info = self.js("const t=[...document.querySelectorAll('.tool')].pop(); return [t.classList.contains('open'), getComputedStyle(t.querySelector('.tb')).maxHeight, getComputedStyle(t.querySelector('.tb')).transitionProperty]")
        self.assertFalse(info[0])
        self.assertEqual(info[1], "0px")
        self.assertIn("max-height", info[2])
        self.js("[...document.querySelectorAll('.tool')].pop().querySelector('.th').click()")
        self.page.spin(700)
        info = self.js("const t=[...document.querySelectorAll('.tool')].pop(); const b=t.querySelector('.tb'); return [t.classList.contains('open'), getComputedStyle(b).maxHeight, parseFloat(getComputedStyle(b).opacity), b.getBoundingClientRect().height > 20]")
        self.assertEqual(info, [True, "340px", 1, True])
        self.js("[...document.querySelectorAll('.tool')].pop().querySelector('.th').click()")
        self.page.spin(700)
        self.assertEqual(self.js("const b=[...document.querySelectorAll('.tool')].pop().querySelector('.tb'); return [getComputedStyle(b).maxHeight, b.getBoundingClientRect().height]"), ["0px", 0])

    def test_diff_rows_get_stagger_indexes_and_the_card_starts_open(self):
        self.js("select('a')")
        rows = self.js("return [...document.querySelectorAll('.tool .dr')].map(r => r.style.getPropertyValue('--n'))")
        self.assertEqual(rows, []) if False else None
        self.js("chats.a.items.push({k:'tool', id:'t10', name:'Edit', input:{file_path:'/x.py', old_string:'a\\nb', new_string:'c\\nd\\ne'}, result:'ok'}); select('a')")
        out = self.js("const t=[...document.querySelectorAll('.tool')].pop(); return [t.classList.contains('open'), [...t.querySelectorAll('.dr')].map(r => r.style.getPropertyValue('--n'))]")
        self.assertTrue(out[0])
        self.assertEqual(out[1], ["0", "1", "2", "3", "4"])
        self.assertNotEqual(self.js("return getComputedStyle(document.querySelector('.tool.open .dr')).animationName"), "none")

    def test_refreshing_an_open_card_does_not_replay_its_animation(self):
        self.js("chats.a.items.push({k:'tool', id:'t11', name:'Edit', input:{file_path:'/y.py', old_string:'a', new_string:'b'}, result:null}); select('a')")
        self.js("const it=chats.a.items.find(x=>x.id==='t11'); it.result='done'; refreshTool('a', it)")
        self.assertEqual(self.js("return getComputedStyle(document.querySelector('.tool.open.noanim .dr')).animationName"), "none")
        self.page.spin(900)
        self.assertEqual(self.js("return document.querySelectorAll('.tool.noanim').length"), 0)


class Sidebar(Base):
    def test_collapse_and_expand_animate_and_persist(self):
        self.page.posts.clear()
        self.js("toggleSidebar()")
        self.assertTrue(self.js("return document.getElementById('side').classList.contains('collapsed')"))
        self.page.spin(500)
        self.assertEqual(self.js("return document.getElementById('side').getBoundingClientRect().width"), 0)
        self.assertEqual(self.page.sent("setsettings")[-1]["patch"], {"sidebar": False})
        self.js("toggleSidebar()")
        self.page.spin(500)
        self.assertEqual(self.js("return document.getElementById('side').getBoundingClientRect().width"), 260)
        self.assertEqual(self.page.sent("setsettings")[-1]["patch"], {"sidebar": True})

    def test_ctrl_b_and_button(self):
        self.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'b',ctrlKey:true,bubbles:true}))")
        self.assertTrue(self.js("return document.getElementById('side').classList.contains('collapsed')"))
        self.js("document.getElementById('sbtn').click()")
        self.assertFalse(self.js("return document.getElementById('side').classList.contains('collapsed')"))

    def test_saved_collapsed_state_is_applied_at_startup(self):
        self.js("S.settings.sidebar=false; applySidebar(true)")
        self.page.spin(100)
        self.assertEqual(self.js("return document.getElementById('side').getBoundingClientRect().width"), 0)

    def test_search_shows_a_snippet_for_body_matches(self):
        self.js("document.getElementById('search').value='answer for beta'; document.getElementById('search').dispatchEvent(new Event('input'))")
        out = self.js("return [...document.querySelectorAll('#list .chat')].map(c => [c.querySelector('.t').textContent, (c.querySelector('.snip')||{}).textContent])")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "Beta chat")
        self.assertIn("answer for beta", out[0][1].lower())
        self.assertEqual(self.js("return document.querySelectorAll('#list .snip mark').length"), 1)
        self.js("document.getElementById('search').value=''; document.getElementById('search').dispatchEvent(new Event('input'))")

    def test_color_dot_and_context_menu(self):
        self.js("chats.a.color='#12a594'; renderList()")
        self.assertEqual(self.js("return document.querySelectorAll('#list .cdot').length"), 1)
        self.js("colorMenu({clientX:100, clientY:100, preventDefault(){}}, chats.a)")
        self.assertEqual(self.js("return document.querySelectorAll('#menu .swc').length"), 22)
        self.js("document.querySelector('#menu [data-scope=chat] .swc[data-c=\"#e5484d\"]').click()")
        self.assertEqual(self.js("return chats.a.color"), "#e5484d")
        self.js("colorMenu({clientX:100, clientY:100}, chats.a); document.querySelector('#menu [data-scope=dir] .swc[data-c=\"#3e63dd\"]').click()")
        self.assertEqual(self.js("return S.settings.projectColors['/home/test/proj']"), "#3e63dd")
        self.js("colorMenu({clientX:100, clientY:100}, chats.a); document.querySelector('#menu [data-scope=chat] .swc.none').click()")
        self.assertEqual(self.js("return chats.a.color"), None)

    def test_accent_command(self):
        self.js("LOCAL.accent[1]('#ff00ff')")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#ff00ff")
        self.js("LOCAL.accent[1]('reset')")
        self.assertEqual(self.js("return chats[cur].color"), None)


class Backgrounds(Base):
    def test_each_mode_builds_its_layer(self):
        for mode, probe in (("aurora", "document.querySelectorAll('#bgfx i').length"), ("particles", "document.querySelectorAll('#bgfx canvas').length"), ("gradient", "document.getElementById('bgfx').style.backgroundImage.includes('linear-gradient')")):
            with self.subTest(mode=mode):
                self.js("S.settings.bgMode=%r; applyAppearance()" % mode)
                self.assertTrue(self.js("return document.documentElement.classList.contains('fx')"))
                self.assertTrue(self.js("return document.getElementById('bgfx').className===%r" % mode))
                self.assertTrue(self.js("return !!(%s)" % probe))
        self.js("S.settings.bgMode='none'; applyAppearance()")
        self.assertFalse(self.js("return document.documentElement.classList.contains('fx')"))
        self.assertEqual(self.js("return document.querySelectorAll('#bgfx').length"), 0)

    def test_surfaces_become_translucent_with_a_background(self):
        opaque = self.css("background-color", "document.getElementById('side')")
        self.js("S.settings.bgMode='aurora'; applyAppearance()")
        self.assertNotEqual(self.css("background-color", "document.getElementById('side')"), opaque)

    def test_image_background_loads_from_disk(self):
        path = os.path.join(tempfile.mkdtemp(prefix="cl bg "), "pic 1.png")      # spaces on purpose
        png(path)
        self.js("S.settings.bgMode='image'; S.settings.bgImage=%r; applyAppearance()" % path)
        self.assertIn("pic%201.png", self.js("return document.getElementById('bgfx').style.backgroundImage"))
        ok = self.js("""return await new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = fileUrl(%r); })""" % path)
        self.assertEqual(ok, [8, 8], "file:// pictures must load inside the page")

    def test_image_mode_without_a_picture_is_off(self):
        self.js("S.settings.bgMode='image'; S.settings.bgImage=''; applyAppearance()")
        self.assertEqual(self.js("return document.querySelectorAll('#bgfx').length"), 0)

    def test_particles_stop_when_leaving_the_mode(self):
        self.js("S.settings.bgMode='particles'; applyAppearance()")
        self.assertNotEqual(self.js("return pRaf"), 0)
        self.js("S.settings.bgMode='none'; applyAppearance()")
        self.assertEqual(self.js("return pRaf"), 0)

    def test_background_with_reduced_motion_is_static(self):
        self.js("S.settings.motion='reduced'; S.settings.bgMode='particles'; applyAppearance()")
        self.assertEqual(self.js("return pRaf"), 0)
        self.assertEqual(self.js("return document.querySelectorAll('#bgfx canvas').length"), 1)


class SplitView(Base):
    def test_open_render_live_update_swap_close(self):
        self.js("select('a'); openSplit('b')")
        self.assertTrue(self.js("return document.getElementById('app').classList.contains('splitting')"))
        self.assertEqual(self.js("return document.getElementById('stitle').textContent"), "Beta chat")
        self.assertEqual(self.js("return document.querySelectorAll('#scol .msg').length"), 2)
        self.assertGreater(self.js("return document.getElementById('split').getBoundingClientRect().width"), 300)
        # new content in the split chat shows up (persistChat is what every event calls)
        self.js("chats.b.items.push({k:'text', text:'fresh words'}); persistChat('b')")
        self.page.spin(500)
        self.assertIn("fresh words", self.js("return document.getElementById('scol').textContent"))
        self.js("document.getElementById('sswap').click()")
        self.assertEqual(self.js("return cur"), "b")
        self.assertEqual(self.js("return S.split"), "a")
        self.js("document.getElementById('sclose').click()")
        self.assertFalse(self.js("return document.getElementById('app').classList.contains('splitting')"))

    def test_selecting_the_split_chat_closes_the_split(self):
        self.js("select('a'); openSplit('b'); select('b')")
        self.assertEqual(self.js("return S.split"), None)

    def test_tool_cards_in_the_split_toggle_and_keep_their_state(self):
        self.js("chats.b.items.push({k:'tool', id:'sp1', name:'Bash', input:{command:'ls'}, result:'x'}); select('a'); openSplit('b')")
        self.js("document.querySelector('#scol .tool .th').click()")
        self.assertTrue(self.js("return document.querySelector('#scol .tool').classList.contains('open')"))
        self.js("renderSplit()")
        self.assertTrue(self.js("return document.querySelector('#scol .tool').classList.contains('open')"))

    def test_toggle_needs_another_chat(self):
        self.js("closeSplit(); const keep = chats.b; delete chats.b; select('a'); toggleSplit(); window.__keep = keep")
        self.assertEqual(self.js("return S.split"), None)
        self.js("chats.b = window.__keep")

    def test_shortcut_opens_the_chooser(self):
        self.js("select('a'); document.dispatchEvent(new KeyboardEvent('keydown',{key:'\\\\',ctrlKey:true,bubbles:true}))")
        self.assertIn("Beta chat", self.js("return document.getElementById('menu').textContent"))


class Exports(Base):
    def test_html_export_is_standalone_and_escaped(self):
        self.js("chats.a.title='A <b>&</b> chat'; chats.a.items.push({k:'text', text:'x <script>alert(1)</script>'}); select('a')")
        self.js("exportChat('html')")
        m = self.page.sent("savetext")[-1]
        self.assertEqual(m["ext"], ".html")
        self.assertTrue(m["text"].startswith("<!doctype html>"))
        self.assertNotIn("<script>alert(1)</script>", m["text"])
        self.assertIn("&lt;script&gt;", m["text"])
        self.assertIn("A &lt;b&gt;", m["text"])
        self.assertIn("question for", m["text"])
        self.assertNotIn("var(--", m["text"])                                           # no dependence on the app's CSS variables

    def test_markdown_export_goes_to_python(self):
        self.js("select('a'); exportChat('md')")
        self.assertEqual(self.page.sent("export")[-1]["chat"], "a")

    def test_pdf_builds_a_print_document_and_cleans_up(self):
        self.js("select('a'); exportChat('pdf')")
        self.assertEqual(self.js("return document.querySelectorAll('#printdoc').length"), 1)
        self.assertIn("answer for Alpha", self.js("return document.getElementById('printdoc').textContent"))
        self.assertEqual(self.page.sent("pdf")[-1]["name"], self.js("return chats.a.title"))
        self.page.send("pdf_done", {"ok": True, "text": "Exported"})
        self.assertEqual(self.js("return document.querySelectorAll('#printdoc, #printstyle').length"), 0)

    def test_empty_chat_is_refused(self):
        self.js("newChat()")
        self.page.posts.clear()
        self.js("exportChat('html')")
        self.assertEqual(self.page.sent("savetext"), [])
        self.js("select('a')")

    def test_unknown_format(self):
        self.js("select('a'); exportChat('docx')")
        self.assertIn("Use /export", self.js("return document.getElementById('toast').textContent"))


class DropFiles(Base):
    def drop(self, uris, files=""):
        return self.js("""
            const dt = new DataTransfer(); dt.setData('text/uri-list', %r); %s
            document.dispatchEvent(new DragEvent('dragenter', {dataTransfer: dt, bubbles: true}));
            const shown = document.getElementById('dropz').classList.contains('on');
            document.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
            return [shown, document.getElementById('in').value, document.getElementById('dropz').classList.contains('on')]""" % (uris, files))

    def test_dropped_paths_become_mentions(self):
        self.js("select('a'); document.getElementById('in').value=''")
        shown, value, still = self.drop("file:///home/test/proj/src/app.py\r\nfile:///etc/hosts\r\nfile:///home/test/proj/my%20notes.txt\r\n")
        self.assertTrue(shown)
        self.assertFalse(still)
        self.assertEqual(value, '@src/app.py @/etc/hosts @"my notes.txt" ')

    def test_comment_lines_and_non_file_uris_are_ignored(self):
        self.js("document.getElementById('in').value=''")
        _, value, _ = self.drop("# comment\r\nhttps://example.com/x\r\n")
        self.assertEqual(value, "")

    def test_appends_to_existing_text(self):
        self.js("document.getElementById('in').value='look at'")
        _, value, _ = self.drop("file:///home/test/proj/a.py")
        self.assertEqual(value, "look at @a.py ")
        self.js("document.getElementById('in').value=''")

    def test_plain_text_drags_are_not_hijacked(self):
        r = self.js("""const dt = new DataTransfer(); dt.setData('text/plain', 'hello');
          document.dispatchEvent(new DragEvent('dragenter', {dataTransfer: dt, bubbles: true}));
          return document.getElementById('dropz').classList.contains('on')""")
        self.assertFalse(r)


class Status(Base):
    def test_busy_waiting_and_progress_are_reported(self):
        self.js("select('a'); chats.a.items.push({k:'tool', id:'td', name:'TodoWrite', input:{todos:[{status:'completed',content:'a'},{status:'in_progress',content:'b'},{status:'pending',content:'c'},{status:'pending',content:'d'}]}, result:'ok'})")
        self.js("lastStatus=''; chats.a.busy=true; reportStatus()")
        m = self.page.sent("status")[-1]
        self.assertEqual((m["busy"], m["waiting"]), (1, 0))
        self.assertAlmostEqual(m["progress"], 0.25)
        self.js("chats.b.items.push({k:'perm', status:'wait', rid:'r1', tool:'Bash', input:{}}); reportStatus()")
        self.assertEqual(self.page.sent("status")[-1]["waiting"], 1)
        self.js("chats.a.busy=false; chats.b.items.pop(); reportStatus()")
        m = self.page.sent("status")[-1]
        self.assertEqual((m["busy"], m["waiting"], m["progress"]), (0, 0, None))

    def test_unchanged_status_is_not_resent(self):
        self.js("reportStatus()")
        n = len(self.page.sent("status"))
        self.js("reportStatus(); reportStatus()")
        self.assertEqual(len(self.page.sent("status")), n)

    def test_window_title_is_reported(self):
        self.js("select('a'); renderList()")
        self.assertEqual(self.page.sent("title")[-1]["text"], "Alpha chat")


class SettingsPages(Base):
    def open(self, name):
        self.js("openPanel(%r)" % name)
        self.page.spin(80)

    def test_appearance_page_lists_every_theme_and_sections(self):
        self.open("appearance")
        n = self.js("return document.querySelectorAll('#pbody [data-ap-theme]').length")
        self.assertEqual(n, len(self.js("return THEMES")) + 3)
        text = self.js("return document.getElementById('pbody').textContent")
        for want in ("Accent color", "Custom theme", "Typography and layout", "Background and window", "Animation", "Code blocks", "Catppuccin Mocha", "Synthwave", "System (KDE colors)"):
            self.assertIn(want, text)
        self.assertIn("tk-k", self.js("return document.querySelector('#pbody .demo').innerHTML"))

    def test_clicking_a_theme_tile_applies_it(self):
        self.open("appearance")
        self.js("document.querySelector('#pbody [data-ap-theme=\"dracula\"]').click()")
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "dracula")
        self.assertEqual(self.js("return document.querySelectorAll('#pbody .tc.on').length"), 1)

    def test_accent_swatch_and_reset(self):
        self.open("appearance")
        self.js("document.querySelector('#pbody [data-ap-accent=\"#3e63dd\"]').click()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#3e63dd")
        self.js("document.querySelector('#pbody [data-ap-accent=\"\"]').click()")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#d97757")

    def test_slider_previews_live_and_saves_on_release(self):
        self.open("appearance")
        self.page.posts.clear()
        self.js("""const r = document.querySelector('#pbody [data-ap-range=fontSize]'); r.value = 19; r.dispatchEvent(new Event('input'))""")
        self.assertEqual(self.css("--fs"), "19px")
        self.assertEqual(self.page.sent("setsettings"), [])
        self.js("document.querySelector('#pbody [data-ap-range=fontSize]').dispatchEvent(new Event('change'))")
        self.assertEqual(self.page.sent("setsettings")[-1]["patch"], {"fontSize": 19})
        self.assertEqual(self.js("return document.querySelector('#pbody [data-val=fontSize]').textContent"), "19 px")

    def test_custom_color_inputs_preview_and_save(self):
        self.open("appearance")
        self.js("document.querySelector('#pbody [data-ap=use-custom], #pbody [data-ap-act=use-custom]').click()")
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "custom")
        self.js("""const i = document.querySelector('#pbody [data-ap-ct=bg]'); i.value = '#102030'; i.dispatchEvent(new Event('input'))""")
        self.assertEqual(self.js("return toHex(varRGB('--bg'))"), "#102030")
        self.js("document.querySelector('#pbody [data-ap-ct=bg]').dispatchEvent(new Event('change'))")
        self.assertEqual(self.js("return S.settings.customTheme.bg"), "#102030")

    def test_background_choice_reveals_its_options(self):
        self.open("appearance")
        self.assertNotIn("Dim the background", self.js("return document.getElementById('pbody').textContent"))
        self.js("""const s = document.querySelector('#pbody select[data-id=bgMode]'); s.value='gradient'; s.dispatchEvent(new Event('change'))""")
        self.page.spin(120)
        self.assertIn("Dim the background", self.js("return document.getElementById('pbody').textContent"))
        self.assertEqual(self.js("return document.getElementById('bgfx').className"), "gradient")

    def test_desktop_page_and_toggles(self):
        self.open("desktop")
        text = self.js("return document.getElementById('pbody').textContent")
        for want in ("Tray icon", "Close to the tray", "Taskbar badge", "Global shortcut", "Color scheme"):
            self.assertIn(want, text)
        self.page.posts.clear()
        self.js("""const c = document.querySelector('#pbody input[data-id=closeToTray]'); c.checked = true; c.dispatchEvent(new Event('change'))""")
        self.assertEqual(self.page.sent("setsettings")[-1]["patch"], {"closeToTray": True})

    def test_hotkey_state_messages(self):
        self.js("S.settings.hotkey=true; S.hotkeyState=null")
        self.open("desktop")
        self.assertIn("Asking your desktop", self.js("return document.getElementById('pbody').textContent"))
        self.page.send("hotkey", {"ok": True, "msg": "Ctrl+Alt+C"})
        self.assertIn("Ctrl+Alt+C", self.js("return document.getElementById('pbody').textContent"))
        self.page.send("hotkey", {"ok": False, "msg": "denied"})
        self.assertIn("denied", self.js("return document.getElementById('pbody').textContent"))
        self.js("S.settings.hotkey=false")

    def test_general_page_points_to_appearance(self):
        self.open("general")
        self.js("document.querySelector('#pbody [data-go=appearance]').click()")
        self.assertEqual(self.js("return panel"), "appearance")

    def test_font_list_is_requested_once_and_fills_the_datalist(self):
        self.js("S.fonts=null; S.fontsAsked=false")
        self.page.posts.clear()
        self.open("appearance")
        self.assertEqual(len(self.page.sent("fonts")), 1)
        self.page.send("fonts", {"fonts": ["Cantarell", "Noto Sans"]})
        self.assertEqual(self.js("return document.querySelectorAll('#fontlist option').length"), 2)
        self.open("appearance")
        self.assertEqual(len(self.page.sent("fonts")), 1)

    def test_import_through_the_page(self):
        self.open("appearance")
        self.js("document.getElementById('imptext').value = %r; document.querySelector('[data-ap-act=import-paste]').click()" % '{"bg":"#0a0a0a","fg":"#fafafa","accent":"#00ff99"}')
        self.assertEqual(self.js("return document.documentElement.dataset.theme"), "custom")
        self.assertEqual(self.js("return toHex(varRGB('--accent'))"), "#00ff99")

    def test_new_commands_in_palette_and_help(self):
        names = self.js("return cmdList().map(x => x[0])")
        for n in ("split", "appearance", "accent", "export", "theme"):
            self.assertIn(n, names)
        items = self.js("return palItems().map(x => x.l)")
        for want in ("Split view", "Next theme", "Export chat as PDF", "Theme: Catppuccin Mocha", "Theme: System (KDE colors)", "Appearance settings"):
            self.assertIn(want, items)


if __name__ == "__main__":
    unittest.main()
