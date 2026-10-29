"""Small helpers: JSON files, the CLI's /usage text, and the chat store."""
import json
import os
import re
import time
from datetime import datetime, timedelta

from .paths import CHATDIR, CHATS


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def parse_when(text, tz):
    """'Oct 28, 5:59am' + tz name -> epoch of the real reset (the CLI prints it one minute early)."""
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo(tz)
    except Exception:
        z = None
    now = datetime.now(z)
    m = re.match(r"(?:([A-Za-z]{3})\w*\s+(\d{1,2}),?\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text.strip(), re.I)
    if not m:
        return None
    mon, day, hh, mm, ap = m.groups()
    hh = int(hh) % 12 + (12 if ap.lower() == "pm" else 0)
    mm = int(mm or 0)
    try:
        if mon:
            d = datetime.strptime(f"{now.year} {mon} {day}", "%Y %b %d").replace(hour=hh, minute=mm, tzinfo=z)
            if d < now - timedelta(days=2):
                d = d.replace(year=now.year + 1)
        else:
            d = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if d < now - timedelta(hours=1):
                d += timedelta(days=1)
    except Exception:
        return None
    if mm == 59:
        d += timedelta(minutes=1)
    return int(d.timestamp())


def parse_usage(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"Current (.+?):\s*(\d+)% used\s*·\s*resets (.+?)\s*\(([^)]+)\)\s*$", line.strip())
        if m:
            label, pct, when, tz = m.groups()
            rows.append({"label": label, "pct": int(pct), "resetsAt": parse_when(when, tz), "raw": f"{when} ({tz})"})
    return {"rows": rows, "text": text.strip(), "ts": time.time()}


def load_chats():
    """One JSON file per chat in CHATDIR; migrates the old single chats.json once."""
    os.makedirs(CHATDIR, exist_ok=True)
    if os.path.exists(CHATS):
        for k, v in read_json(CHATS, {}).items():
            if v.get("items"):
                write_json(os.path.join(CHATDIR, os.path.basename(k) + ".json"), v)
        os.replace(CHATS, CHATS + ".migrated")
    out = {}
    for f in os.listdir(CHATDIR):
        if f.endswith(".json"):
            v = read_json(os.path.join(CHATDIR, f), None)
            if v and v.get("items"):
                out[f[:-5]] = v
    return out
