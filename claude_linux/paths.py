"""Where things live. Every location can be redirected with an environment variable (used by the tests)."""
import os
import shutil

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
APP_ID = os.environ.get("CL_APP_ID", "dev.nein.ClaudeLinux")
DATA = os.environ.get("CL_DATA") or os.path.join(HOME, ".local/share/claude-linux")
CHATS = os.path.join(DATA, "chats.json")
CMDS = os.path.join(DATA, "cmds.json")
CHATDIR = os.path.join(DATA, "chats")
SETTINGS = os.path.join(DATA, "settings.json")
EXPORT_DIR = os.environ.get("CL_EXPORT_DIR") or os.path.join(HOME, "Downloads")
CLAUDE_DIR = os.environ.get("CL_CLAUDE_DIR") or os.path.join(HOME, ".claude")
CLAUDE_FILES = {"settings": os.path.join(CLAUDE_DIR, "settings.json"),
                "memory": os.path.join(CLAUDE_DIR, "CLAUDE.md")}
CLAUDE = os.environ.get("CL_CLAUDE") or shutil.which("claude") or os.path.join(HOME, ".local/bin/claude")
os.makedirs(DATA, exist_ok=True)
