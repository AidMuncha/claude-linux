# Claude Linux

A desktop window around the Claude Code CLI (GTK 4 + WebKitGTK).

- Run from this folder: `./run.sh` (rebuilds the UI automatically if you edited `ui/css` or `ui/js`)
- Install for yourself or friends: `./make-installer.sh` makes `claude-linux-installer.sh`; run it with `bash`.
- Tests: `tests/run_tests.sh` (headless, never touches your real chats/settings)
- Push an update to everyone who installed it: `python3 release.py 1.1.0 --notes "what changed"`, then upload `dist/`
  to the address in `claude_linux/update_url.txt`. Keep `~/.local/share/claude-linux-release/private.pem` safe.

- Jarvis: type `/jarvis` (talk to him) or `/jarvistextmode` (type to him) in any chat. The first start downloads his voice and the
  speech recognizer (about 700 MB, once). Say "stand down" or use `/jarvis off` to stop him.
  Ask him to read something on your screen and a blue hologram follows each word over the real text, then turns green and fades.
  He moves the mouse like a person (curved, eased); the first use asks KDE once for permission.
  Screen share (like a Discord stream): `/jarvis share`, or say "watch this with me". `/jarvis watch` adds automatic commentary.

Layout: `claude_linux/` (Python), `ui/css` + `ui/js` (built into `ui/index.html` by `build.py`), `tests/`.
