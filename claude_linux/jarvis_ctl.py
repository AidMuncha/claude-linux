#!/usr/bin/env python3
"""How Jarvis (Claude, through Bash) asks Claude Linux to read the screen, point at things and move the mouse like a person.
usage: python3 -I jarvis_ctl.py COMMAND [ARGS]     (run `help` for the list). Needs the JARVIS_CTL socket, which Jarvis' own session has."""
import json
import os
import socket
import sys


def main():
    path = os.environ.get("JARVIS_CTL") or os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "jarvis-ctl.sock")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(path)
    except OSError as e:
        print("Jarvis is not running (%s)" % e, file=sys.stderr)
        return 2
    s.sendall((json.dumps({"argv": sys.argv[1:]}) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    try:
        r = json.loads(buf)
    except ValueError:
        print("No answer from Jarvis", file=sys.stderr)
        return 2
    if r.get("out"):
        print(r["out"])
    if r.get("error"):
        print(r["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
