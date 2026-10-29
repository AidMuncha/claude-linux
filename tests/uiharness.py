"""Runs ui/index.html in a WebKit view that is never shown, with a fake backend, so tests can drive the real page.

    page = Page()
    page.boot()                                  # answers the page's "ready" with an init message
    value = page.run("return document.title")    # JS body, may use await; returns JSON-able data
    page.posts                                   # every message the page sent to Python
"""
import json
import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")
from gi.repository import GLib, Gtk, WebKit  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import env  # noqa: E402,F401  (must come first: redirects the app to temp folders)
import build  # noqa: E402

Gtk.init()


class Page:
    def __init__(self, w=1240, h=820):
        build.build()
        self.posts, self.errors, self._res, self._n = [], [], {}, 0
        ucm = WebKit.UserContentManager()
        ucm.register_script_message_handler("bridge", None)
        ucm.connect("script-message-received::bridge", self._on_msg)
        self.web = WebKit.WebView(user_content_manager=ucm)
        self.web.set_size_request(w, h)
        self.win = Gtk.Window()          # never presented: nothing appears on screen
        self.win.set_default_size(w, h)
        self.win.set_child(self.web)
        if os.environ.get("CL_PRESENT"):   # under `run_tests.sh` (a headless compositor) the window is shown so the page really renders
            self.win.present()
        self.web.load_uri("file://" + os.path.join(HERE, "ui", "index.html"))

    def _on_msg(self, _ucm, value):
        m = json.loads(value.to_json(0))
        if m.get("type") == "__res":
            self._res[m["id"]] = m
            return
        if m.get("type") == "jserr":
            self.errors.append(m.get("text"))
        self.posts.append(m)

    def spin(self, ms):
        """Let the page run for `ms` milliseconds (animations, timers, rAF) by pumping the main loop."""
        end = time.monotonic() + ms / 1000
        ctx = GLib.MainContext.default()
        while time.monotonic() < end:
            if not ctx.iteration(False):
                time.sleep(0.004)

    def wait_for(self, pred, timeout=10000):
        left = timeout
        while not pred() and left > 0:
            self.spin(50)
            left -= 50
        return pred()

    def boot(self, init=None):
        assert self.wait_for(lambda: any(p.get("type") == "ready" for p in self.posts), 15000), "page never sent ready"
        payload = {"chats": {}, "home": "/home/test", "version": "0.0.0-test", "settings": {"theme": "dark"}, "usage": None}
        payload.update(init or {})
        self.send("init", payload)
        return self

    def send(self, name, payload):
        self.web.evaluate_javascript("window.fromPyBatch(%s)" % json.dumps([[name, payload]]), -1, None, None, None, None, None)
        self.spin(60)

    def run(self, body, timeout=10000):
        self._n += 1
        i = self._n
        js = ("(async()=>{try{const __r=await (async()=>{%s})();"
              "window.webkit.messageHandlers.bridge.postMessage({type:'__res',id:%d,ok:true,val:JSON.stringify(__r===undefined?null:__r)})}"
              "catch(e){window.webkit.messageHandlers.bridge.postMessage({type:'__res',id:%d,ok:false,err:String(e&&e.stack||e)})}})()") % (body, i, i)
        self.web.evaluate_javascript(js, -1, None, None, None, None, None)
        if not self.wait_for(lambda: i in self._res, timeout):
            raise TimeoutError("JS did not finish: " + body[:120])
        r = self._res.pop(i)
        if not r["ok"]:
            raise RuntimeError("JS error: " + r["err"])
        return json.loads(r["val"])

    def snapshot(self, path, timeout=10000):
        """Saves what the page currently looks like as a PNG (needs the window to be shown: CL_PRESENT=1)."""
        done = []
        self.web.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE, None,
                              lambda web, res: (web.get_snapshot_finish(res).save_to_png(path), done.append(1)))
        assert self.wait_for(lambda: done, timeout), "snapshot timed out"

    def sent(self, typ):
        return [p for p in self.posts if p.get("type") == typ]
