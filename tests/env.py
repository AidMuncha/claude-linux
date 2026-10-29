"""Import this first in every test module: points the app at throw-away folders and a fake `claude`,
so no test can ever read or change your real chats, settings or ~/.claude."""
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_tmp = tempfile.mkdtemp(prefix="claude-linux-test-")
for key, sub in (("CL_DATA", "data"), ("CL_CLAUDE_DIR", "claude"), ("CL_EXPORT_DIR", "exports")):
    os.environ.setdefault(key, os.path.join(_tmp, sub))
os.environ["CL_CLAUDE"] = os.path.join(HERE, "fake_claude.py")
os.environ.setdefault("CL_APP_ID", "dev.nein.ClaudeLinuxTest")
real = os.path.expanduser("~")
for key in ("CL_DATA", "CL_CLAUDE_DIR", "CL_EXPORT_DIR"):
    p = os.path.realpath(os.environ[key])
    assert not p.startswith(os.path.join(real, ".local/share/claude-linux")) and p != os.path.join(real, ".claude") and p != os.path.join(real, "Downloads"), \
        "refusing to run tests against real data: %s=%s" % (key, p)
