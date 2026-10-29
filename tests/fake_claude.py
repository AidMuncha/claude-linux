#!/usr/bin/env python3
"""A stand-in for the `claude` CLI, so tests never need a login, the network, or tokens."""
import json
import sys
import time

a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
elif a[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max", "email": "test@example.com"}))
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
