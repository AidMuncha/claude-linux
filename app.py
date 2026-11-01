#!/usr/bin/env python3
"""Claude Linux - a desktop window around the Claude Code CLI."""
import os

# WebKitGTK's DMA-BUF renderer freezes the page on many machines (NVIDIA drivers, some Ubuntu/Mint/X11 setups):
# it draws once and then never updates, so nothing seems clickable. These must be set before WebKit loads.
# CL_GPU=1 skips them for anyone who wants the fully accelerated path.
if os.environ.get("CL_GPU") != "1":
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    if os.path.exists("/proc/driver/nvidia/version"):      # proprietary NVIDIA driver: GPU compositing is the other usual culprit
        os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

from claude_linux.gtkapp import main  # noqa: E402

if __name__ == "__main__":
    main()
