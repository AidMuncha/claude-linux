# Claude Linux

A desktop window around the Claude Code CLI (GTK 4 + WebKitGTK).

- Run from this folder: `./run.sh` (rebuilds the UI automatically if you edited `ui/css` or `ui/js`)
- Install for yourself or friends: `./make-installer.sh` makes `claude-linux-installer.sh`; run it with `bash`.
- Tests: `tests/run_tests.sh` (headless, never touches your real chats/settings)
- Push an update to everyone who installed it: `python3 release.py 1.1.0 --notes "what changed"`, then upload `dist/`
  to the address in `claude_linux/update_url.txt`. Keep `~/.local/share/claude-linux-release/private.pem` safe.

Layout: `claude_linux/` (Python), `ui/css` + `ui/js` (built into `ui/index.html` by `build.py`), `tests/`.
