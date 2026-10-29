#!/usr/bin/env python3
"""A stand-in for the `claude` CLI, so tests never need a login, the network, or tokens."""
import json
import os
import sys
import time

AUTH = os.environ.get("FAKE_AUTH")          # if set, "signed in" means this file exists (so tests can sign in and out)

a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
elif a[:2] == ["auth", "status"]:
    if AUTH and not os.path.exists(AUTH):
        print(json.dumps({"loggedIn": False}))
    else:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max", "email": "test@example.com"}))
elif a[:2] == ["auth", "login"]:
    print("Opening browser to sign in\u2026", flush=True)
    print("If the browser did not open, visit: https://claude.ai/oauth/authorize?code=true&client_id=fake&mode=" + (a[2] if len(a) > 2 else ""), flush=True)
    if os.environ.get("FAKE_LOGIN_FAIL"):
        print("Login failed: access denied", flush=True)
        sys.exit(1)
    if os.environ.get("FAKE_NEEDS_CODE"):
        sys.stdout.write("The browser can't return the sign-in to Claude Code automatically. After you sign in, paste the code shown.\nPaste code here > ")
        sys.stdout.flush()
        if sys.stdin.readline().strip() != "good-code-123":
            print("\nThat code is not from this sign-in.", flush=True)
            sys.exit(1)
    go = os.environ.get("FAKE_AUTH_GO")
    end = time.time() + 30
    while go and not os.path.exists(go) and time.time() < end:
        time.sleep(0.1)
    if AUTH:
        open(AUTH, "w").write("1")
    print("Login successful", flush=True)
elif a[:2] == ["mcp", "list"]:
    print("Checking MCP server health...\nfoo: npx -y foo - ✓ Connected")
elif "/usage" in a:
    print(json.dumps({"result": "Current session: 12% used · resets 5:59am (UTC)\nCurrent week (all models): 30% used · resets Oct 31, 9:00am (UTC)"}))
elif "stream-json" in a:
    def out(o):
        print(json.dumps(o), flush=True)
    out({"type": "system", "subtype": "init", "session_id": "sess-1", "model": "claude-test-1-0", "slash_commands": ["help", "compact", "context"], "skills": ["demo-skill"]})
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("type") != "user":
            continue
        c = msg["message"]["content"]
        text = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if b.get("type") == "text")
        if "/usage" == text.strip():
            continue
        if "slow" in text:
            time.sleep(7)
        reply = "Echo: " + text
        out({"type": "stream_event", "event": {"type": "message_start"}})
        out({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": reply}}})
        out({"type": "assistant", "uuid": "a-1", "message": {"content": [{"type": "text", "text": reply}]}})
        out({"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 5, "output_tokens": 7}, "total_cost_usd": 0.001})
else:
    sys.exit(2)
