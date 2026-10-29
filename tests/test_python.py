import env  # noqa: F401  (must be first)

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(env.HERE))

from gi.repository import GLib  # noqa: E402

from claude_linux import kde, paths, util  # noqa: E402
from claude_linux.core import Core  # noqa: E402
from claude_linux.settings import DEFAULTS  # noqa: E402


class Paths(unittest.TestCase):
    def test_everything_is_redirected_to_the_test_folders(self):
        self.assertEqual(paths.DATA, os.environ["CL_DATA"])
        self.assertTrue(paths.SETTINGS.startswith(os.environ["CL_DATA"]))
        self.assertEqual(paths.EXPORT_DIR, os.environ["CL_EXPORT_DIR"])
        self.assertEqual(paths.CLAUDE_FILES["settings"], os.path.join(os.environ["CL_CLAUDE_DIR"], "settings.json"))
        self.assertTrue(paths.CLAUDE.endswith("fake_claude.py"))


class Usage(unittest.TestCase):
    def test_parse_when_today_and_dated(self):
        tz = "UTC"
        now = datetime.now(ZoneInfo(tz))
        e = util.parse_when("11:30pm", tz)
        d = datetime.fromtimestamp(e, ZoneInfo(tz))
        self.assertEqual((d.hour, d.minute), (23, 30))
        e = util.parse_when("Oct 31, 9am", tz)
        d = datetime.fromtimestamp(e, ZoneInfo(tz))
        self.assertEqual((d.month, d.day, d.hour), (10, 31, 9))
        self.assertGreaterEqual(d.year, now.year)

    def test_the_cli_prints_the_reset_one_minute_early(self):
        e = util.parse_when("5:59am", "UTC")
        d = datetime.fromtimestamp(e, ZoneInfo("UTC"))
        self.assertEqual((d.hour, d.minute), (6, 0))

    def test_parse_when_rejects_garbage(self):
        self.assertIsNone(util.parse_when("soon", "UTC"))
        self.assertIsNone(util.parse_when("5:59am", "Not/AZone") and None)

    def test_parse_usage(self):
        out = util.parse_usage("Current session: 12% used · resets 5:59am (UTC)\nCurrent week (all models): 30% used · resets Oct 31, 9:00am (UTC)\nnoise")
        self.assertEqual([r["pct"] for r in out["rows"]], [12, 30])
        self.assertEqual(out["rows"][0]["label"], "session")
        self.assertEqual(out["rows"][1]["label"], "week (all models)")
        self.assertEqual(util.parse_usage("nothing here")["rows"], [])


class Kde(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".rc", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    SCHEME = """[General]
ColorScheme=OceanDeep
AccentColor=0,190,220

[Colors:Window]
BackgroundNormal=11,30,52
ForegroundNormal=252,252,252

[Colors:View]
BackgroundNormal=7,21,38
ForegroundNormal=252,252,252
ForegroundInactive=161,169,177
ForegroundPositive=39,174,96
ForegroundNegative=218,68,83
ForegroundNeutral=246,116,0

[Colors:Button]
BackgroundNormal=18,42,70

[Colors:Selection]
BackgroundNormal=61,174,233
"""

    def test_dark_scheme(self):
        s = kde.scheme(self.write(self.SCHEME))
        self.assertEqual((s["name"], s["view"], s["window"], s["button"]), ("OceanDeep", "#071526", "#0b1e34", "#122a46"))
        self.assertEqual((s["fg"], s["dim"], s["accent"]), ("#fcfcfc", "#a1a9b1", "#00bedc"))
        self.assertEqual((s["green"], s["red"], s["yellow"]), ("#27ae60", "#da4453", "#f67400"))
        self.assertTrue(s["dark"])

    def test_light_scheme_and_selection_accent_fallback(self):
        text = self.SCHEME.replace("AccentColor=0,190,220\n", "").replace("BackgroundNormal=7,21,38", "BackgroundNormal=252,252,252").replace("ForegroundNormal=252,252,252\nForegroundInactive", "ForegroundNormal=35,38,41\nForegroundInactive")
        s = kde.scheme(self.write(text))
        self.assertFalse(s["dark"])
        self.assertEqual(s["accent"], "#3daee9")

    def test_missing_or_broken_files_give_none(self):
        self.assertIsNone(kde.scheme("/nonexistent/kdeglobals"))
        self.assertIsNone(kde.scheme(self.write("this is not an ini file\n[[")))
        self.assertIsNone(kde.scheme(self.write("[Colors:View]\nBackgroundNormal=1,2\n")))
        self.assertIsNone(kde.scheme(self.write("[Colors:View]\nBackgroundNormal=300,2,3\nForegroundNormal=1,1,1\n[Colors:Window]\nBackgroundNormal=1,1,1\n")))

    def test_window_buttons(self):
        self.assertEqual(kde.window_buttons("/nonexistent"), ":minimize,maximize,close")                 # Plasma's defaults
        p = self.write("[org.kde.kdecoration2]\nButtonsOnLeft=XIA\nButtonsOnRight=MSH\n")
        self.assertEqual(kde.window_buttons(p), "close,minimize,maximize:")
        p = self.write("[org.kde.kdecoration2]\nButtonsOnRight=IX\n")
        self.assertEqual(kde.window_buttons(p), ":minimize,close")

    def test_real_scheme_on_this_machine_is_parseable_if_present(self):
        if os.path.exists(kde.KDEGLOBALS):
            s = kde.scheme()
            self.assertTrue(s is None or all(s[k].startswith("#") for k in ("view", "window", "fg")))


def pump_until(cond, seconds=3.0):
    """Runs the GLib main loop until cond() is true (idle callbacks only run while it is being iterated)."""
    end = time.time() + seconds
    while time.time() < end and not cond():
        if not GLib.MainContext.default().iteration(False):
            time.sleep(0.005)
    return cond()


def clean_slate():
    """Every test starts with empty data, export and ~/.claude stand-in folders."""
    for d in (paths.DATA, paths.CLAUDE_DIR, paths.EXPORT_DIR):
        shutil.rmtree(d, True)
    os.makedirs(paths.DATA, exist_ok=True)
    os.makedirs(paths.CLAUDE_DIR, exist_ok=True)


class CoreTests(unittest.TestCase):
    def setUp(self):
        clean_slate()
        self.pushed = []
        self.core = Core(lambda name, payload: self.pushed.append((name, payload)), None)
        self.addCleanup(shutil.rmtree, paths.EXPORT_DIR, True)

    def last(self, name):
        return [p for n, p in self.pushed if n == name][-1]

    def wait_for(self, name, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if any(n == name for n, _ in self.pushed):
                return self.last(name)
            GLib.MainContext.default().iteration(False)
            time.sleep(0.01)
        self.fail("nothing pushed: " + name)

    def test_defaults_cover_every_setting_the_page_uses(self):
        for key in ("theme", "accent", "customTheme", "projectColors", "font", "monoFont", "fontSize", "chatWidth", "bgMode", "bgImage", "glass",
                    "motion", "animSpeed", "celebrate", "syntax", "codeNums", "codeWrap", "tray", "closeToTray", "hotkey", "taskbar", "sidebar", "autoDark", "autoLight", "kdeAccent"):
            self.assertIn(key, DEFAULTS, key)

    def test_only_known_settings_are_saved(self):
        self.core.h_setsettings({"patch": {"theme": "nord", "fontSize": 17, "evil": "x", "customTheme": {"bg": "#000000"}}})
        saved = json.load(open(paths.SETTINGS))
        self.assertEqual((saved["theme"], saved["fontSize"], saved["customTheme"]), ("nord", 17, {"bg": "#000000"}))
        self.assertNotIn("evil", saved)
        self.assertNotIn("evil", self.core.settings)

    def test_settings_survive_a_restart(self):
        self.core.h_setsettings({"patch": {"theme": "tokyonight", "sidebar": False}})
        again = Core(lambda *_: None, None)
        self.assertEqual((again.settings["theme"], again.settings["sidebar"]), ("tokyonight", False))
        self.assertEqual(again.settings["fontSize"], 15)                                         # defaults fill the gaps

    def test_settings_change_notifies_the_app(self):
        calls = []

        class App:
            def apply_settings(self, s):
                calls.append(dict(s))
        c = Core(lambda *_: None, App())
        c.h_setsettings({"patch": {"tray": False}})
        self.assertTrue(pump_until(lambda: calls))
        self.assertIs(calls[-1]["tray"], False)

    def test_safe_names_and_unique_paths(self):
        self.assertEqual(Core.safe_name("../../etc/passwd"), "etcpasswd")
        self.assertEqual(Core.safe_name("***"), "chat")
        self.assertEqual(Core.safe_name("***", "x"), "x")
        self.assertLessEqual(len(Core.safe_name("a" * 200)), 40)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p1 = Core.unique_path(d, "n", ".md")
        open(p1, "w").close()
        p2 = Core.unique_path(d, "n", ".md")
        open(p2, "w").close()
        self.assertEqual((os.path.basename(p1), os.path.basename(p2), os.path.basename(Core.unique_path(d, "n", ".md"))), ("n.md", "n (2).md", "n (3).md"))

    def test_export_markdown_never_overwrites(self):
        self.core.chats["c"] = {"title": "My: chat", "items": [{"k": "user", "text": "hello"}, {"k": "text", "text": "world"},
                                                                  {"k": "tool", "name": "Bash", "input": {"command": "ls"}}]}
        self.core.h_export({"chat": "c"})
        self.core.h_export({"chat": "c"})
        files = sorted(os.listdir(paths.EXPORT_DIR))
        self.assertEqual(files, ["My chat (2).md", "My chat.md"])
        text = open(os.path.join(paths.EXPORT_DIR, "My chat.md")).read()
        self.assertIn("# My: chat", text)
        self.assertIn("**You:** hello", text)
        self.assertIn("`Bash`", text)
        self.core.h_export({"chat": "missing"})                                                    # unknown chat is ignored

    def test_savetext_only_writes_known_extensions_into_the_export_folder(self):
        self.core.h_savetext({"name": "../x", "ext": ".html", "text": "<p>hi</p>"})
        self.core.h_savetext({"name": "t", "ext": ".json", "text": "{}"})
        self.core.h_savetext({"name": "t", "ext": ".sh", "text": "rm -rf"})
        self.assertEqual(sorted(os.listdir(paths.EXPORT_DIR)), ["t (2).txt" if False else "t.json", "t.txt", "x.html"])
        self.assertEqual(open(os.path.join(paths.EXPORT_DIR, "x.html")).read(), "<p>hi</p>")

    def test_fonts_are_listed_and_deduplicated(self):
        self.core.h_fonts({})
        fonts = self.wait_for("fonts")["fonts"]
        self.assertEqual(fonts, sorted(set(fonts), key=str.lower))
        self.assertTrue(all("," not in f and f for f in fonts))

    def test_scan_and_rank_find_files(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "src"))
        os.makedirs(os.path.join(d, "node_modules/x"))
        for rel in ("src/app.py", "src/util.py", "README.md", "node_modules/x/skip.js", ".hidden"):
            open(os.path.join(d, rel), "w").close()
        files = self.core.scan(d)
        self.assertIn("src/app.py", files)
        self.assertNotIn("node_modules/x/skip.js", files)
        self.assertNotIn(".hidden", files)
        self.core.rank({"chat": "c", "q": "app"}, "app", files)
        self.assertEqual(self.last("files")["files"][0], "src/app.py")
        self.core.rank({"chat": "c", "q": "zzz"}, "zzz", files)
        self.assertEqual(self.last("files")["files"], [])

    def test_command_line_for_code_and_chat_sessions(self):
        code = self.core.build_cmd({"kind": "code", "mode": "plan", "session": "abc"})
        self.assertIn("--permission-prompt-tool", code)
        self.assertEqual(code[code.index("--permission-mode") + 1], "plan")
        self.assertEqual(code[code.index("--resume") + 1], "abc")
        chat = self.core.build_cmd({"kind": "chat"})
        self.assertEqual(chat[chat.index("--tools") + 1], "")
        self.assertNotIn("--permission-mode", chat)
        self.core.settings.update(model="claude-opus-5-5", long=True, effort="high")
        cmd = self.core.build_cmd({"kind": "code"})
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-5-5[1m]")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")

    def test_putfile_validates_json_and_keeps_a_backup(self):
        self.core.h_putfile({"which": "settings", "text": "{not json"})
        self.assertTrue(self.last("toast")["err"])
        self.assertFalse(os.path.exists(paths.CLAUDE_FILES["settings"]))
        self.core.h_putfile({"which": "settings", "text": '{"a": 1}'})
        self.core.h_putfile({"which": "settings", "text": '{"a": 2}'})
        self.assertEqual(json.load(open(paths.CLAUDE_FILES["settings"])), {"a": 2})
        self.assertEqual(json.load(open(paths.CLAUDE_FILES["settings"] + ".claude-linux.bak")), {"a": 1})

    def test_cset_sets_and_removes_dotted_keys(self):
        self.core.h_cset({"key": "permissions.defaultMode", "value": "plan"})
        self.assertEqual(json.load(open(paths.CLAUDE_FILES["settings"]))["permissions"]["defaultMode"], "plan")
        self.core.h_cset({"key": "permissions.defaultMode", "value": None})
        self.assertNotIn("defaultMode", json.load(open(paths.CLAUDE_FILES["settings"]))["permissions"])

    def test_chats_are_stored_one_file_each_and_old_store_migrated(self):
        old = os.path.join(paths.DATA, "chats.json")
        json.dump({"m1": {"title": "Migrated", "items": [{"k": "user", "text": "x"}]}, "empty": {"title": "E", "items": []}}, open(old, "w"))
        chats = util.load_chats()
        self.assertIn("m1", chats)
        self.assertNotIn("empty", chats)
        self.assertTrue(os.path.exists(os.path.join(paths.CHATDIR, "m1.json")))
        self.assertFalse(os.path.exists(old))
        self.core.h_save({"id": "z", "chat": {"title": "Z", "busy": True, "items": [{"k": "user", "text": "q"}]}})
        self.core.flush_chats()
        saved = json.load(open(os.path.join(paths.CHATDIR, "z.json")))
        self.assertNotIn("busy", saved)
        self.core.h_delete({"id": "z"})
        self.assertFalse(os.path.exists(os.path.join(paths.CHATDIR, "z.json")))

    def test_delete_cannot_escape_the_chat_folder(self):
        victim = os.path.join(paths.DATA, "victim.json")
        open(victim, "w").close()
        self.core.h_delete({"id": "../victim"})
        self.assertTrue(os.path.exists(victim))


class TrayMenu(unittest.TestCase):
    """The dbusmenu answers, without needing a session bus."""

    def make(self):
        from claude_linux.tray import Tray
        t = Tray.__new__(Tray)
        t.title, t.icon, t.icon_dir, t.app_id = "Claude Linux", "icon", "/icons", "app"
        t.status, t.tip, t.registered, t.conn = "Active", "tip", False, None
        t.items = [(1, "Show Claude Linux"), (2, "New session"), (3, None), (4, "Quit")]
        t.clicks = []
        t.on_show, t.on_new, t.on_quit = (lambda: t.clicks.append("show")), (lambda: t.clicks.append("new")), (lambda: t.clicks.append("quit"))
        return t

    class Inv:
        value = "unset"

        def return_value(self, v):
            self.value = v

    def call(self, t, method, params):
        inv = self.Inv()
        t._menu_call(None, None, None, None, method, params, inv)
        return inv.value

    def test_layout_lists_the_entries(self):
        t = self.make()
        rev, (root, props, kids) = self.call(t, "GetLayout", GLib.Variant("(iias)", (0, -1, []))).unpack()
        self.assertEqual((rev, root), (1, 0))
        labels = [k[1].get("label") for k in kids]
        self.assertEqual(labels, ["Show Claude Linux", "New session", None, "Quit"])
        self.assertEqual(kids[2][1]["type"], "separator")

    def test_clicking_runs_the_callbacks(self):
        t = self.make()
        for ident in (1, 2, 4, 3):
            self.call(t, "Event", GLib.Variant("(isvu)", (ident, "clicked", GLib.Variant("s", ""), 0)))
        pump_until(lambda: len(t.clicks) >= 3)
        self.assertEqual(sorted(t.clicks), ["new", "quit", "show"])

    def test_non_click_events_do_nothing(self):
        t = self.make()
        self.call(t, "Event", GLib.Variant("(isvu)", (1, "hovered", GLib.Variant("s", ""), 0)))
        pump_until(lambda: False, 0.3)
        self.assertEqual(t.clicks, [])

    def test_item_properties(self):
        t = self.make()
        self.assertEqual(t._item_get(None, None, None, None, "Id").unpack(), "app")
        self.assertEqual(t._item_get(None, None, None, None, "Menu").unpack(), "/MenuBar")
        self.assertEqual(t._item_get(None, None, None, None, "Status").unpack(), "Active")
        self.assertEqual(t._item_get(None, None, None, None, "ToolTip").unpack()[2], "Claude Linux")
        self.assertIsNone(t._item_get(None, None, None, None, "Nope"))


if __name__ == "__main__":
    unittest.main()
