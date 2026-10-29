#!/usr/bin/env bash
# Runs the tests.
#   ./run_tests.sh                              everything
#   ./run_tests.sh test_ui_features.Themes      just some (any `unittest` arguments)
#
# The UI tests need a real, rendering window, so they run inside `cage` (a tiny headless Wayland
# compositor) on a private D-Bus session: nothing appears on your screen, your tray, notifications
# and shortcuts are never touched, and your chats/settings are never read (see tests/env.py).
set -u
cd "$(dirname "$0")"
if [ $# -eq 0 ]; then set -- discover -p 'test_*.py'; fi
export GTK_A11Y=none CL_DATA="$(mktemp -d)" CL_CLAUDE_DIR="$(mktemp -d)" CL_PRESENT=1 CL_APP_ID=dev.nein.ClaudeLinuxTest
cleanup() { [ -n "${PGID:-}" ] && kill -- -"$PGID" 2>/dev/null; rm -rf "$CL_DATA" "$CL_CLAUDE_DIR"; }
trap cleanup EXIT INT TERM
if command -v cage >/dev/null && command -v dbus-run-session >/dev/null; then
  # own session/process group, so everything started below is stopped when this script ends
  setsid dbus-run-session --config-file="$PWD/session.conf" -- env WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 \
    WLR_RENDERER=pixman GSK_RENDERER=cairo cage -s -- python3 -W ignore -m unittest "$@" 2>&1 &
  PGID=$!
  wait "$PGID"
  rc=$?
else
  echo "cage and dbus-run-session are needed for the full test suite; running without them (some tests will fail)" >&2
  python3 -W ignore -m unittest "$@"
  rc=$?
fi
exit $rc
