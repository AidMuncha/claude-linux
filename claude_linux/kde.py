"""Reads the KDE Plasma color scheme and titlebar button layout, so the app can look native."""
import configparser
import os

CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
KDEGLOBALS = os.path.join(CONFIG, "kdeglobals")
KWINRC = os.path.join(CONFIG, "kwinrc")


def _parser(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # KDE keys are case-sensitive
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    return cp


def _hex(value):
    """'r,g,b' (0-255) -> '#rrggbb'; anything else -> None."""
    try:
        r, g, b = [int(x) for x in value.split(",")[:3]]
    except (AttributeError, ValueError):
        return None
    if not all(0 <= c <= 255 for c in (r, g, b)):
        return None
    return "#%02x%02x%02x" % (r, g, b)


def luminance(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def scheme(path=None):
    """The active color scheme as plain hex strings, or None when KDE's settings are missing or unreadable."""
    cp = _parser(path or KDEGLOBALS)
    if cp is None:
        return None

    def col(section, key):
        return _hex(cp.get(section, key, fallback=""))

    view, window = col("Colors:View", "BackgroundNormal"), col("Colors:Window", "BackgroundNormal")
    fg = col("Colors:View", "ForegroundNormal")
    if not (view and window and fg):
        return None
    return {
        "name": cp.get("General", "ColorScheme", fallback=""),
        "view": view,
        "window": window,
        "button": col("Colors:Button", "BackgroundNormal") or window,
        "fg": fg,
        "dim": col("Colors:View", "ForegroundInactive") or fg,
        "accent": _hex(cp.get("General", "AccentColor", fallback="")) or col("Colors:Selection", "BackgroundNormal"),
        "green": col("Colors:View", "ForegroundPositive"),
        "red": col("Colors:View", "ForegroundNegative"),
        "yellow": col("Colors:View", "ForegroundNeutral"),
        "dark": luminance(view) < 0.5,
    }


_BUTTONS = {"I": "minimize", "A": "maximize", "X": "close"}


def window_buttons(path=None):
    """GTK 'decoration-layout' matching the titlebar buttons the user chose in KDE (left:right)."""
    cp = _parser(path or KWINRC)
    sec = "org.kde.kdecoration2"
    left = cp.get(sec, "ButtonsOnLeft", fallback="MS") if cp else "MS"
    right = cp.get(sec, "ButtonsOnRight", fallback="HIAX") if cp else "HIAX"

    def conv(s):
        return ",".join(_BUTTONS[c] for c in s if c in _BUTTONS)
    return conv(left) + ":" + conv(right)
