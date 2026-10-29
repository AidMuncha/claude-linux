"""End-to-end: the real GTK app, with a fake `claude`, a fake tray host and a private D-Bus session."""
import env  # noqa: F401  (must be first)

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from gi.repository import Gio, GLib

ROOT = os.path.dirname(env.HERE)
sys.path.insert(0, ROOT)
from claude_linux.version import VERSION  # noqa: E402
APP = os.path.join(ROOT, "app.py")
CTX = GLib.MainContext.default()

HELPERS = """
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (f, ms = 20000) => { const t = Date.now(); while (!f() && Date.now() - t < ms) await sleep(50); return !!f(); };
const log = o => post({type:'log', text: JSON.stringify(o)});
await until(() => S.version && S.usage && S.usage.rows && S.usage.rows.length && S.account && S.cmds.length && cur);
"""


def pump(seconds=0.0, until=None):
    end = time.time() + seconds
    while time.time() < end:
        if until and until():
            return True
        if not CTX.iteration(False):
            time.sleep(0.01)
    return bool(until and until())


WATCHER_XML = """<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
<property name="RegisteredStatusNotifierItems" type="as" access="read"/>
<property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
<property name="ProtocolVersion" type="i" access="read"/></interface></node>"""


class FakeTrayHost:
    """Plays the part of KDE's StatusNotifierWatcher so we can see the app register its icon. One per process; reset() between tests."""
    _shared = None

    @classmethod
    def get(cls):
        if cls._shared is None:
            cls._shared = cls()
        cls._shared.reset()
        return cls._shared

    def __init__(self):
        self.items, self.statuses, self.launcher = [], [], []
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.info = Gio.DBusNodeInfo.new_for_xml(WATCHER_XML).interfaces[0]
        self.conn.register_object("/StatusNotifierWatcher", self.info, self.call, self.on_get, None)
        self.owner = Gio.bus_own_name_on_connection(self.conn, "org.kde.StatusNotifierWatcher", Gio.BusNameOwnerFlags.NONE, None, None)
        self.conn.signal_subscribe(None, "org.kde.StatusNotifierItem", "NewStatus", "/StatusNotifierItem", None, Gio.DBusSignalFlags.NONE,
                                   lambda _c, sender, _p, _i, _n, params: self.statuses.append((sender, params.unpack()[0])))
        self.conn.signal_subscribe(None, "com.canonical.Unity.LauncherEntry", "Update", None, None, Gio.DBusSignalFlags.NONE,
                                   lambda _c, _s, _p, _i, _n, params: self.launcher.append({k: v for k, v in params.unpack()[1].items()}))

    def reset(self):
        self.items.clear()
        self.statuses.clear()
        self.launcher.clear()

    def call(self, _c, _s, _p, _i, method, params, inv):
        self.items.append(params.unpack()[0])
        inv.return_value(None)

    def on_get(self, _c, _s, _p, _i, prop):
        return {"RegisteredStatusNotifierItems": GLib.Variant("as", self.items), "IsStatusNotifierHostRegistered": GLib.Variant("b", True),
                "ProtocolVersion": GLib.Variant("i", 0)}.get(prop)

    def item_call(self, service, path, iface, method, params=None):
        return self.conn.call_sync(service, path, iface, method, params, None, Gio.DBusCallFlags.NONE, 5000, None)


class AppRun:
    """One run of app.py. Output lines starting with LOG: are collected from stderr as they arrive."""

    def __init__(self, script="", settings=None, args=(), data=None, delay=1000, extra_env=None):
        self.data = data or tempfile.mkdtemp(prefix="cl-int-data-")
        self.exports = tempfile.mkdtemp(prefix="cl-int-exp-")
        self.claude_dir = tempfile.mkdtemp(prefix="cl-int-claude-")
        if settings is not None:
            os.makedirs(self.data, exist_ok=True)
            json.dump(settings, open(os.path.join(self.data, "settings.json"), "w"))
        e = dict(os.environ, CL_DATA=self.data, CL_EXPORT_DIR=self.exports, CL_CLAUDE_DIR=self.claude_dir, CL_CLAUDE=os.path.join(env.HERE, "fake_claude.py"),
                 CL_APP_ID="dev.nein.ClaudeLinuxIntegration", CL_TEST_JS_DELAY=str(delay))
        e.update(extra_env or {})
        if script:
            e["CL_TEST_JS"] = "(async () => { try { " + HELPERS + script + " } catch (e) { post({type:'log', text: JSON.stringify({error: String(e && e.message || e) + ' | ' + String(e && e.stack || '')})}); post({type:'quit'}); } })()"
        self.proc = subprocess.Popen([sys.executable, "-W", "ignore", APP, *args], env=e, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.err, self.out = [], []
        for stream, sink in ((self.proc.stderr, self.err), (self.proc.stdout, self.out)):
            threading.Thread(target=lambda s=stream, k=sink: [k.append(l.rstrip("\n")) for l in s], daemon=True).start()

    def logs(self):
        out = []
        for line in list(self.err):
            if line.startswith("LOG: "):
                out.append(json.loads(line[5:]))
        return out

    def wait_log(self, n=1, timeout=45):
        pump(timeout, lambda: len(self.logs()) >= n or self.proc.poll() is not None)
        logs = self.logs()
        if len(logs) < n:
            self.fail_dump("expected %d log line(s) from the page" % n)
        assert "error" not in logs[-1], logs[-1]["error"]
        return logs[n - 1]

    def finish(self, timeout=30):
        pump(timeout, lambda: self.proc.poll() is not None)
        if self.proc.poll() is None:
            self.proc.kill()
            raise AssertionError("the app did not exit by itself\n" + "\n".join(self.err[-15:]))
        pump(0.3)
        return self.proc.returncode

    def fail_dump(self, why):
        if self.proc.poll() is None:
            self.proc.kill()
        raise AssertionError(why + "\n--- stderr ---\n" + "\n".join(self.err[-25:]))

    def clean(self):
        if self.proc.poll() is None:
            self.proc.kill()
        for d in (self.data, self.exports, self.claude_dir):
            shutil.rmtree(d, True)

    def problems(self):
        return [l for l in self.err if not l.startswith("LOG: ") and ("Traceback" in l or "JS ERROR" in l or "Error:" in l and "xkb" not in l.lower())]


class Base(unittest.TestCase):
    def run_app(self, *a, **k):
        r = AppRun(*a, **k)
        self.addCleanup(r.clean)
        return r

    def no_problems(self, r):
        self.assertEqual(r.problems(), [], "\n".join(r.err[-20:]))


class Startup(Base):
    SCRIPT = """
        document.getElementById('in').value = 'hello there'; send();
        await until(() => chats[cur].items.some(i => i.k === 'text' && /Echo: hello there/.test(i.text)) && !chats[cur].busy);
        log({version:S.version, usage:S.usage.rows.map(r => r.pct), email:S.account && S.account.email, plan:S.account && S.account.plan,
             hasCompact:S.cmds.includes('compact'), items:chats[cur].items.map(i => i.k + ':' + (i.text || '')), title:chats[cur].title,
             session:chats[cur].session, model:S.model, theme:document.documentElement.dataset.theme, kde:KDE.scheme ? KDE.scheme.name : null, buttons:KDE.buttons});
        post({type:'quit'});
    """

    def test_a_conversation_works_end_to_end(self):
        r = self.run_app(self.SCRIPT, settings={"tray": False})
        log = r.wait_log()
        self.assertEqual(log["version"], "9.9.9")
        self.assertEqual(log["usage"], [12, 30])
        self.assertEqual((log["email"], log["plan"]), ("test@example.com", "max"))
        self.assertTrue(log["hasCompact"])
        self.assertEqual(log["items"], ["user:hello there", "text:Echo: hello there"])
        self.assertEqual((log["title"], log["session"], log["model"]), ("hello there", "sess-1", "claude-test-1-0"))
        self.assertIn(":", log["buttons"])
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_chats_and_settings_persist_between_runs(self):
        first = self.run_app(self.SCRIPT.replace("post({type:'quit'});", "setSetting('theme', 'tokyonight'); setSetting('fontSize', 17); setSetting('projectColors', {'/x':'#123456'}); await sleep(2500); post({type:'quit'});"), settings={"tray": False})
        first.wait_log()
        self.assertEqual(first.finish(), 0)
        files = os.listdir(os.path.join(first.data, "chats"))
        self.assertEqual(len(files), 1)
        saved = json.load(open(os.path.join(first.data, "chats", files[0])))
        self.assertEqual(saved["title"], "hello there")
        s = json.load(open(os.path.join(first.data, "settings.json")))
        self.assertEqual((s["theme"], s["fontSize"], s["projectColors"]), ("tokyonight", 17, {"/x": "#123456"}))
        second = self.run_app("""log({theme:document.documentElement.dataset.theme, fs:getComputedStyle(document.documentElement).getPropertyValue('--fs').trim(),
                                   titles:Object.values(chats).map(c => c.title), items:chats[cur].items.length}); post({type:'quit'});""", data=first.data, settings=None)
        log = second.wait_log()
        self.assertEqual((log["theme"], log["fs"], log["titles"], log["items"]), ("tokyonight", "17px", ["hello there"], 2))
        self.assertEqual(second.finish(), 0)

    def test_a_missing_cli_gives_a_clear_message_and_the_app_still_opens(self):
        r = self.run_app("""log({toast:document.getElementById('toast').textContent, err:document.getElementById('toast').className, hasChats:Object.keys(chats).length}); post({type:'quit'});""",
                         settings={"tray": False}, extra_env={"CL_CLAUDE": "/nonexistent/claude"}, delay=300)
        log = r.wait_log()
        self.assertIn("Claude Code CLI was not found", log["toast"])
        self.assertIn("claude auth login", log["toast"])
        self.assertGreaterEqual(log["hasChats"], 1)
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_page_script_errors_would_show_up(self):
        r = self.run_app("post({type:'jserr', text:'planted'}); log({ok:true}); post({type:'quit'});", settings={"tray": False})
        r.wait_log()
        r.finish()
        self.assertTrue(r.problems(), "the error channel itself must work, or 'no problems' means nothing")


class WindowAndTray(Base):
    def setUp(self):
        self.host = FakeTrayHost.get()

    def test_tray_registers_responds_and_shows_attention(self):
        r = self.run_app("""
            log({stage:'up'});
            await until(() => Object.keys(chats).length >= 2, 25000);       // the test clicks "New session" in the tray menu
            chats[cur].busy = true; chats[cur].items.push({k:'tool', id:'td', name:'TodoWrite', input:{todos:[{status:'completed',content:'a'},{status:'pending',content:'b'}]}, result:'ok'});
            renderList(); await sleep(700);
            chats[cur].items.push({k:'perm', status:'wait', rid:'r9', tool:'Bash', input:{}}); renderList(); await sleep(700);
            chats[cur].items.pop(); chats[cur].busy = false; renderList(); await sleep(700);
            post({type:'appstate'}); await until(() => S.appstate);
            log({chats:Object.keys(chats).length, appstate:S.appstate});
            post({type:'quit'});
        """, settings={"tray": True})
        r.wait_log(1)
        self.assertTrue(pump(10, lambda: self.host.items), "the app never registered a tray icon")
        service = self.host.items[0]
        self.assertRegex(service, r"^org\.kde\.StatusNotifierItem-\d+-1$")
        props = self.host.item_call(service, "/StatusNotifierItem", "org.freedesktop.DBus.Properties", "GetAll", GLib.Variant("(s)", ("org.kde.StatusNotifierItem",))).unpack()[0]
        self.assertEqual((props["Id"], props["Title"], props["Status"], props["IconName"]), ("dev.nein.ClaudeLinuxIntegration", "Claude Linux", "Active", "dev.nein.ClaudeLinux"))
        rev, (root, _p, kids) = self.host.item_call(service, "/MenuBar", "com.canonical.dbusmenu", "GetLayout", GLib.Variant("(iias)", (0, -1, []))).unpack()
        self.assertEqual([k[1].get("label") for k in kids], ["Show Claude Linux", "New session", None, "Quit"])
        self.host.item_call(service, "/MenuBar", "com.canonical.dbusmenu", "Event", GLib.Variant("(isvu)", (2, "clicked", GLib.Variant("s", ""), 0)))
        log = r.wait_log(2)
        self.assertEqual(log["chats"], 2, "clicking New session in the tray must open a new session")
        self.assertTrue(log["appstate"]["tray"])
        self.assertEqual(r.finish(), 0)
        self.assertIn("NeedsAttention", [s for _, s in self.host.statuses])
        self.assertEqual([s for _, s in self.host.statuses][-1], "Active", "attention clears once the question is answered")
        # taskbar: badge, progress from the todo list, urgent while waiting
        busy = [u for u in self.host.launcher if u.get("count") == 1]
        self.assertTrue(busy, self.host.launcher)
        self.assertAlmostEqual(busy[0]["progress"], 0.5)
        self.assertTrue(busy[0]["progress-visible"])
        self.assertTrue(any(u.get("urgent") for u in self.host.launcher))
        self.assertEqual(self.host.launcher[-1]["count"], 0)
        self.assertFalse(self.host.launcher[-1]["urgent"])
        self.no_problems(r)

    def test_taskbar_can_be_turned_off(self):
        r = self.run_app("chats[cur].busy = true; renderList(); await sleep(800); log({ok:true}); post({type:'quit'});", settings={"tray": False, "taskbar": False})
        r.wait_log()
        r.finish()
        self.assertEqual(self.host.launcher, [])

    def test_close_goes_to_the_tray_and_present_brings_it_back(self):
        r = self.run_app("""
            log({stage:'up'});
            await until(() => S.settings.closeToTray);
            post({type:'close'}); await sleep(600);
            post({type:'appstate'}); S.appstate = null; post({type:'appstate'}); await until(() => S.appstate);
            log({stage:'closed', visible:S.appstate.visible});
            // wait for the test to ask the window to come back
            S.appstate = null; let back = false;
            for (let i = 0; i < 100 && !back; i++) { post({type:'appstate'}); await sleep(200); back = S.appstate && S.appstate.visible; }
            log({stage:'back', visible:back});
            post({type:'quit'});
        """, settings={"tray": True, "closeToTray": True})
        r.wait_log(1)
        self.assertTrue(pump(10, lambda: self.host.items))
        closed = r.wait_log(2)
        self.assertEqual(closed["visible"], False, "the window must hide, not quit")
        self.assertIsNone(r.proc.poll(), "the app must keep running in the tray")
        subprocess.run(["gapplication", "action", "dev.nein.ClaudeLinuxIntegration", "present"], check=True)
        back = r.wait_log(3)
        self.assertEqual(back["visible"], True)
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_close_quits_when_there_is_no_tray_to_come_back_from(self):
        r = self.run_app("await sleep(300); post({type:'close'});", settings={"tray": False, "closeToTray": True})
        self.assertEqual(r.finish(), 0)

    def test_close_quits_without_the_setting(self):
        r = self.run_app("await sleep(300); post({type:'close'});", settings={"tray": True, "closeToTray": False})
        self.assertEqual(r.finish(), 0)

    def test_second_launch_with_new_opens_a_session_in_the_first_window(self):
        r = self.run_app("""
            log({stage:'up'});
            const before = Object.keys(chats).length;
            await until(() => Object.keys(chats).length > before, 25000);
            log({before, after:Object.keys(chats).length});
            post({type:'quit'});
        """, settings={"tray": False})
        r.wait_log(1)
        second = subprocess.run([sys.executable, "-W", "ignore", APP, "--new"], env=dict(os.environ, CL_DATA=r.data, CL_APP_ID="dev.nein.ClaudeLinuxIntegration", CL_CLAUDE=os.path.join(env.HERE, "fake_claude.py")),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 0, second.stderr)
        log = r.wait_log(2)
        self.assertGreater(log["after"], log["before"])
        self.assertEqual(r.finish(), 0)

    def test_new_flag_on_a_fresh_start_opens_a_fresh_session(self):
        r = self.run_app("""
            await until(() => Object.keys(chats).length >= 1);
            await sleep(1500);
            log({n:Object.keys(chats).length, empties:Object.values(chats).filter(c => !c.items.length).length}); post({type:'quit'});
        """, settings={"tray": False}, args=("--new",))
        log = r.wait_log()
        self.assertGreaterEqual(log["empties"], 1)
        self.assertEqual(r.finish(), 0)

    def test_global_shortcut_failure_is_reported_not_fatal(self):
        r = self.run_app("""
            setSetting('hotkey', true);
            await until(() => S.hotkeyState, 15000);
            log({state:S.hotkeyState}); post({type:'quit'});
        """, settings={"tray": False})
        log = r.wait_log()
        self.assertFalse(log["state"]["ok"])
        self.assertTrue(log["state"]["msg"])
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_chrome_glass_and_fullscreen_do_not_crash(self):
        r = self.run_app("""
            for (const t of ['nord', 'light', 'cyberpunk', 'catppuccin-latte']) { setSetting('theme', t); await sleep(120); }
            setSetting('glass', true); setSetting('glassOpacity', 0.6); await sleep(300);
            post({type:'fullscreen'}); await sleep(300); post({type:'appstate'}); await until(() => S.appstate); const fs = S.appstate.fullscreen;
            post({type:'fullscreen'}); await sleep(300);
            setSetting('glass', false); setSetting('theme', 'system'); await sleep(300);
            post({type:'title', text:'A title with <b>markup</b> & "quotes"'}); await sleep(100);
            log({fs, theme:document.documentElement.dataset.theme}); post({type:'quit'});
        """, settings={"tray": False})
        log = r.wait_log()
        self.assertIn(log["theme"], ("system", "dark", "light"))
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_exports_land_in_the_export_folder(self):
        r = self.run_app("""
            document.getElementById('in').value = 'export me'; send();
            await until(() => chats[cur].items.some(i => i.k === 'text') && !chats[cur].busy);
            exportChat('md'); exportChat('html'); await sleep(500);
            exportChat('pdf'); await until(() => /Exported to|PDF failed/.test(document.getElementById('toast').textContent), 30000);
            log({toast:document.getElementById('toast').textContent}); post({type:'quit'});
        """, settings={"tray": False})
        log = r.wait_log(timeout=60)
        self.assertIn("Exported to", log["toast"])
        names = sorted(os.listdir(r.exports))
        self.assertEqual(sorted(os.path.splitext(n)[1] for n in names), [".html", ".md", ".pdf"], names)
        pdf = [n for n in names if n.endswith(".pdf")][0]
        if shutil.which("pdftotext"):
            text = subprocess.run(["pdftotext", os.path.join(r.exports, pdf), "-"], capture_output=True, text=True).stdout
            self.assertIn("Echo: export me", text)
        self.assertIn("Echo: export me", open(os.path.join(r.exports, [n for n in names if n.endswith(".html")][0])).read())
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_dropped_file_paths_reach_the_input_inside_the_real_app(self):
        r = self.run_app("""
            const dt = new DataTransfer(); dt.setData('text/uri-list', 'file:///etc/hostname\\r\\n');
            document.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
            log({value:document.getElementById('in').value}); post({type:'quit'});
        """, settings={"tray": False})
        self.assertEqual(r.wait_log()["value"], "@/etc/hostname ")
        r.finish()


class SignIn(Base):
    def test_signed_out_user_signs_in_in_the_browser_and_lands_back_in_the_app(self):
        tmp = tempfile.mkdtemp(prefix="cl-auth-")
        self.addCleanup(shutil.rmtree, tmp, True)
        auth, go = os.path.join(tmp, "auth"), os.path.join(tmp, "go")
        r = self.run_app("""
            const page = () => document.getElementById('loginpage').classList.contains('on');
            await until(page, 20000);
            const welcome = document.getElementById('loginbox').innerText;
            document.querySelector('#loginbox [data-lg=login]').click();
            await until(() => LG.url, 20000);
            log({stage:'waiting', welcome, waiting:document.getElementById('loginbox').innerText, url:LG.url});
            await until(() => !page(), 30000);
            post({type:'appstate'}); await until(() => S.appstate);
            log({stage:'back', loggedIn:S.account.loggedIn, plan:S.account.plan, visible:S.appstate.visible, inputFocusable:!!document.getElementById('in')});
            post({type:'quit'});
        """, settings={"tray": False}, extra_env={"FAKE_AUTH": auth, "FAKE_AUTH_GO": go, "CL_LOGIN_POLL": "0.5"})
        waiting = r.wait_log(1, timeout=60)
        self.assertIn("Welcome to Claude Linux", waiting["welcome"])
        self.assertIn("Finish signing in", waiting["waiting"])
        self.assertTrue(waiting["url"].startswith("https://claude.ai/oauth/authorize"))
        self.assertFalse(os.path.exists(auth), "not signed in until the browser step is done")
        open(go, "w").close()
        back = r.wait_log(2, timeout=60)
        self.assertEqual((back["loggedIn"], back["plan"], back["visible"]), (True, "max", True))
        self.assertTrue(os.path.exists(auth))
        self.assertEqual(r.finish(), 0)
        self.no_problems(r)

    def test_already_signed_in_never_sees_the_page(self):
        r = self.run_app("""await sleep(2500); log({shown:document.getElementById('loginpage').classList.contains('on')}); post({type:'quit'});""", settings={"tray": False})
        self.assertFalse(r.wait_log()["shown"])
        r.finish()

    def test_a_computer_without_the_cli_gets_the_install_page(self):
        r = self.run_app("""await sleep(2000); log({shown:document.getElementById('loginpage').classList.contains('on'), text:document.getElementById('loginbox').innerText}); post({type:'quit'});""",
                         settings={"tray": False}, extra_env={"CL_CLAUDE": "/nonexistent/claude"}, delay=300)
        log = r.wait_log()
        self.assertTrue(log["shown"])
        self.assertIn("Install Claude Code", log["text"])
        r.finish()


class SelfUpdate(Base):
    """A real app finds a signed update on a local web server, downloads it with progress, installs it and restarts."""

    @classmethod
    def setUpClass(cls):
        import updsrv
        cls.w = updsrv.World()
        cls.w.make("99.0.1", notes="Shiny new things")

    @classmethod
    def tearDownClass(cls):
        cls.w.close()

    def run_update_app(self, script, target, restart_marker):
        return self.run_app(script, settings={"tray": False}, extra_env={
            "CL_UPDATE_URL": self.w.url, "CL_UPDATE_TARGET": target, "CL_UPDATE_PUBKEY": self.w.pub, "CL_UPDATE_DELAY": "0",
            "CL_RESTART_CMD": "echo restarted > " + restart_marker})

    def test_prompt_download_install_restart(self):
        target = self.w.installed_copy("e2e-%d" % time.time_ns())
        self.addCleanup(shutil.rmtree, target, True)
        self.addCleanup(shutil.rmtree, target + ".old", True)
        marker = os.path.join(self.w.tmp, "restarted-%d" % time.time_ns())
        r = self.run_update_app("""
            await until(() => document.getElementById('updmodal').classList.contains('on'), 20000);
            const first = document.getElementById('updbox').innerText;
            const seen = [];
            const watch = setInterval(() => { const b = document.querySelector('#updbox .ubar i'); if (b) seen.push(b.style.width); }, 20);
            document.querySelector('#updbox [data-upd=download]').click();
            await until(() => document.querySelector('#updbox [data-upd=restart]'), 30000);
            clearInterval(watch);
            log({first, last:document.getElementById('updbox').innerText, version:S.appVersion, sawBar:seen.length > 0});
            document.querySelector('#updbox [data-upd=restart]').click();
        """, target, marker)
        log = r.wait_log(timeout=60)
        self.assertIn("New Update Required", log["first"])
        self.assertIn("99.0.1", log["first"])
        self.assertIn("Shiny new things", log["first"])
        self.assertIn("Update installed", log["last"])
        self.assertEqual(log["version"], VERSION)
        self.assertEqual(r.finish(), 0, "the app must quit by itself after Restart now")
        self.assertIn('"99.0.1"', open(os.path.join(target, "claude_linux/version.py")).read())
        self.assertIn('"1.0.0"', open(os.path.join(target + ".old", "claude_linux/version.py")).read())
        self.assertTrue(pump(8, lambda: os.path.exists(marker)), "the replacement copy must be started")
        self.no_problems(r)

    def test_a_tampered_update_is_refused_in_the_dialog(self):
        import json
        import updsrv
        evil = updsrv.World()
        self.addCleanup(evil.close)
        evil.make("99.0.1")
        target = self.w.installed_copy("e2e-evil-%d" % time.time_ns())
        self.addCleanup(shutil.rmtree, target, True)
        # evil author's package + checksum, but announced to an app that trusts the *real* test key
        r = self.run_app("""
            await until(() => document.getElementById('updmodal').classList.contains('on'), 20000);
            document.querySelector('#updbox [data-upd=download]').click();
            await until(() => document.querySelector('#updbox .uerr'), 30000);
            log({err:document.querySelector('#updbox .uerr').innerText, buttons:[...document.querySelectorAll('#updbox .btn')].map(b => b.innerText)});
            post({type:'quit'});
        """, settings={"tray": False}, extra_env={"CL_UPDATE_URL": evil.url, "CL_UPDATE_TARGET": target, "CL_UPDATE_PUBKEY": self.w.pub, "CL_UPDATE_DELAY": "0"})
        log = r.wait_log(timeout=60)
        self.assertIn("not signed by the Claude Linux author", log["err"])
        self.assertEqual(log["buttons"], ["Try again", "Quit"])
        self.assertEqual(r.finish(), 0)
        self.assertIn('"1.0.0"', open(os.path.join(target, "claude_linux/version.py")).read())
        self.assertFalse(os.path.exists(target + ".old"))

    def test_no_update_address_means_the_app_never_looks(self):
        r = self.run_app("""await sleep(2500); log({shown:document.getElementById('updmodal').classList.contains('on')}); post({type:'quit'});""",
                         settings={"tray": False}, extra_env={"CL_UPDATE_URL": "", "CL_UPDATE_DELAY": "0"})
        self.assertFalse(r.wait_log()["shown"])
        self.assertEqual(r.finish(), 0)


if __name__ == "__main__":
    unittest.main()
