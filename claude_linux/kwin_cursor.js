// One-shot: tells Claude Linux where the pointer is right now (global logical pixels).
callDBus("dev.nein.ClaudeLinux.Jarvis", "/jarvis", "dev.nein.ClaudeLinux.Jarvis", "Event", "cursor", String(workspace.cursorPos.x), String(workspace.cursorPos.y), "");
