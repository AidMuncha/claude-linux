"""Settings that Claude Linux itself stores (the CLI's own settings live in ~/.claude/settings.json)."""

DEFAULTS = {
    # session
    "model": "", "long": False, "effort": "", "mode": "acceptEdits", "fallback": "", "maxTurns": 0,
    "appendPrompt": "", "addDirs": [], "cwd": "", "rcName": "Claude Linux", "notify": True,
    # theme and colors
    "theme": "dark",            # a theme id, "system" (KDE colors), "auto" (light/dark follows KDE) or "custom"
    "autoDark": "dark", "autoLight": "light",
    "accent": "",               # "" keeps the theme's accent
    "kdeAccent": False,         # with the "system" theme: use Plasma's accent color
    "customTheme": {},          # {bg, side, card, fg, dim, accent, green, red, yellow}
    "projectColors": {},        # {folder: accent}
    # typography and layout
    "font": "", "monoFont": "", "fontSize": 15, "chatWidth": 800,
    # background and window
    "bgMode": "none",           # none | aurora | particles | gradient | image
    "bgGradient": "dusk", "bgImage": "", "bgDim": 0.55,
    "glass": False, "glassOpacity": 0.82,
    # motion
    "motion": "system",         # system | full | reduced
    "animSpeed": 1.0, "celebrate": "glow",   # glow | confetti | off
    # code blocks
    "syntax": "auto", "codeNums": False, "codeWrap": False,
    # desktop
    "tray": True, "closeToTray": False, "hotkey": False, "taskbar": True, "sidebar": True,
}
