"""A small local socket so Jarvis' own tool calls (jarvis_ctl.py) can reach the running app. Owner-only, in the user's runtime directory."""
import json
import os
import socket
import threading


class Ctl:
    def __init__(self, path, dispatch):
        self.path, self.dispatch = path, dispatch        # dispatch(argv list) -> {"out": str} or {"error": str}
        self.sock = None
        self.running = False

    def start(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(4)
        self.running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < 100000:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            try:
                argv = json.loads(buf)["argv"]
                reply = self.dispatch([str(a) for a in argv])
            except Exception as e:
                reply = {"error": "Jarvis could not do that: %s" % e}
            conn.sendall((json.dumps(reply) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()

    def stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
            os.remove(self.path)
        except OSError:
            pass
