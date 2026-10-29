"""Everything that is not GTK: settings, chats, and the Claude Code CLI processes."""
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from gi.repository import Gio, GLib

from .paths import CLAUDE, CLAUDE_FILES, CHATDIR, CMDS, EXPORT_DIR, HOME, SETTINGS
from .settings import DEFAULTS
from . import update
from .util import load_chats, parse_usage, read_json, write_json
from .version import VERSION


class Core:
    def __init__(self, push, app):
        self.push, self.app = push, app
        self.chats = load_chats()
        self.dirty, self.busy_since = set(), {}
        self.settings = {**DEFAULTS, **read_json(SETTINGS, {})}
        self.procs, self.busy = {}, set()
        self._save_timer = None
        self._usage_busy = False
        self.usage = None
        self._fcache = {}
        self._update_started, self.update_manifest, self._update_busy = False, None, False

    # ---------- persistence ----------
    def save_settings(self):
        write_json(SETTINGS, self.settings)

    def save_chats_soon(self, cid=None):
        if cid:
            self.dirty.add(cid)
        if self._save_timer:
            return

        def go():
            self._save_timer = None
            self.flush_chats()
        self._save_timer = threading.Timer(1.5, go)
        self._save_timer.start()

    def flush_chats(self):
        dirty, self.dirty = self.dirty, set()
        for cid in dirty:
            c = self.chats.get(cid)
            if c and c.get("items"):
                write_json(os.path.join(CHATDIR, os.path.basename(cid) + ".json"), c)

    @staticmethod
    def version():
        try:
            return subprocess.check_output([CLAUDE, "--version"], text=True).split()[0]
        except Exception:
            return "?"

    def handle(self, m):
        fn = getattr(self, "h_" + str(m.get("type")), None)
        if fn:
            fn(m)

    # ---------- basic handlers ----------
    def h_ready(self, m):
        self.push("init", {"chats": self.chats, "home": HOME, "version": self.version(),
                           "settings": self.settings, "usage": self.usage, "appVersion": VERSION})
        if not (os.path.isfile(CLAUDE) and os.access(CLAUDE, os.X_OK)):
            self.push("toast", {"text": "The Claude Code CLI was not found. Install it from claude.com/claude-code, then run: claude auth login", "err": True})
        self.start_update_checks()
        self.refresh_usage()
        self.h_account({})
        cached = read_json(CMDS, None)
        if cached:
            self.push("cmds", cached)
        self.h_cmds({})

    def h_save(self, m):
        c = m["chat"]
        c.pop("busy", None)
        self.chats[m["id"]] = c
        self.save_chats_soon(m["id"])

    def h_delete(self, m):
        self.chats.pop(m["id"], None)
        self.dirty.discard(m["id"])
        try:
            os.remove(os.path.join(CHATDIR, os.path.basename(m["id"]) + ".json"))
        except OSError:
            pass
        self.kill(m["id"])

    def h_stop(self, m):
        self.kill(m.get("chat"))

    def h_setsettings(self, m):
        self.settings.update({k: v for k, v in m["patch"].items() if k in DEFAULTS})
        self.save_settings()
        if self.app and hasattr(self.app, "apply_settings"):
            GLib.idle_add(lambda: self.app.apply_settings(self.settings) and False)

    def h_pickdir(self, m):
        GLib.idle_add(self.app.pickdir, m.get("start", ""))

    def h_getfile(self, m):
        p = CLAUDE_FILES[m["which"]]
        try:
            text = open(p).read()
        except Exception:
            text = "{}\n" if m["which"] == "settings" else ""
        self.push("file", {"which": m["which"], "text": text, "path": p})

    def h_putfile(self, m):
        p, text = CLAUDE_FILES[m["which"]], m["text"]
        try:
            if m["which"] == "settings":
                json.loads(text or "{}")
            self.backup_write(p, text)
            self.push("toast", {"text": "Saved"})
            self.h_getfile({"which": m["which"]})
        except Exception as e:
            self.push("toast", {"text": f"Not saved: {e}", "err": True})

    @staticmethod
    def backup_write(p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.exists(p):
            shutil.copy(p, p + ".claude-linux.bak")
        with open(p, "w") as f:
            f.write(text)

    def h_cset(self, m):
        """Set (or with value None, remove) a dotted key in ~/.claude/settings.json."""
        p = CLAUDE_FILES["settings"]
        data = read_json(p, {})
        cur = data
        parts = m["key"].split(".")
        for k in parts[:-1]:
            cur = cur.setdefault(k, {})
        if m.get("value") is None:
            cur.pop(parts[-1], None)
        else:
            cur[parts[-1]] = m["value"]
        try:
            self.backup_write(p, json.dumps(data, indent=2) + "\n")
        except Exception as e:
            self.push("toast", {"text": f"Not saved: {e}", "err": True})
        self.h_getfile({"which": "settings"})

    def h_mcp(self, m):
        def run():
            try:
                out = subprocess.run([CLAUDE, "mcp", "list"], capture_output=True, text=True, timeout=60,
                                     cwd=HOME).stdout.strip() or "No MCP servers configured."
            except Exception as e:
                out = f"claude mcp list failed: {e}"
            self.push("sysmsg", {"text": out})
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def safe_name(title, default="chat"):
        return "".join(ch for ch in title if ch.isalnum() or ch in " -_")[:40].strip() or default

    @staticmethod
    def unique_path(directory, name, ext):
        """directory/name.ext, or name (2).ext, ... so an export never overwrites an earlier one."""
        os.makedirs(directory, exist_ok=True)
        path, n = os.path.join(directory, name + ext), 2
        while os.path.exists(path):
            path = os.path.join(directory, "%s (%d)%s" % (name, n, ext))
            n += 1
        return path

    def h_export(self, m):
        c = self.chats.get(m["chat"])
        if not c:
            return
        lines = [f"# {c.get('title', 'Chat')}\n"]
        for it in c.get("items", []):
            k = it.get("k")
            if k == "user":
                lines.append(f"**You:** {it['text']}\n")
            elif k == "text":
                lines.append(it["text"] + "\n")
            elif k == "tool":
                lines.append(f"`{it['name']}` {json.dumps(it.get('input'))[:200]}\n")
        path = self.unique_path(EXPORT_DIR, self.safe_name(c.get("title", "chat")), ".md")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        self.push("toast", {"text": f"Exported to {path}"})

    def h_savetext(self, m):
        """Saves text the page produced (HTML export, theme JSON) into ~/Downloads without overwriting anything."""
        ext = m.get("ext") if m.get("ext") in (".html", ".json") else ".txt"
        path = self.unique_path(EXPORT_DIR, self.safe_name(m.get("name", ""), "export"), ext)
        with open(path, "w") as f:
            f.write(m.get("text", ""))
        self.push("toast", {"text": f"Saved {path}"})

    def h_fonts(self, m):
        def run():
            try:
                out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=20).stdout
            except Exception:
                out = ""
            fams = sorted({line.split(",")[0].strip() for line in out.splitlines() if line.strip()}, key=str.lower)
            self.push("fonts", {"fonts": fams})
        threading.Thread(target=run, daemon=True).start()

    def h_open_url(self, m):
        url = m.get("url", "")
        if url.startswith("https://"):
            GLib.idle_add(lambda: Gio.AppInfo.launch_default_for_uri(url, None) and False)

    # ---------- updates: see update.py ----------
    def start_update_checks(self):
        """Looks for a new version a few seconds after start, then every 6 hours. Silent when offline or unconfigured."""
        if self._update_started:
            return
        self._update_started = True
        update.cleanup_old(update.target_dir())

        def loop():
            time.sleep(float(os.environ.get("CL_UPDATE_DELAY", "4")))
            while True:
                self.check_update(manual=False)
                time.sleep(6 * 3600)
        threading.Thread(target=loop, daemon=True).start()

    def check_update(self, manual):
        url = update.manifest_url()
        if not url:
            if manual:
                self.push("update", {"state": "disabled", "version": VERSION})
            return
        try:
            m = update.fetch_manifest(url)
            if update.is_newer(m["version"]):
                self.update_manifest = m
                self.push("update", {"state": "available", "version": m["version"], "current": VERSION, "notes": m["notes"],
                                     "required": m["required"], "size": m.get("size", 0), "canInstall": bool(update.target_dir())})
            elif manual:
                self.push("update", {"state": "current", "version": VERSION})
        except (update.UpdateError, OSError, ValueError) as e:
            if manual:
                self.push("update", {"state": "error", "message": "Could not check for updates: %s" % e, "retry": "check"})

    def h_update_check(self, m):
        threading.Thread(target=self.check_update, args=(True,), daemon=True).start()

    def h_update_download(self, m):
        manifest = self.update_manifest
        if not manifest or self._update_busy:
            return
        self._update_busy = True

        def run():
            last = [0.0]

            def progress(done, total):
                if time.time() - last[0] > 0.08 or done == total:
                    last[0] = time.time()
                    self.push("update", {"state": "downloading", "done": done, "total": total})
            try:
                self.push("update", {"state": "downloading", "done": 0, "total": manifest.get("size", 0)})
                update.download_and_install(manifest, update.target_dir(), progress)
                self.push("update", {"state": "ready", "version": manifest["version"]})
            except update.UpdateError as e:
                self.push("update", {"state": "error", "message": str(e), "retry": "download"})
            except Exception as e:  # never leave the dialog stuck on "downloading"
                self.push("update", {"state": "error", "message": "Unexpected problem: %s" % e, "retry": "download"})
            finally:
                self._update_busy = False
        threading.Thread(target=run, daemon=True).start()

    def h_update_restart(self, m):
        if self.app and hasattr(self.app, "restart"):
            GLib.idle_add(lambda: self.app.restart() and False)

    def h_quit(self, m):
        GLib.idle_add(self.app.quit)

    # ---------- real usage: `/usage` is answered locally by the CLI (no tokens, no cost) ----------
    def refresh_usage(self):
        if self._usage_busy:
            return
        self._usage_busy = True

        def run():
            try:
                out = subprocess.run([CLAUDE, "-p", "/usage", "--output-format", "json", "--no-session-persistence"],
                                     capture_output=True, text=True, timeout=60, cwd=HOME,
                                     stdin=subprocess.DEVNULL).stdout
                self.usage = parse_usage(json.loads(out).get("result") or "")
                self.push("usage", self.usage)
            except Exception as e:
                self.push("usage", {"error": str(e), "rows": [], "text": "", "ts": time.time()})
            self._usage_busy = False
        threading.Thread(target=run, daemon=True).start()

    def h_refresh_usage(self, m):
        self.refresh_usage()

    # ---------- Remote Control: per chat, same as /remote-control in Claude Code ----------
    def ctl(self, cid, request, prefix="rc-", rid=None):
        p = self.procs.get(cid)
        if not p or p["proc"].poll() is not None:
            return False
        msg = {"type": "control_request", "request_id": rid or prefix + uuid.uuid4().hex[:10], "request": request}
        p["proc"].stdin.write(json.dumps(msg) + "\n")
        p["proc"].stdin.flush()
        return True

    def notify(self, title, body, nid):
        if self.settings.get("notify", True) and self.app:
            self.app.notify(title, body, nid)

    # ---------- MCP servers ----------
    def h_mcp_list(self, m):
        def run():
            rows = []
            try:
                out = subprocess.run([CLAUDE, "mcp", "list"], capture_output=True, text=True, timeout=90, cwd=HOME,
                                     stdin=subprocess.DEVNULL).stdout
                for line in out.splitlines():
                    if ": " not in line or line.startswith("Checking"):
                        continue
                    name, _, rest = line.partition(": ")
                    target, _, status = rest.rpartition(" - ")
                    rows.append({"name": name.strip(), "target": target.strip(), "status": status.strip()})
            except Exception as e:
                self.push("mcp_state", {"rows": [], "error": str(e)})
                return
            self.push("mcp_state", {"rows": rows})
        threading.Thread(target=run, daemon=True).start()

    def h_mcp_add(self, m):
        def run():
            name, target, tr, scope = m["name"].strip(), m["target"].strip(), m.get("transport", "stdio"), m.get("scope", "user")
            cmd = [CLAUDE, "mcp", "add", "-s", scope]
            if tr == "stdio":
                cmd += [name, "--"] + shlex.split(target)
            else:
                cmd += ["--transport", tr, name, target]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=HOME, stdin=subprocess.DEVNULL)
            self.push("toast", {"text": f"Added {name}" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-200:], "err": r.returncode != 0})
            self.h_mcp_list({})
        threading.Thread(target=run, daemon=True).start()

    def h_mcp_remove(self, m):
        def run():
            ok = False
            for scope in ("user", "local", "project"):
                r = subprocess.run([CLAUDE, "mcp", "remove", "-s", scope, m["name"]], capture_output=True, text=True,
                                   timeout=60, cwd=HOME, stdin=subprocess.DEVNULL)
                if r.returncode == 0:
                    ok = True
                    break
            self.push("toast", {"text": "Removed " + m["name"] if ok else "Could not remove (managed by your account?)", "err": not ok})
            self.h_mcp_list({})
        threading.Thread(target=run, daemon=True).start()

    def h_perm_reply(self, m):
        """Answer a can_use_tool request (permission card, AskUserQuestion, plan approval)."""
        p = self.procs.get(m["chat"])
        if not p or p["proc"].poll() is not None:
            return
        if m.get("allow"):
            body = {"behavior": "allow", "updatedInput": m.get("input") or {}}
            if m.get("perms"):
                body["updatedPermissions"] = m["perms"]
        else:
            body = {"behavior": "deny", "message": m.get("message") or "The user doesn't want to proceed with this tool use."}
        msg = {"type": "control_response", "response": {"subtype": "success", "request_id": m["rid"], "response": body}}
        try:
            p["proc"].stdin.write(json.dumps(msg) + "\n")
            p["proc"].stdin.flush()
        except Exception as e:
            self.push("error", {"chat": m["chat"], "text": str(e)})

    def h_rewind(self, m):
        """Restore files to how they were before a user message (CLI file checkpoints)."""
        dry = bool(m.get("dry"))
        if not self.ctl(m["chat"], {"subtype": "rewind_files", "user_message_id": m["uid"], "dry_run": dry},
                        rid="rw-%s-%s" % ("dry" if dry else "do", m["uid"])):
            self.push("rewind", {"chat": m["chat"], "dry": dry, "uid": m["uid"], "ok": False,
                                 "error": "This session isn't running, so its checkpoints are gone. Send a message first.", "files": [], "ins": 0, "del": 0})

    def h_stoptask(self, m):
        self.ctl(m["chat"], {"subtype": "stop_task", "task_id": m["task_id"]}, prefix="st-")

    def h_resetproc(self, m):
        self.kill(m["chat"])

    def h_setmode(self, m):
        p = self.procs.get(m["chat"])
        if p and self.ctl(m["chat"], {"subtype": "set_permission_mode", "mode": m["mode"]}, prefix="sm-"):
            p["mode"] = m["mode"]

    # ---------- slash commands / skills: ask the CLI itself (a local command, no tokens) ----------
    def h_cmds(self, m):
        def run():
            try:
                proc = subprocess.Popen([CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                                         "--verbose", "--no-session-persistence"], cwd=m.get("cwd") or HOME, text=True,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": "/usage"}}) + "\n")
                proc.stdin.flush()
                for line in proc.stdout:
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("type") == "system" and ev.get("subtype") == "init":
                        d = {"commands": ev.get("slash_commands", []), "skills": ev.get("skills", [])}
                        write_json(CMDS, d)
                        self.push("cmds", d)
                        break
                proc.terminate()
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ---------- `!command` bash mode ----------
    def h_bang(self, m):
        cwd = m.get("cwd") if os.path.isdir(m.get("cwd") or "") else HOME

        def run():
            try:
                r = subprocess.run(["bash", "-lc", m["cmd"]], cwd=cwd, capture_output=True, text=True, timeout=120,
                                   stdin=subprocess.DEVNULL)
                out, err, code = r.stdout, r.stderr, r.returncode
            except subprocess.TimeoutExpired:
                out, err, code = "", "Command timed out after 120s", 124
            except Exception as e:
                out, err, code = "", str(e), 1
            self.push("bang", {"chat": m["chat"], "id": m["id"], "out": out[-20000:], "err": err[-5000:], "code": code})
        threading.Thread(target=run, daemon=True).start()

    # ---------- @file mentions ----------
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", "target", "dist", "build", ".next"}

    def h_files(self, m):
        root = m.get("cwd") if os.path.isdir(m.get("cwd") or "") else HOME
        q = (m.get("q") or "").lower()

        def run():
            hit = self._fcache.get(root)
            if hit and time.time() - hit[0] < 15:
                files = hit[1]
            else:
                files = self.scan(root)
                self._fcache[root] = (time.time(), files)
            self.rank(m, q, files)

        threading.Thread(target=run, daemon=True).start()

    def scan(self, root):
        files = []
        try:
            out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True,
                                 text=True, timeout=5).stdout.split("\n")
            files = [f for f in out if f]
        except Exception:
            pass
        if not files:
            for dp, dn, fn in os.walk(root):
                dn[:] = [d for d in dn if d not in self.SKIP and not d.startswith(".")]
                depth = dp[len(root):].count(os.sep)
                if depth >= 5:
                    dn[:] = []
                for f in fn:
                    if not f.startswith("."):
                        files.append(os.path.relpath(os.path.join(dp, f), root))
                if len(files) > 8000:
                    break
        return files

    def rank(self, m, q, files):
        def score(f):
            lf, base = f.lower(), os.path.basename(f).lower()
            if not q:
                return 3 + f.count("/")
            if base.startswith(q):
                return 0
            if q in base:
                return 1
            if q in lf:
                return 2
            it = iter(lf)
            return 4 if all(c in it for c in q) else None
        ranked = sorted((s, len(f), f) for f in files for s in [score(f)] if s is not None)[:30]
        self.push("files", {"chat": m["chat"], "q": m.get("q", ""), "files": [f for _, _, f in ranked]})

    def h_rc_chat(self, m):
        cid = m["chat"]
        chat = self.chats.setdefault(cid, {})
        for k in ("kind", "cwd", "mode", "session", "title"):
            if k in m:
                chat[k] = m[k]
        if chat.get("kind") == "chat":
            self.push("rc_resp", {"chat": cid, "ok": False, "error": "Remote Control is only available in Code chats."})
            return
        chat["rc"] = {"on": bool(m["on"])}
        try:
            if m["on"]:
                self.get_proc(cid, chat)  # starts the chat's Claude process if needed (enables on spawn)
                self.enable_rc(cid, chat)
            else:
                self.ctl(cid, {"subtype": "remote_control", "enabled": False})
        except Exception as e:
            self.push("rc_resp", {"chat": cid, "ok": False, "error": str(e)})

    def enable_rc(self, cid, chat):
        name = (chat.get("title") or "Claude Linux")[:60]
        self.ctl(cid, {"subtype": "remote_control", "enabled": True, "name": name})

    def h_account(self, m):
        def run():
            try:
                out = subprocess.run([CLAUDE, "auth", "status"], capture_output=True, text=True, timeout=30,
                                     cwd=HOME, stdin=subprocess.DEVNULL).stdout
                d = json.loads(out)
                self.push("account", {"loggedIn": d.get("loggedIn"), "method": d.get("authMethod"),
                                      "plan": d.get("subscriptionType"), "email": d.get("email")})
            except Exception as e:
                missing = not (os.path.isfile(CLAUDE) and os.access(CLAUDE, os.X_OK))
                self.push("account", {"loggedIn": None, "error": str(e), "missing": missing})
        threading.Thread(target=run, daemon=True).start()

    # ---------- signing in: `claude auth login` opens the browser; we wait for it, then bring the window back ----------
    URL_RE = re.compile(r"https://[^\s\"'<>]+")

    def auth_ok(self):
        try:
            out = subprocess.run([CLAUDE, "auth", "status"], capture_output=True, text=True, timeout=30, cwd=HOME, stdin=subprocess.DEVNULL).stdout
            return bool(json.loads(out).get("loggedIn"))
        except Exception:
            return False

    def h_login(self, m):
        if getattr(self, "_login", None) and self._login.poll() is None:
            return
        flag = "--console" if m.get("mode") == "console" else "--claudeai"
        try:
            proc = subprocess.Popen([CLAUDE, "auth", "login", flag], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=HOME)
        except OSError as e:
            self.push("login", {"state": "error", "message": "Could not start the sign-in: %s" % e})
            return
        self._login, self._login_cancelled = proc, False
        self.push("login", {"state": "waiting"})

        def read():
            """Reads the CLI's output as it arrives (its 'Paste code' prompt has no newline), looking for the sign-in link and that prompt."""
            seen_url, asked, buf = None, False, ""
            fd = proc.stdout.fileno()
            while True:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf = (buf + chunk.decode("utf-8", "replace"))[-4000:]
                m2 = self.URL_RE.search(buf)
                if m2 and m2.group(0).rstrip(".,)") != seen_url:
                    seen_url = m2.group(0).rstrip(".,)")
                    self.push("login", {"state": "waiting", "url": seen_url, "needCode": asked})
                if not asked and re.search(r"paste code here", buf, re.I):
                    asked = True      # the browser cannot hand the sign-in back by itself: the user has to paste the code the page shows
                    self.push("login", {"state": "waiting", "url": seen_url, "needCode": True})
        threading.Thread(target=read, daemon=True).start()

        def watch():
            start, last = time.time(), 0.0
            limit = float(os.environ.get("CL_LOGIN_TIMEOUT", "600"))
            while proc.poll() is None and time.time() - start < limit:
                time.sleep(0.3)
                if time.time() - last > float(os.environ.get("CL_LOGIN_POLL", "4")):
                    last = time.time()
                    if self.auth_ok():            # signed in even though the CLI is still wrapping up
                        proc.terminate()
                        break
            if self._login_cancelled:
                return
            timed_out = proc.poll() is None
            if timed_out:
                proc.kill()
            if not timed_out and self.auth_ok():
                self.push("login", {"state": "done"})
                self.h_account({})
                self.refresh_usage()
                self.h_cmds({})
                if self.app and hasattr(self.app, "show_window"):
                    GLib.idle_add(lambda: self.app.show_window() and False)      # back to the app, in front of the browser
            else:
                self.push("login", {"state": "error", "message": "Sign-in timed out. Please try again." if timed_out else
                                    "Sign-in did not finish. Please try again."})
        threading.Thread(target=watch, daemon=True).start()

    CODE_RE = re.compile(r"[A-Za-z0-9_\-#.~%+/=]{8,600}")

    def h_login_code(self, m):
        proc = getattr(self, "_login", None)
        code = str(m.get("code", "")).strip()
        if not (proc and proc.poll() is None):
            return
        if not self.CODE_RE.fullmatch(code):
            self.push("toast", {"text": "That does not look like a sign-in code. Copy the whole code from the browser page.", "err": True})
            return
        try:
            proc.stdin.write((code + "\n").encode())
            proc.stdin.flush()
        except OSError:
            pass

    def h_login_cancel(self, m):
        proc = getattr(self, "_login", None)
        if proc and proc.poll() is None:
            self._login_cancelled = True
            proc.terminate()
        self.push("login", {"state": "idle"})

    INSTALL_CMD = "curl -fsSL https://claude.ai/install.sh | bash"

    def h_install_cli(self, m):
        """One click for a fresh machine: runs Anthropic's own installer and reports its last output line."""
        if getattr(self, "_installing", False):
            return
        self._installing = True

        def run():
            self.push("login", {"state": "installing", "line": "Starting…"})
            tail = []
            try:
                p = subprocess.Popen(["bash", "-c", os.environ.get("CL_INSTALL_CMD") or self.INSTALL_CMD], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, cwd=HOME)
                for line in p.stdout:
                    line = line.strip()
                    if line:
                        tail = (tail + [line])[-6:]
                        self.push("login", {"state": "installing", "line": line[:140]})
                rc = p.wait()
            except OSError as e:
                rc, tail = 1, [str(e)]
            if rc == 0 and os.path.isfile(CLAUDE) and os.access(CLAUDE, os.X_OK):
                self.push("toast", {"text": "Claude Code installed"})
                self.h_account({})
                self.push("login", {"state": "idle"})
            else:
                self.push("login", {"state": "error", "message": "The install did not finish: " + (tail[-1] if tail else "no output"), "retry": "install"})
            self._installing = False
        threading.Thread(target=run, daemon=True).start()

    # ---------- claude processes ----------
    def kill(self, chat):
        p = self.procs.pop(chat, None)
        if p and p["proc"].poll() is None:
            p["proc"].terminate()

    def kill_all(self):
        for c in list(self.procs):
            self.kill(c)

    def model_arg(self):
        s = self.settings
        if not s["model"]:
            return ""
        return s["model"] + ("[1m]" if s.get("long") and s["model"] != "opusplan" else "")

    def build_cmd(self, chat):
        s = self.settings
        cmd = [CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--include-partial-messages", "--replay-user-messages"]
        if chat.get("kind") == "chat":
            cmd += ["--tools", "", "--append-system-prompt",
                    "You are in Chat mode inside Claude Linux: you have no access to the user's computer, "
                    "files or shell. Answer conversationally; if they need actions on their PC, suggest "
                    "switching to Code mode."]
        else:
            cmd += ["--permission-mode", chat.get("mode") or s["mode"], "--permission-prompt-tool", "stdio"]
            for d in s["addDirs"]:
                cmd += ["--add-dir", d]
            if s["appendPrompt"]:
                cmd += ["--append-system-prompt", s["appendPrompt"]]
        if self.model_arg():
            cmd += ["--model", self.model_arg()]
        if s["effort"]:
            cmd += ["--effort", s["effort"]]
        if s["fallback"]:
            cmd += ["--fallback-model", s["fallback"]]
        if s["maxTurns"]:
            cmd += ["--max-turns", str(s["maxTurns"])]
        if chat.get("session"):
            cmd += ["--resume", chat["session"]]
            if chat.get("resumeAt"):
                cmd += ["--fork-session", "--resume-session-at", chat["resumeAt"]]
        return cmd

    @staticmethod
    def strip_opt(cmd, opt):
        if opt in cmd:
            i = cmd.index(opt)
            return cmd[:i] + cmd[i + 2:]
        return cmd

    def get_proc(self, cid, chat):
        cwd = chat.get("cwd") if chat.get("kind") != "chat" else HOME
        cwd = cwd if cwd and os.path.isdir(cwd) else HOME
        cmd = self.build_cmd(chat)
        mode = cmd[cmd.index("--permission-mode") + 1] if "--permission-mode" in cmd else None
        base = [x for x in cmd if x != "--fork-session"]
        for opt in ("--resume", "--permission-mode", "--resume-session-at"):
            base = self.strip_opt(base, opt)
        key = (tuple(base), cwd)
        p = self.procs.get(cid)
        if p and p["proc"].poll() is None and p["key"] == key:
            if mode and p.get("mode") != mode:
                self.ctl(cid, {"subtype": "set_permission_mode", "mode": mode})
                p["mode"] = mode
            return p
        self.kill(cid)
        env = dict(os.environ, CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING="1")
        proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        p = {"proc": proc, "key": key, "mode": mode}
        self.procs[cid] = p
        chat.pop("resumeAt", None)
        threading.Thread(target=self.reader, args=(cid, proc), daemon=True).start()
        if (chat.get("rc") or {}).get("on") and chat.get("kind") != "chat":
            self.enable_rc(cid, chat)
        return p

    def reader(self, cid, proc):
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                typ = ev.get("type")
                if typ == "rate_limit_event":
                    continue
                if typ == "control_request":
                    r = ev.get("request", {})
                    if r.get("subtype") == "can_use_tool":
                        self.notify("Claude needs your input", f'{r.get("tool_name")} · {(self.chats.get(cid) or {}).get("title", "")}', cid)
                        self.push("perm", {"chat": cid, "rid": ev.get("request_id"), "tool": r.get("tool_name"),
                                           "input": r.get("input") or {}, "desc": r.get("description", ""),
                                           "suggestions": r.get("permission_suggestions") or [],
                                           "blocked": r.get("blocked_path", ""), "tid": r.get("tool_use_id", "")})
                    continue
                if typ == "control_cancel_request":
                    self.push("perm_cancel", {"chat": cid, "rid": ev.get("request_id")})
                    continue
                if typ == "control_response":
                    r = ev.get("response", {})
                    rq = str(r.get("request_id", ""))
                    if rq.startswith("rw-"):
                        _, kind, uid_ = rq.split("-", 2)
                        body = r.get("response") or {}
                        self.push("rewind", {"chat": cid, "dry": kind == "dry", "uid": uid_, "ok": r.get("subtype") == "success" and body.get("canRewind", True),
                                             "error": r.get("error") or body.get("error", ""), "files": body.get("filesChanged") or [],
                                             "ins": body.get("insertions", 0), "del": body.get("deletions", 0)})
                        continue
                    if rq.startswith("rc-"):
                        body = r.get("response") or {}
                        self.push("rc_resp", {"chat": cid, "ok": r.get("subtype") == "success",
                                              "error": r.get("error", ""), "url": body.get("session_url", "")})
                    continue
                if typ == "system" and ev.get("subtype") == "bridge_state":
                    self.push("rc_state", {"chat": cid, "state": ev.get("state")})
                    continue
                if typ == "system" and ev.get("subtype") == "init":
                    self.push("meta_init", {"chat": cid, "session": ev.get("session_id"), "model": ev.get("model"),
                                            "commands": ev.get("slash_commands", [])})
                    continue
                self.push("event", {"chat": cid, "ev": ev})
                if typ == "result":
                    if time.time() - self.busy_since.get(cid, time.time()) > 8:
                        self.notify("Claude finished", (self.chats.get(cid) or {}).get("title", ""), cid)
                    self.busy.discard(cid)
                    self.push("done", {"chat": cid})
                    self.refresh_usage()
            err = proc.stderr.read().strip()
            if proc.wait() and err:
                self.push("error", {"chat": cid, "text": err[-600:]})
        except Exception as e:
            self.push("error", {"chat": cid, "text": str(e)})
        cur = self.procs.get(cid)
        if cur is None or cur["proc"] is proc:
            self.procs.pop(cid, None)
            self.busy.discard(cid)
            self.push("done", {"chat": cid})

    def h_send(self, m):
        cid, text = m["chat"], (m.get("text") or "").strip()
        if (not text and not m.get("images")) or cid in self.busy:
            return
        chat = self.chats.setdefault(cid, {})
        for k in ("kind", "cwd", "mode", "session", "resumeAt"):
            if k in m:
                chat[k] = m[k]
        self.busy.add(cid)
        self.busy_since[cid] = time.time()
        try:
            p = self.get_proc(cid, chat)
            content = text
            if m.get("images"):
                content = [{"type": "image", "source": {"type": "base64", "media_type": i["type"], "data": i["data"]}}
                           for i in m["images"]] + ([{"type": "text", "text": text}] if text else [])
            msg = {"type": "user", "message": {"role": "user", "content": content}}
            if m.get("uuid"):
                msg["uuid"] = m["uuid"]
            p["proc"].stdin.write(json.dumps(msg) + "\n")
            p["proc"].stdin.flush()
        except Exception as e:
            self.busy.discard(cid)
            self.push("error", {"chat": cid, "text": str(e)})
            self.push("done", {"chat": cid})
