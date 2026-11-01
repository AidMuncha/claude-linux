"""Jarvis: a voice (or text) assistant that runs on your Claude subscription and can use your computer.

Ears:   jarvis_stt.py (faster-whisper, offline) in its own virtualenv, fed by the microphone through `parecord`.
Voice:  Piper with the community "Jarvis" voice (espeak-ng if that cannot be downloaded), played with `paplay`.
Brain:  its own `claude` process, always Sonnet at low effort, with Bash so it can click, type, open apps and look at
        the screen. Nothing here touches the normal chats or their settings.
Everything the page needs arrives as one message type, "jarvis", with an `ev` field (state, say, heard, level, ...).
The first start downloads the speech model, the voice and a small Python environment into ~/.local/share/claude-linux/jarvis.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import wave
import base64

from .paths import CLAUDE, DATA, HERE, HOME
from .screenshare import FPS, ScreenShare
from .activity import Activity
from .ctl import Ctl
from .pointer import Pointer
from .screenread import ScreenReader, monitors, to_screen, to_view, view
from .voice import Voice, PIPER, VOICE
from gi.repository import GLib

from . import gamemic, images, launcher
from .gameinput import GameInput

JDIR = os.path.join(DATA, "jarvis")
VENV = os.path.join(JDIR, "venv")
PY = os.path.join(VENV, "bin", "python")
MODELS = os.path.join(JDIR, "models")
PIPER_ROOT = os.path.join(JDIR, "piper-bin")
VOICE_DIR = os.path.join(JDIR, "voice")
STT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_stt.py")
WHISPER = "distil-small.en"          # about as accurate as small.en for English and several times faster
PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
VOICE_URL = "https://huggingface.co/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/medium/jarvis-medium.onnx"
SHOTS = os.path.join(tempfile.gettempdir(), "jarvis-shots")
CTL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_ctl.py")
CTL_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), "jarvis-ctl.sock")
YDOTOOL_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", ".jarvis_ydotool_socket")

STOP_WORDS = re.compile(r"^\W*(?:jarvis\W+)?(?:stop|cancel|abort|never\s?mind|be quiet|quiet|enough|shut up)\W*$", re.I)
POWER_DOWN = re.compile(r"^\W*(?:jarvis\W+)?(?:(?:stand|power|shut)\s?down|deactivate|goodbye|good bye|that'?s all|go to sleep)\W*(?:jarvis)?\W*$", re.I)
SHARE_ON = re.compile(r"\b(?:watch (?:this|it|that|the \w+|a \w+)?\s*with me|share (?:my|the) screen|screen ?share|start (?:watching|sharing)|(?:look at|watch) my screen)\b", re.I)
SHARE_OFF = re.compile(r"\b(?:stop|end|quit) (?:watching|sharing|the screen ?share|the stream)\b", re.I)
TICK = ("(Automatic watch check: the user did not speak.) Look at the latest frames and what was said recently. If there is something genuinely worth a short comment "
        "or heads-up (a danger, a mistake, an error, a kill, something that just happened or is about to), say it in ONE short sentence, ten words or fewer, like a teammate calling it out. "
        "Never repeat or rephrase something you already said in this conversation: if your point was already made, it is NOTHING. "
        "If not, reply with exactly the word NOTHING and nothing else.")
CTX_LIMIT = 90000                     # past this many tokens of context every reply gets slower: start a fresh session with a short recap
CUT = re.compile(r"(?<=[.!?])[\"')\]]*\s+|\n+")

PROMPT = """You are JARVIS, the user's personal AI assistant, in the spirit of the one from the Iron Man films: calm, dry, quietly witty, extremely capable. You run on the user's own Linux computer ({desktop}) and you can operate it. The user speaks to you (or types) and everything you write is READ ALOUD by a text-to-speech voice and shown on screen, so:
- Be brief. Reply in short, natural spoken sentences of about eight words each. One sentence, two at most, unless the user asks for detail. No markdown, no lists, no headings, no code blocks, no emoji, no URLs, no file paths read out letter by letter.
- Do not announce or describe your actions, and never read back what you did or which tools you used. For a task that is just something to do (open, click, type, play, search, move, launch, close), do it silently and when finished say only "Completed." (or "Done."), nothing more. Only speak more when the user asked a question, you must report something they need to know (a result, an error, something you found), or you need an answer from them. Then use the fewest words possible: one short sentence, never a summary of the steps.
- Address the user as "sir" now and then, not in every sentence. Stay in character but never let the character get in the way of being useful.
- You have the Bash tool and the rest of Claude Code's tools. Use them to do whatever is asked: open apps, move or click the mouse, type, press keys, read the screen, manage files, run commands, search the web, analyze things.
- Ask before anything destructive, irreversible, expensive, or that sends something to other people (deleting, purchases, posting, emailing). Ask aloud in one short question and wait for the answer in the next message.
- Pictures of the screen (from `look`) are saved in {shots}: Read them, then delete the files right away (rm). Never leave them lying around.
- Every message starts with a short note on what the user is doing on the PC (the window in front, recent switches, tab or page title changes, windows opening and closing, what else is open). Treat it as what you can see happening, and mention changes naturally when they matter. Do not recite it.
- If you are not sure what was said (speech recognition makes mistakes), pick the most likely meaning for harmless requests, otherwise ask.
- You are watching the user's screen live, like a stream: their messages arrive with the latest frames of it (a fraction of a second to a few seconds old, a few per second) and automatic captions of the computer's audio when there are any. Use them directly, and speak about what you see as it happens. You see stills close together, not smooth video, and the captions can be wrong.
Computer control on this machine:
{hints}
Keep going until the request is done. If something fails, try another approach before giving up, and tell the user plainly what happened."""


def which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def control_hints():
    """What this computer offers for mouse, keyboard, windows and screenshots; told to Jarvis so he does not have to guess."""
    h = [screen_facts()]
    c = "python3 -I " + CTL
    h.append("- FAST HANDS AND EYES (use these first): the tools mcp__jarvis__click_text, mcp__jarvis__click, mcp__jarvis__move, mcp__jarvis__scroll, mcp__jarvis__drag and mcp__jarvis__look. Each acts like a human hand and RETURNS THE LIVE SCREEN "
             "right afterwards as a picture, so you see the result in the same step: no separate screenshot, no Read, no waiting. Work in quick succession: act, look at the returned picture, act again. "
             "Do not announce every step; one short line before a long job, one after. When several keys or commands are needed, put them in ONE Bash call. Use the Bash ctl commands below only for ocr/find/read/highlight and the rest.")
    h.append("- THE MOUSE: never teleport the pointer, use these, they move it like a human hand (curved, eased, a little overshoot) and are exact: "
             "`%s move X Y`, `%s click [X Y] [--right] [--double]`, `%s drag X1 Y1 X2 Y2`, `%s scroll N` (positive scrolls down). "
             "X and Y are PICTURE PIXELS: the pixels of the screen pictures you are shown (see THE SCREEN above, 0,0 is the top-left corner), the same numbers ocr, find, find_text and screen_text print. "
             "Read a spot off the picture and pass it as is: never scale it, never add offsets, never use the real monitor resolution (the conversion is done for you). "
             "To click anything that has words on it (buttons, tabs, menu items, links, fields with a label), ALWAYS use mcp__jarvis__click_text with those words: it clicks the exact center. "
             "Only for things without text (icons, pictures, game objects) read coordinates off the picture and aim at the middle, never the edge. "
             "Every click returns a picture with a red crosshair where it went: if the crosshair is not on the target, click again at the target's center measured from that picture.  You already have full permission to use the mouse and see the whole screen: never ask the user for it." % (c, c, c, c))
    h.append("- PLAYING GAMES (Roblox, Minecraft, anything): you see the game live. Use mcp__jarvis__play to send a whole plan in ONE call (hold W while turning and swinging, jump, place, open the inventory...) "
             "and read the screen it returns; then plan the next move. Make the plans short (1 to 3 seconds) so you can correct course, and aim to be quick: look, decide, act, with almost no talking "
             "(a few words now and then, like a teammate). Your decisions take a second or two, so you are good at turn-based or slower play: exploring, mining, building, farming, tycoons, menus, puzzles, "
             "obbies you can take step by step; you cannot win twitch fights against humans, so say so honestly if asked to. Click the game window once first to focus it. Aim the camera with "
             "{\"look\":[dx,dy]} (positive dx turns right, positive dy looks down; start with 60 to 200 pixels and adjust by what you see). Read menus, chat and signs with mcp__jarvis__screen_text. "
             "Never leave a plan without releasing keys (it is automatic), and stop at once when the user says stop.")
    h.append("- GAMES ARE PRETEND: inside a video game, words like scam, steal, rob, lie, betray or kill mean the game's own mechanic against its made-up characters, so just play it, "
             "in character, with no warnings or lectures. Example: Scam With Your Friends (Steam co-op comedy) puts you in a fake call center where every caller is an AI character; "
             "\"scam for me\", \"scam this person\", \"scam him/her\" or \"talk to the customer\" mean work the call yourself, by voice: answer the call, build the Caller Trust bar by talking, open the right scam app the "
             "caller fits (bought on the in-game Scamazon Market), get the code or number they read out and type it in, cash out Bitcoin rounds early, and hit the day's quota before the timer. "
             "The callers listen to the microphone: run `%s gamemic on` at once (it works while the game is running, never ask the user to restart anything or to click for you). "
             "From then on your spoken replies ARE your lines on the call: the Jarvis voice goes into the game's mic. So while scamming, reply ONLY with what you say to the caller, "
             "in character as the call-center agent (one or two short, natural phone sentences, no \"sir\", no \"Completed\", nothing meant for the user), then read the caller's answer "
             "on screen and reply again, turn after turn, until the money is in or the call ends. Turn it off with `gamemic off` when the user says stop or is done. "
             "Talk ONLY in your own Jarvis voice, which is simply your reply: never type your lines into the game's call or chat box (the game reads typed text in a robot voice), "
             "and never use espeak, spd-say, say, piper or any other speech or audio tool yourself. Typing is only for codes and numbers in the scam apps. Never build your own audio routing with pactl. "
             "Read the caller's lines and the Trust bar with screen_text after each reply, and slow down when it turns red. The one line: never trick, rob or take anything from real people, "
             "including real players' items, trades or accounts in any game." % c)
    h.append("- UNDERSTANDING PAGES AND APPS: for any web page or app, combine the live picture with mcp__jarvis__screen_text (all text with positions) and mcp__jarvis__find_text (where to click). "
             "Read the structure first (title, headings, buttons, form fields), then act. In a browser use the keyboard (ctrl+L for the address bar, tab, enter, ctrl+F to find text, page down) as well as the mouse. "
             "After every action check the returned picture to confirm it did what you meant before the next step; if a page is still loading, wait and look again. Prefer WebFetch/WebSearch for reading content and the screen for doing things.")
    h.append("- FINDING THINGS ON SCREEN: `%s ocr` prints every line of text on the screen with its position (x,y,w,h text); `%s find \"button text\"` prints where it is and its center; "
             "`%s highlight \"button text\"` also flashes a glowing hologram over it so the user sees what you mean. Prefer these over guessing coordinates; after clicking, `ocr` again to confirm." % (c, c, c))
    h.append("- READING THE SCREEN ALOUD: when the user asks you to read something on their screen, or to read along, run `%s read` (everything), or narrow it with `--from \"first words\" --to \"last words\"` "
             "or `--region X,Y,W,H`; run `ocr` first if you need to see what is where. It speaks the text itself with a glowing blue hologram that follows each word over the real text on their screen, "
             "then turns green and fades. Do not repeat the text yourself afterwards. For summaries or explanations just talk, no hologram." % c)
    h.append("- STEAM GAMES: Steam is installed and running. `%s games [name]` lists the installed games with their ids; `%s game \"name\"` launches one (fuzzy name match, start it as soon as asked, "
             "say you are launching it, do not wait for it to load). Never use `steam -applaunch`. If a game is not installed, say so and offer to open its store page (`steam steam://store/APPID`, "
             "find the id by searching the web). Other launchers: `lutris` is installed." % (c, c))
    h.append("- PICTURES: `%s img web \"query\" [-n 8] [--download] [--show]` finds pictures online (titles, sizes, image and page addresses; --download saves them so you can Read them, --show opens the search in the browser); "
             "`%s img lens FILE_OR_URL \"a few words on what it shows\"` is the first choice for finding where a picture comes from or what it shows: it runs Google Lens in a hidden browser (nothing appears on screen) and returns what Lens found, and if Google refuses it falls back to your own matching by itself;"
             "`%s img match FILE_OR_URL \"what it shows\"` finds that picture or look-alikes on the web with your own matching (no outside image-search site): look at the picture, describe it in a few words, and it searches those words, compares every candidate with the picture and ranks them; try a second description if nothing scores well; "
             "`%s img onscreen FILE` finds where a given picture, icon or logo is on the screen and prints its center (then move/click as usual, or highlight it); "
             "`%s img like FILE [DIR]` ranks picture files in a folder (default Pictures) by how much they look like FILE; "
             "`%s img sheet FILE_OR_DIR...` makes a numbered contact sheet you can Read to pick pictures by what they show (describe-and-find). Delete every file you download or generate with rm when done." % (c, c, c, c, c, c))
    h.append("- ANY APP: `%s apps [name]` lists installed apps; `%s launch \"name\"` starts one (Firefox, Discord, a file manager...). For a file or website use `xdg-open`." % (c, c))
    h.append("- LOOKING THINGS UP: you have WebSearch and WebFetch. Use them whenever the user asks you to look something up, wants current facts (news, prices, scores, weather, release dates, how-tos, game info), "
             "or you are not sure. Search, read what matters, then answer in a few spoken sentences with the key facts; name the source in a few words if it matters, never read out URLs. "
             "Offer to open the page on screen if it would help.")
    h.append("- FILES: you may read, create, edit and organize files anywhere the user can (home is ~ with Documents, Downloads, Desktop, Pictures). When asked to make a file (notes, a script, a document, a list...), "
             "write it with the Write tool or Bash, pick a sensible name and put it in Documents unless they say where, then say what and where in plain words (\"saved as shopping list in Documents\"). "
             "Look before you change: ask first before overwriting an existing file or deleting anything. Summarize big files instead of reading them out.")
    h.append("- General rule: if the user asks for it and it is not harmful, do it, with whatever combination of tools it takes; do not say you cannot until you have actually tried.")
    if which("ydotool"):
        h.append("- Typing and key presses (Wayland): `ydotool type 'text'`, `ydotool key 29:1 46:1 46:0 29:0` by Linux key code (29 ctrl, 42 shift, 56 alt, 125 super, 28 enter, 15 tab, 1 esc). "
                 "Its daemon is running and YDOTOOL_SOCKET is set. Click into the right field with the mouse commands first.")
    else:
        h.append("- ydotool is not installed, so typing into Wayland apps is limited; xdotool only reaches XWayland windows.")
    if which("xdotool"):
        h.append("- `xdotool` works only on XWayland (X11) windows.")
    h.append("- YOU SEE THE SCREEN LIVE, as if the user were screen sharing with you: the pictures attached to each message are the latest moments of the screen, the last one only a fraction of a second old, "
             "so you see what they see as they talk. Look at them instead of taking screenshots. While you are working (after clicking, typing, opening something) run `mcp__jarvis__look` (or `%s look` for files) to see the screen as it is now "
             "(`look 5` for more moments), Read the files it prints, then rm them. If a message has no pictures attached the live view is off: `look` then gives you a single fresh screenshot instead." % c)
    if which("kscreen-doctor"):
        h.append("- Real monitor layout: `kscreen-doctor -o` (information only: the mouse and every position you are given use picture pixels, not these).")
    h.append("- Open an app: `gtk-launch <desktop-id>` or `nohup setsid <command> >/dev/null 2>&1 &` (find desktop ids in /usr/share/applications and ~/.local/share/applications; flatpaks are in /var/lib/flatpak/exports/share/applications). Open a file or URL: `xdg-open`.")
    if which("qdbus", "qdbus6"):
        h.append("- KDE: `qdbus` talks to KWin and Plasma; `kioclient exec` opens things. Clipboard: `wl-copy` / `wl-paste`.")
    h.append("- Volume: `wpctl` or `pactl`. Notifications: `notify-send`.")
    return "\n".join(h)


def screen_facts():
    """The real monitor layout and how the pictures he sees map onto it, so he never has to guess the screen size."""
    ms = monitors() or [(0, 0, 1920, 1080)]
    gx, gy, k, pw, ph = view((ms[0][0], ms[0][1]))
    mons = "; ".join("%dx%d at %d,%d" % (w, h, x, y) for x, y, w, h in ms)
    return ("- THE SCREEN: %d monitor%s (%s, logical pixels). Every screen picture you get is %dx%d, the whole monitor, undistorted: one picture pixel is %.2f "
            "screen pixels. The mouse pointer is drawn in the pictures, so you can see where it really is. Coordinates you pass are picture pixels (0,0 to %d,%d)."
            % (len(ms), "" if len(ms) == 1 else "s", mons, pw, ph, k, pw - 1, ph - 1))


def clean_for_speech(text):
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "that link", t)
    t = re.sub(r"(?m)^\s*(?:[-*+•]|\d+[.)])\s+", "", t)
    t = re.sub(r"(?m)^\s*#+\s*", "", t)
    t = re.sub(r"[*_`~|>]+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def fetch(url, dest, progress=None):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "claude-linux-jarvis"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    os.replace(tmp, dest)


class Jarvis:
    def __init__(self, push, too_risky):
        self.push, self.too_risky = push, too_risky
        self.mode = None                        # None (off) | "voice" | "text"
        self.lock = threading.RLock()
        self.gen = 0                            # bumps on every interruption; older speech is dropped
        self.proc = None                        # the claude process
        self.stt = None                         # the ears
        self.ears_ready = False
        self.voice_on = True                    # speak out loud (text mode can turn this off)
        self.cfg = lambda key, default=None: default          # replaced by the app with the user's Settings > Jarvis
        self.user_muted = False
        self.speech_t0 = 0.0                         # when the current utterance began, to line the frames up with what you said
        self.turn = False                       # Claude is working on a request
        self.pending = 0                        # sentences waiting to be turned into audio
        self.speaking = False
        self.buf = ""
        self.streamed = False
        self.interrupted = False                # set by a stop; silences what the CLI still sends for the abandoned request
        self.say_q = queue.Queue()
        self.voice = Voice()                    # Piper stays loaded, audio streams into one open player (voice.py)
        self.spoke_turn = False
        self.ctl = Ctl(CTL_SOCKET, self._dispatch)
        self.screen = ScreenReader(self)        # OCR + the hologram over text on the real screen (screenread.py)
        self.state = "off"
        self.workers = False
        self.ydotoold = None
        self.setup_lock = threading.Lock()
        self.session = 0
        self.share, self.sharing, self.watch, self.auto_share = None, False, False, False    # screen share (see screenshare.py) and automatic commentary
        self.caps, self.cap_stt, self.cap_ready = [], None, False    # captions of what the computer is playing: [(time, text)]
        self.last_addr, self.last_tick, self.tick_turn, self.tick_text = 0.0, 0.0, False, ""
        self.activity = Activity()                                   # window and tab tracking (see activity.py)
        self.seen_activity = 0
        # he starts thinking when you pause, but says and does nothing until you have really stopped (see _on_pause)
        self.spec, self.hold, self.held = None, False, []        # the request being worked on early; whether output is being held back; what was held
        self.spec_gen, self.spec_token, self.spec_timer = 0, 0, None
        self.confirm, self.cancel_done, self.cancelling = threading.Event(), threading.Event(), False
        self.cancel_t, self.spec_dropped = 0.0, False            # when a request was abandoned; whether the next one replaces a cut-off one
        self.ctx, self.recap, self.said = 0, "", []               # context size of the session, a recap for a fresh one, recent lines [(who, text)]
        self.pointer = Pointer(self.activity.cursor_pos)
        self.game = GameInput(self.pointer, dict(os.environ, YDOTOOL_SOCKET=YDOTOOL_SOCKET))     # batched keys and mouse for games (gameinput.py)
        self.brain = None             # the mouse, moved like a hand (pointer.py)

    # ---------- messages from the page ----------
    def handle(self, m):
        fn = getattr(self, "h_" + str(m.get("type", ""))[7:], None)
        if fn:
            fn(m)

    def emit(self, ev, **kw):
        self.push("jarvis", dict(kw, ev=ev))

    def set_state(self, state, label=""):
        self.state = state
        self.emit("state", state=state, label=label, mode=self.mode, muted=self.user_muted, voice=self.voice_on)

    def h_start(self, m):
        keep = m.get("mode") not in ("text", "voice")           # "keep": start in voice mode if off, otherwise leave the running mode alone
        mode = "text" if m.get("mode") == "text" else "voice"
        with self.lock:
            if self.mode and keep:
                return
            if self.mode and self.mode != mode:
                self.mode = mode
                if mode == "text":
                    self._stop_ears()
                self.set_state(self.state if self.state != "off" else "waiting")
                if mode == "voice":
                    threading.Thread(target=self._start_ears, args=(self.session,), daemon=True).start()
                return
            if self.mode:
                return
            self.mode, self.session = mode, self.session + 1
            self.user_muted, self.voice_on = False, True
        self.set_state("waiting")
        threading.Thread(target=self._boot, args=(self.session,), daemon=True).start()

    def h_stop(self, m):
        self.stop()

    def h_interrupt(self, m):
        self.interrupt()

    def h_text(self, m):
        text = (m.get("text") or "").strip()
        if text and self.mode:
            self.emit("heard", text=text, typed=True)
            self._note("User", text)
            if not self._command(text):
                self._input(text)

    def h_mute(self, m):
        self.user_muted = bool(m.get("on"))
        self._sync_mic()
        busy = self.speaking or self.turn or self.pending > 0
        self.set_state(self.state if busy else self._rest_state())

    def h_share(self, m):
        if m.get("on", True):
            self.start_share(bool(m.get("watch")))
        else:
            self.stop_share()

    def h_watch(self, m):
        self.watch = bool(m.get("on")) and self.sharing
        self.last_tick = time.time()
        self._emit_share()

    def h_voice(self, m):
        self.voice_on = bool(m.get("on"))
        if not self.voice_on:
            self.interrupt(keep_turn=True)
        self.set_state(self.state)

    # ---------- start / stop ----------
    def _boot(self, session):
        """Gets everything ready, then greets. The very first run downloads the voice and the speech model."""
        try:
            self._start_workers()
            self._clean_shots(all_files=True)
            self.activity.start()
            self.start_share(auto=True)             # he sees the screen live from the start, as if you were sharing it with him
            self._ensure_voice()
            threading.Thread(target=self.voice.warm, daemon=True).start()    # load the voice now so the first sentence is instant
            self._ydotoold()
            threading.Thread(target=self._ydotoold_watch, args=(session,), daemon=True).start()
            try:
                self.ctl.start()
            except OSError as e:
                self.emit("error", text="Mouse and screen reading are unavailable (%s)" % e)
        except Exception as e:
            self.emit("error", text="Jarvis could not start: %s" % e)
        if not self.mode or session != self.session:
            return
        self.set_state(self._rest_state())
        self._say("Jarvis Mode Activated")
        threading.Thread(target=self._prewarm_claude, daemon=True).start()
        if self.mode == "voice":
            self._start_ears(session)          # the first run installs the speech recognizer here, which takes a while

    def _prewarm_claude(self):
        """Starts the claude process now, so the first request does not wait for it to boot."""
        try:
            self._claude()
        except Exception:
            pass

    def _rest_state(self):
        if self.mode == "voice":
            if not self.ears_ready:
                return "waiting"
            return "muted" if self.user_muted else "listening"
        return "idle"

    def stop(self):
        with self.lock:
            if not self.mode:
                return
            self.mode = None
            self.session += 1
        self.interrupt()
        self.stop_share()
        self.ctl.stop()
        self.screen.close()
        self.pointer.close()
        self.voice.close()
        self.activity.stop()
        self._clean_shots(all_files=True)
        self._stop_ears()
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
        yd, self.ydotoold = self.ydotoold, None
        if yd and yd.poll() is None:
            yd.terminate()
        if gamemic.modules():
            gamemic.off(self.voice)
        self.turn = False
        self.set_state("off")

    def _stop_ears(self):
        s, self.stt = self.stt, None
        self.ears_ready = False
        if s and s.poll() is None:
            try:
                s.stdin.write("quit\n")
                s.stdin.flush()
            except Exception:
                pass
            try:
                s.terminate()
            except Exception:
                pass

    # ---------- first-run downloads ----------
    def _progress(self, text):
        self.emit("setup", text=text)

    def _ensure_voice(self):
        if os.path.isfile(PIPER) and os.path.isfile(VOICE):
            return
        with self.setup_lock:
            try:
                if not os.path.isfile(PIPER):
                    self._progress("Downloading Jarvis' voice engine (first run only)…")
                    tgz = os.path.join(JDIR, "piper.tar.gz")
                    fetch(PIPER_URL, tgz)
                    shutil.rmtree(PIPER_ROOT, ignore_errors=True)
                    os.makedirs(PIPER_ROOT)
                    with tarfile.open(tgz, "r:gz") as t:
                        t.extractall(PIPER_ROOT, filter="data")
                    os.remove(tgz)
                if not os.path.isfile(VOICE):
                    fetch(VOICE_URL + ".json", VOICE + ".json")
                    fetch(VOICE_URL, VOICE, lambda f: self._progress("Downloading Jarvis' voice… %d%%" % int(f * 100)))
            except Exception as e:
                self.emit("error", text="Could not download Jarvis' voice (%s). Using the basic system voice instead." % e)
            finally:
                self._progress("")

    def _ensure_ears(self):
        """A private Python environment with faster-whisper, and the speech model. Returns True when ready."""
        marker = os.path.join(JDIR, "ears-%s.ok" % WHISPER)
        if os.path.isfile(marker) and os.path.isfile(PY):
            return True
        with self.setup_lock:
            if os.path.isfile(marker) and os.path.isfile(PY):
                return True
            try:
                if not os.path.isfile(PY):
                    self._progress("Setting up Jarvis' hearing (first run only)…")
                    subprocess.run([sys.executable, "-m", "venv", VENV], check=True, capture_output=True, text=True)
                self._progress("Installing the speech recognizer (a few minutes, first run only)…")
                r = subprocess.run([PY, "-m", "pip", "install", "--quiet", "faster-whisper"], capture_output=True, text=True)
                if r.returncode:
                    raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "pip failed")
                self._progress("Downloading the speech model (about 330 MB, first run only)…")
                r = subprocess.run([PY, "-c", "import sys; from faster_whisper.utils import download_model; download_model(sys.argv[1], cache_dir=sys.argv[2])", WHISPER, MODELS],
                                   capture_output=True, text=True)
                if r.returncode:
                    raise RuntimeError((r.stderr or "download failed").strip().splitlines()[-1])
                open(marker, "w").close()
                return True
            except Exception as e:
                self.emit("error", text="Could not set up hearing: %s. Use /jarvistextmode until that is fixed." % e)
                return False
            finally:
                self._progress("")

    # ---------- the ears ----------
    def _start_ears(self, session):
        if not self._ensure_ears() or session != self.session or self.mode != "voice":
            return
        self._progress("Loading the speech model…")
        self.stt = proc = subprocess.Popen([PY, "-I", STT_SCRIPT, WHISPER, MODELS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._ears_reader, args=(proc, session), daemon=True).start()

    def _ears_reader(self, proc, session):
        try:
            for line in proc.stdout:
                if session != self.session or self.stt is not proc:
                    break
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                kind = ev.get("ev")
                if kind == "ready":
                    self.ears_ready = True
                    self._progress("")
                    self._sync_mic()
                    if not self.turn and not self.speaking:
                        self.set_state(self._rest_state())
                elif kind == "level":
                    self.emit("level", v=ev.get("v", 0))
                elif kind == "hearing":
                    if not self.speech_t0 or time.time() - self.speech_t0 > 30:
                        self.speech_t0 = time.time()        # the screen at this moment is what you were looking at as you began
                    if not self.turn and not self.speaking:
                        self.set_state("hearing")
                elif kind == "nothing":
                    if not self.turn and not self.speaking:
                        self.set_state(self._rest_state())
                elif kind == "partial":
                    self.emit("partial", text=ev.get("text", ""))
                elif kind == "pause":
                    self._on_pause(ev.get("text", ""))
                elif kind == "resume":
                    self._on_resume()
                elif kind == "text":
                    self._heard(ev.get("text", ""))
                elif kind == "error":
                    self.emit("error", text=ev.get("text", "Speech recognition failed"))
            err = proc.stderr.read().strip()
            if self.stt is proc and session == self.session and self.mode == "voice":
                self.ears_ready = False
                self.emit("error", text="Jarvis' hearing stopped. %s" % (err.splitlines()[-1] if err else ""))
                self.set_state("waiting")
        except Exception as e:
            self.emit("error", text=str(e))

    def _sync_mic(self):
        c = self.cap_stt
        if c and self.cap_ready and c.poll() is None:
            try:
                c.stdin.write("mute\n" if (self.speaking or self.pending > 0) else "unmute\n")
                c.stdin.flush()
            except Exception:
                pass
        s = self.stt
        if not s or s.poll() is not None or not self.ears_ready:
            return
        mute = self.speaking or self.pending > 0 or self.user_muted
        try:
            s.stdin.write("mute\n" if mute else "unmute\n")
            s.stdin.flush()
        except Exception:
            pass

    def _awake(self, text):
        """True when he should react to this: the activation word is off, it was said, a follow-up is still open, or it is a stop/power/share command."""
        if not self.cfg("jarvisWake", False) or STOP_WORDS.match(text) or POWER_DOWN.match(text) or SHARE_OFF.search(text) or SHARE_ON.search(text):
            return True
        if time.time() - self.last_addr <= 25:
            return True
        low = " ".join(re.findall(r"[\w']+", text.lower()))
        words = [" ".join(re.findall(r"[\w']+", w.lower())) for w in str(self.cfg("jarvisWord", "jarvis") or "jarvis").split(",")]
        return any(w and re.search(r"\b%s\b" % re.escape(w), low) for w in words)

    def _heard(self, text):
        text = text.strip()
        if not text:
            return
        if not self._awake(text):
            return                          # not addressed to him (the activation word in Settings > Jarvis)
        self.emit("heard", text=text)
        self._note("User", text)
        self.spec_token += 1
        if POWER_DOWN.match(text):
            self._cancel_spec()
            self._say("Powering down. Call me when you need me.")
            threading.Thread(target=self._power_down_later, args=(self.session,), daemon=True).start()
            return
        if STOP_WORDS.match(text):
            self.interrupt()
            return
        if self._command(text):
            self._cancel_spec()
            return
        if self.spec and self._same(text, self.spec["text"]):
            self._confirm_spec()                    # the early request was for exactly this: its answer is released now
            return
        self._cancel_spec()
        self._input(text)

    @staticmethod
    def _same(a, b):
        import difflib
        norm = lambda t: " ".join(re.findall(r"\w+", t.lower()))
        return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= 0.9

    # ---------- thinking while you talk ----------
    def _on_pause(self, text):
        """You went quiet for a moment. Start working on what you have said so far, but hold back everything until you have really stopped."""
        if self.mode != "voice" or self.turn or self.speaking or self.user_muted or self.spec:
            return
        text = text.strip()
        if launcher.LAUNCH_RE.match(text) and (launcher.find_game(launcher.LAUNCH_RE.match(text).group(1)) or launcher.find_app(launcher.LAUNCH_RE.match(text).group(1))):
            return
        if len(text.split()) < 3 or POWER_DOWN.match(text) or STOP_WORDS.match(text) or SHARE_ON.search(text) or SHARE_OFF.search(text):
            return
        if not self._awake(text):
            return
        self.spec_token += 1
        token = self.spec_token
        if re.search(r"[.?!][\"')\]]*$", text):           # it sounds like a finished sentence: go now
            self._start_spec(text, token)
        else:                                       # maybe just a breath: wait a beat before spending a request on it
            self.spec_timer = threading.Timer(0.25, self._start_spec, (text, token))
            self.spec_timer.start()

    def _start_spec(self, text, token):
        with self.lock:
            if token != self.spec_token or self.spec or self.turn or not self.mode:
                return
            self.spec, self.hold, self.held = {"text": text}, True, []
            self.spec_gen += 1
            self.confirm.clear()
        self._input(text, spec=True)

    def _on_resume(self):
        """You carried on talking: what he started on is out of date."""
        self.spec_token += 1
        if self.spec_timer:
            self.spec_timer.cancel()
        self._cancel_spec()

    def _cancel_spec(self):
        with self.lock:
            if not self.spec:
                return
            self.spec, self.hold, self.held, self.buf = None, False, [], ""
            self.spec_gen += 1
            self.confirm.set()                      # wakes anything waiting for permission, which now finds it was cancelled
            proc = self.proc
            if proc and proc.poll() is None and self.turn:
                self.spec_dropped = True            # the cut-off request stays in his history: the next one must say it replaces it
                self._abandon(proc, "spec")
            self.turn, self.interrupted = False, True

    def _abandon(self, proc, tag):
        """Interrupts the running request. Until its result arrives, whatever it still sends is dropped (see _result)."""
        self.cancelling, self.cancel_t = True, time.time()
        self.cancel_done.clear()
        try:
            msg = {"type": "control_request", "request_id": "%s-%d" % (tag, int(time.time() * 1000)), "request": {"subtype": "interrupt"}}
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
        except Exception:
            self.cancelling = False

    def _confirm_spec(self):
        with self.lock:
            if not self.spec:
                return
            self.spec, self.hold = None, False
            held, self.held = self.held, []
            self.last_addr = self.last_tick = time.time()
            self.confirm.set()
        if not held and self.turn:
            self.set_state("thinking")
        for text, screen in held:                   # whatever he already worked out is said now
            self._say(text, screen)
        if not self.turn and not held:
            self._settle()

    def _permission_held(self, proc, ev, gen):
        """Something he wants to do (click, open, type...) waits until you have really stopped talking."""
        self.confirm.wait(40)
        if self.spec_gen != gen or self.hold:
            msg = {"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"),
                                                            "response": {"behavior": "deny", "message": "Cancelled: the user was still speaking."}}}
            try:
                proc.stdin.write(json.dumps(msg) + "\n")
                proc.stdin.flush()
            except Exception:
                pass
            return
        self._permission(proc, ev)

    def _launch_command(self, text):
        """\"Launch Marvel Rivals\", \"open Firefox\": a clear match starts at once, without a round trip to Claude."""
        m = launcher.LAUNCH_RE.match(text)
        if not m:
            return False
        query = m.group(1)
        game = launcher.find_game(query)
        if game:
            launcher.launch_game(game)
            self._say("Launching %s." % game["name"])
            return True
        app = launcher.find_app(query)
        if app:
            launcher.launch_app(app)
            self._say("Opening %s." % app["name"])
            return True
        return False

    def _command(self, text):
        """Spoken or typed requests that control Jarvis himself rather than going to Claude."""
        if self._launch_command(text):
            return True
        if self.sharing and SHARE_OFF.search(text):
            self.stop_share()
            self._say("Screen share ended.")
            return True
        if SHARE_ON.search(text):
            watch = bool(re.search(r"\bwatch\b", text, re.I))
            if self.sharing:
                self.watch = self.watch or watch
                self._emit_share()
                self._say("Watching with you." if watch else "I can already see your screen.")
            else:
                self.start_share(watch)
            return True
        return False

    def _power_down_later(self, session):
        deadline = time.time() + 15
        time.sleep(0.5)
        while time.time() < deadline and (self.pending > 0 or self.speaking):
            time.sleep(0.2)
        if session == self.session:
            self.emit("poweroff")
            self.stop()

    # ---------- screen share, like a Discord stream: frames of the screen plus captions of what it plays ----------
    def _emit_share(self):
        self.emit("share", on=self.sharing, watch=self.watch)

    def start_share(self, watch=False, auto=False):
        """`auto` is the live view Jarvis starts with: quiet, and it gives up silently if the desktop will not share."""
        if not self.mode or self.share:
            return
        if not which("gst-launch-1.0"):
            if not auto:
                self.emit("error", text="Screen sharing needs GStreamer (gst-launch-1.0), which was not found")
            return
        self.watch, self.auto_share = watch, auto
        self.share = sh = ScreenShare()
        if not auto:
            self._say("Of course.")
        threading.Thread(target=self._share_begin, args=(sh,), daemon=True).start()

    def _share_begin(self, sh):
        """The screen comes through the mouse-control permission (the entire screen, allowed once for good), so there is no picker and no second question."""
        ptr = self.pointer
        try:
            ptr.ensure()
        except Exception:
            pass
        if ptr.backend == "portal" and ptr.session and ptr.node is not None:
            GLib.idle_add(lambda: sh.attach(ptr.conn, ptr.session, ptr.node, self._share_done) and False)
        else:
            sh.start(self._share_done)                  # no portal mouse control: fall back to the desktop's own share dialog

    def _share_done(self, ok, msg):
        """Called on the GTK main loop, so hand off to a thread."""
        sh = self.share
        auto, self.auto_share = self.auto_share, False
        if not ok:
            self.share, self.watch = None, False
            if not auto:
                self.emit("error", text=msg)
                self._say("I couldn't start the screen share, sir.")
            self._emit_share()
            return
        self.sharing = True
        self.last_addr = self.last_tick = time.time()
        self._emit_share()
        if not auto:
            self._say("I can see your screen now." + (" I'll watch along." if self.watch else ""))
        threading.Thread(target=self._start_captions, args=(self.session, sh), daemon=True).start()
        threading.Thread(target=self._watch_loop, args=(self.session, sh), daemon=True).start()

    def stop_share(self):
        sh, self.share = self.share, None
        self.sharing = self.watch = False
        if sh:
            sh.stop()
        cs, self.cap_stt = self.cap_stt, None
        self.cap_ready = False
        self.caps = []
        if cs and cs.poll() is None:
            try:
                cs.stdin.write("quit\n")
                cs.stdin.flush()
            except Exception:
                pass
            cs.terminate()
        self._emit_share()

    def _start_captions(self, session, sh):
        """Listens to what the computer is playing (the default output's monitor) and turns it into text."""
        if not self._ensure_ears() or session != self.session or self.share is not sh:
            return
        self.cap_stt = proc = subprocess.Popen([PY, "-I", STT_SCRIPT, WHISPER, MODELS, "@DEFAULT_MONITOR@"], stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        for line in proc.stdout:
            if self.cap_stt is not proc:
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("ev") == "ready":
                self.cap_ready = True
                self._sync_mic()
            elif ev.get("ev") == "text":
                self.caps = (self.caps + [(time.time(), ev.get("text", ""))])[-60:]
                self.emit("caption", text=ev.get("text", ""))

    # how often he looks on his own: (seconds between checks, minimum gap when something changed, minimum gap when nothing did)
    REACT = {"normal": (1.5, 25, 60), "fast": (1.0, 8, 25), "game": (0.5, 3.5, 12)}

    def _watch_loop(self, session, sh):
        """Looks at the screen on his own (Settings > Jarvis) and speaks only if there is something worth saying."""
        while session == self.session and self.share is sh and self.sharing:
            poll, gap_changed, gap_still = self.REACT.get(self.cfg("jarvisReact", "fast"), self.REACT["fast"])
            time.sleep(poll)
            if not (self.watch or self.cfg("jarvisWatch", True)) or self.turn or self.speaking or self.pending or not self.mode:
                continue
            now = time.time()
            gap = now - self.last_tick
            if gap < gap_changed:
                continue
            fresh = any(ts > self.last_tick for ts, _ in self.caps) or self.activity.count != self.seen_activity
            moved = sh.motion() > 0.12
            if not (fresh or moved) and gap < gap_still:
                continue
            self.seen_activity = self.activity.count
            self.last_tick = now
            self._input(TICK, tick=True)

    def _content(self, text, tick=False):
        """The message for Claude: a note on what the user is doing on the PC, plus (with a live share) the latest frames and captions."""
        sh = self.share
        frames = []
        if sh and self.sharing:
            now = time.time()
            t0, self.speech_t0 = self.speech_t0, 0.0
            if tick:
                frames = sh.frames(2, gap=0.6)
            elif t0 and now - t0 < 30:
                # as you began talking, partway through, and right now: what you saw while saying it
                wanted = [t0 - 0.4, t0, t0 + (now - t0) * 0.5, now - 0.05]
                frames = sh.frames_at(wanted)
            else:
                frames = sh.frames(4, gap=0.5)
        notes = []
        act = self.activity.summary()
        if act:
            notes.append("PC activity:\n" + act)
        if frames:
            n = len(frames)
            ages = ", ".join("%.1fs" % a for _, a in frames)
            notes.append("Live screen share, captured live at about %d frames a second: the %d image%s are frames of the screen, oldest first, taken %s ago. "
                         "When the user spoke, the frames line up with their words: the first shows the moment they began, the last is right now." % (FPS, n, "s" if n > 1 else "", ages))
            heard = " ".join(t for ts, t in self.caps if time.time() - ts < 90)[-1200:]
            if heard:
                notes.append('What the computer\'s audio said recently (automatic captions, may be wrong): "%s"' % heard)
        if not notes:
            return text
        full = "[" + "\n".join(notes) + "]\n" + text
        if not frames:
            return full
        blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(d).decode()}} for d, _age in frames]
        return blocks + [{"type": "text", "text": full}]

    def _clean_shots(self, all_files=False):
        """Screenshots Jarvis took are deleted as soon as he has looked; this catches any he forgot."""
        try:
            for f in os.listdir(SHOTS):
                p = os.path.join(SHOTS, f)
                if all_files or time.time() - os.path.getmtime(p) > 20:
                    os.remove(p)
        except OSError:
            pass

    # ---------- the brain ----------
    def _input(self, text, tick=False, spec=False):
        if not self.mode:
            return
        if self.cancelling:                         # let the abandoned request finish dying before the real one goes in
            self.cancel_done.wait(1.5)              # (if it is slower, _result still swallows its result instead of ending this turn)
        if not tick and self.spec_dropped:
            self.spec_dropped = False
            text = ("(You were cut off: the user kept talking. This is the full request and it REPLACES the one you just started: "
                    "do it once, and do not repeat anything that already happened.) " + text)
        if self.recap:
            text, self.recap = self.recap + "\n" + text, ""
        if not tick and not spec:
            self.last_addr = self.last_tick = time.time()
            self.set_state("thinking")
        if not spec:
            self.hold = False
        self.turn, self.interrupted, self.tick_turn = True, False, tick
        self.tick_text = ""
        self.buf, self.spoke_turn = "", False
        try:
            proc = self._claude()
            msg = {"type": "user", "message": {"role": "user", "content": self._content(text, tick)}}
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
        except Exception as e:
            self.turn = False
            self.emit("error", text="Jarvis could not reach Claude: %s" % e)
            self.set_state(self._rest_state())

    BRAINS = {"fast": ("haiku", "low"), "balanced": ("sonnet", "low"), "smart": ("sonnet", "medium"), "genius": ("opus", "medium")}

    def _brain(self):
        """(model, effort) from Settings > Jarvis."""
        return self.BRAINS.get(self.cfg("jarvisBrain", "balanced"), self.BRAINS["balanced"])

    def _claude(self):
        p = self.proc
        if p and p.poll() is None and self.brain not in (None, self._brain()):
            try:                                    # the brain was changed in Settings: start a fresh session with it
                p.terminate()
            except Exception:
                pass
            p = None
        if p and p.poll() is None:
            return p
        self.brain = self._brain()
        desktop = "%s on %s" % (os.environ.get("XDG_CURRENT_DESKTOP", "Linux desktop"), os.environ.get("XDG_SESSION_TYPE", "Wayland"))
        prompt = PROMPT.format(desktop=desktop, hints=control_hints(), shots=SHOTS)
        cmd = [CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--model", self._brain()[0], "--effort", self._brain()[1], "--permission-mode", "default", "--permission-prompt-tool", "stdio",
               "--add-dir", "/", "--append-system-prompt", prompt,
               "--mcp-config", json.dumps({"mcpServers": {"jarvis": {"command": sys.executable, "args": ["-I", os.path.join(HERE, "claude_linux", "jarvis_mcp.py")]}}}), "--strict-mcp-config"]
        # tool search off: his own tools are loaded from the start instead of costing a ToolSearch round trip in every new session
        env = dict(os.environ, YDOTOOL_SOCKET=YDOTOOL_SOCKET, JARVIS_CTL=CTL_SOCKET, ENABLE_TOOL_SEARCH="false")
        self.proc = p = subprocess.Popen(cmd, cwd=HOME, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, bufsize=1, env=env)
        threading.Thread(target=self._reader, args=(p, self.session), daemon=True).start()
        return p

    def _ydotoold_watch(self, session):
        """ydotoold sometimes dies (typing then silently does nothing); bring it straight back while Jarvis is on."""
        while session == self.session and self.mode:
            time.sleep(2)
            yd = self.ydotoold
            if yd is not None and yd.poll() is not None:
                self.ydotoold = None
                if os.path.exists(YDOTOOL_SOCKET):
                    os.remove(YDOTOOL_SOCKET)
                self._ydotoold()

    def _ydotoold(self):
        if not which("ydotoold") or os.path.exists(YDOTOOL_SOCKET) and self.ydotoold is None and self._socket_alive():
            return
        try:
            if os.path.exists(YDOTOOL_SOCKET):
                os.remove(YDOTOOL_SOCKET)
            self.ydotoold = subprocess.Popen(["ydotoold", "--socket-path", YDOTOOL_SOCKET], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(20):
                if os.path.exists(YDOTOOL_SOCKET):
                    break
                time.sleep(0.1)
        except Exception:
            pass

    @staticmethod
    def _socket_alive():
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(YDOTOOL_SOCKET)
            return True
        except OSError:
            return False
        finally:
            s.close()

    def _reader(self, proc, session):
        try:
            for line in proc.stdout:
                if session != self.session:
                    break
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                typ = ev.get("type")
                if typ == "control_request":
                    self._permission(proc, ev)
                elif typ == "stream_event":
                    self._stream(ev.get("event") or {})
                elif typ == "assistant":
                    self._assistant(ev.get("message") or {})
                elif typ == "result":
                    self._result(ev)
            err = proc.stderr.read().strip()
            if proc.wait() and err and session == self.session and self.turn and self.proc is proc:
                self.emit("error", text=err[-300:])
        except Exception as e:
            self.emit("error", text=str(e))
        if self.proc is proc:
            self.proc = None
            if self.turn and session == self.session:
                self._end_turn()

    def _permission(self, proc, ev):
        r = ev.get("request") or {}
        if r.get("subtype") != "can_use_tool":
            return
        tool, tinput = r.get("tool_name"), r.get("input") or {}
        if self.cancelling:                         # the abandoned request still trying to act: never let it click or type
            body = {"behavior": "deny", "message": "Cancelled: the user interrupted this request."}
            try:
                proc.stdin.write(json.dumps({"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"), "response": body}}) + "\n")
                proc.stdin.flush()
            except Exception:
                pass
            return
        if self.hold:
            threading.Thread(target=self._permission_held, args=(proc, ev, self.spec_gen), daemon=True).start()
            return
        if tool in ("AskUserQuestion", "ExitPlanMode"):
            body = {"behavior": "deny", "message": "Do not use this tool. Ask the user out loud in plain text and wait for their reply."}
        elif self.too_risky(tool, tinput):
            body = {"behavior": "deny", "message": "Blocked by Claude Linux' safety guard: this command could wipe the disk or the home folder. Tell the user, and do not try to work around it."}
        else:
            body = {"behavior": "allow", "updatedInput": tinput}
        msg = {"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"), "response": body}}
        try:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()
        except Exception:
            pass

    def _stream(self, e):
        kind = e.get("type")
        if kind == "message_start":
            self.streamed = False
        elif kind == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
            self.streamed = True
            self._feed(e["delta"].get("text", ""))
        elif kind == "content_block_stop":
            self._flush()

    def _assistant(self, msg):
        u = msg.get("usage") or {}
        if u:
            self.ctx = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
        if self.interrupted or self.cancelling:
            return
        for b in msg.get("content") or []:
            if b.get("type") == "tool_use":
                self._flush()
                if self.hold:
                    continue
                self.emit("tool", name=b.get("name", ""), detail=self._tool_detail(b))
                if not self.speaking and self.pending == 0:
                    self.set_state("acting", self._tool_label(b))
            elif b.get("type") == "text" and not self.streamed and b.get("text", "").strip():
                self._feed(b["text"] + "\n")

    @staticmethod
    def _tool_detail(b):
        i = b.get("input") or {}
        return str(i.get("description") or i.get("command") or i.get("file_path") or i.get("url") or i.get("pattern") or "")[:120]

    @staticmethod
    def _tool_label(b):
        n = b.get("name", "")
        i = b.get("input") or {}
        if n == "Bash":
            return str(i.get("description") or "Working")[:40]
        return {"Read": "Looking", "Write": "Writing", "Edit": "Editing", "WebSearch": "Searching the web", "WebFetch": "Reading the web"}.get(n, "Working")

    def _result(self, ev):
        if self.cancelling:
            self.cancelling = False
            self.cancel_done.set()
            if time.time() - self.cancel_t < 10:   # the abandoned request's result: it must not end the request after it
                self.buf = ""
                return
        self._flush()
        if ev.get("is_error") and not self.interrupted and self.pending == 0 and not self.speaking:
            self._say("I'm afraid something went wrong, sir. %s" % ("Please check your Claude subscription." if "limit" in str(ev.get("result", "")).lower() else "Shall I try again?"))
        self._end_turn()

    def _end_turn(self):
        self.turn = False
        self._clean_shots()
        if self.ctx > CTX_LIMIT and not self.spec:
            self._fresh_session()
        self._settle()

    def _note(self, who, text):
        self.said = (self.said + [(who, text)])[-24:]

    def _fresh_session(self):
        """Every screen picture stays in his context, so replies get slower and older lines get forgotten and repeated. Start over with a short recap."""
        p, self.proc, self.ctx = self.proc, None, 0
        lines = "\n".join("%s: %s" % (who, t[:200]) for who, t in self.said[-16:])
        self.recap = ("[Fresh session (the old one was cleared to keep you fast). The last things said, oldest first:\n%s%s\nDo not redo or repeat any of it.]"
                      % (lines or "(nothing yet)", "\nThe game mic is ON: your replies go into the game's call." if gamemic.modules() else ""))
        if p and p.poll() is None:
            p.terminate()
        threading.Thread(target=self._prewarm_claude, daemon=True).start()

    def interrupt(self, keep_turn=False):
        """Stops talking at once and abandons the current request."""
        with self.lock:
            self.gen += 1
            self.buf, self.tick_text = "", ""
            self.spec, self.hold, self.held = None, False, []
            self.spec_gen += 1
            self.spec_token += 1
            self.confirm.set()
            try:
                while True:
                    self.say_q.get_nowait()
            except queue.Empty:
                pass
            self.pending = 0
        self.voice.stop()
        self.screen.abort()
        proc = self.proc
        if proc and proc.poll() is None and self.turn and not keep_turn:
            self._abandon(proc, "int")
        if not keep_turn:
            self.turn, self.interrupted = False, True
        self.speaking = False
        self.emit("stopsay")
        self._sync_mic()
        self.set_state(("thinking" if self.turn else self._rest_state()) if self.mode else "off")

    # ---------- turning text into speech ----------
    def _next_cut(self):
        for m in CUT.finditer(self.buf):
            if len(self.buf[:m.start()].strip()) >= 10 or "\n" in m.group():
                return m.start(), m.end()
        if not self.spoke_turn:                 # the first words go out at the earliest natural pause, so he starts talking sooner
            for m in re.finditer(r"[,;:]\s", self.buf):
                if m.start() >= 14:
                    return m.start() + 1, m.end()
            for n, m in enumerate(re.finditer(r"\s+", self.buf), 1):
                if n == 5 and m.start() >= 18:
                    return m.start(), m.end()
            if len(self.buf) >= 80 and " " in self.buf[40:]:
                k = self.buf.index(" ", 40)
                return k, k + 1
        return None

    # what a watch check says when it has nothing to report, in any wording ("NOTHING", "Nothing to report.", "No comment")
    NOTHING = re.compile(r"\W*(?:nothing\b|no comment\b|nothing (?:to|worth|new|notable|of note|significant|much)\b)", re.I)

    def _feed(self, delta):
        if self.interrupted or self.cancelling:
            return
        if self.tick_turn:                          # an automatic check is held back until it is complete: only then do we know whether it said "NOTHING"
            self.tick_text += delta
            return
        self.buf += delta
        while True:
            cut = self._next_cut()
            if not cut:
                return
            chunk, self.buf = self.buf[:cut[0]], self.buf[cut[1]:]
            self._say(chunk)

    def _flush(self):
        if self.tick_turn:
            text, self.tick_text = self.tick_text.strip(), ""
            if not text or self.NOTHING.match(text):
                return
            self.buf = text
        rest, self.buf = self.buf, ""
        self._say(rest)

    def _say(self, text, screen=None):
        """Queues a sentence. `screen` is (first word, last word + 1) when it is text being read off the real screen."""
        text = clean_for_speech(text)
        if not self.mode or (not screen and not re.search(r"\w", text)):
            return
        if re.fullmatch(r"\W*NOTHING\W*", text) or self.tick_turn and self.NOTHING.match(text):
            return                                  # the watch check's "nothing to say" must never be spoken or shown, even if it arrives late
        self.spoke_turn = True
        if self.hold:
            self.held.append((text, screen))        # he has an answer ready but you have not finished talking
            return
        self._start_workers()
        with self.lock:
            self.pending += 1
            gen = self.gen
        self._sync_mic()
        self.say_q.put((gen, text, screen))

    def _settle(self):
        """Back to resting once the request is finished and every sentence has been spoken."""
        if self.turn or self.pending > 0 or self.speaking or not self.mode:
            return
        self._sync_mic()
        self.set_state(self._rest_state())

    def _start_workers(self):
        with self.lock:
            if self.workers:
                return
            self.workers = True
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._speech_monitor, daemon=True).start()

    def _synth_loop(self):
        """Sentence by sentence: make the audio (Piper is already loaded, ~0.1 s), hand it to the open player, tell the page when it starts."""
        while True:
            gen, text, screen = self.say_q.get()
            if gen != self.gen:
                continue
            dur, delay = max(0.25 if screen else 0.8, len(text) / 15.0), None
            try:
                if self.voice_on and re.search(r"\w", text):
                    pcm, rate = self.voice.synth(text)
                    if gen != self.gen:
                        continue
                    delay, dur = self.voice.play(pcm, rate)
            except Exception as e:
                self.emit("error", text="Voice failed: %s" % e)
            if gen != self.gen:
                continue
            if delay is None:                               # silent: the voice is off, or there was nothing to pronounce
                delay = self.voice.schedule(dur)
            with self.lock:
                if gen == self.gen:
                    self.pending = max(0, self.pending - 1)
            if screen:
                self.push("jarvis_screen", {"ev": "read", "a": screen[0], "b": screen[1], "delay": round(delay, 3), "dur": round(dur, 3)})
            else:
                self.emit("say", text=text, dur=round(dur, 3), delay=round(delay, 3))
                self._note("Jarvis", text)

    def _speech_monitor(self):
        """Knows when he is talking: closes the microphone on the first sentence, reopens it a moment after the last one ends."""
        quiet = None
        while True:
            time.sleep(0.04)
            busy = self.pending > 0 or self.voice.busy()
            if busy:
                quiet = None
                if not self.speaking:
                    self.speaking = True
                    self._sync_mic()
                    if self.mode:
                        self.set_state("speaking")
            elif self.speaking:
                if quiet is None:
                    quiet = time.time()
                elif time.time() - quiet > 0.4:         # let the room go quiet before listening again
                    quiet, self.speaking = None, False
                    self.last_addr = self.last_tick = time.time()     # no watch check right after he spoke: that is how he ended up saying it again
                    if self.mode:
                        self.set_state("thinking") if self.turn else self._settle()
                    self._sync_mic()

    # ---------- what jarvis_ctl.py (Jarvis' own tool calls) can ask for ----------
    def h_screen_ready(self, m):
        self.screen.overlay_ready.set()

    CTL_HELP = ("ocr [--region X,Y,W,H] | find TEXT | highlight TEXT | read [--from TEXT] [--to TEXT] [--region X,Y,W,H] [--max-chars N] | "
                "move X Y | click [X Y] [--right] [--double] | drag X1 Y1 X2 Y2 | scroll N | games [NAME] | game NAME | apps [NAME] | launch NAME | "
                "img web|lens|match|onscreen|like|sheet ... | look [N] | play JSON | gamemic on|off")

    def _dispatch(self, argv):
        if not self.mode:
            return {"error": "Jarvis is switched off"}
        if not argv or argv[0] in ("help", "-h", "--help"):
            return {"out": self.CTL_HELP}
        cmd, rest = argv[0], argv[1:]
        try:
            if cmd in ("ocr", "find", "highlight", "read"):
                return self.screen.run(cmd, rest)
            if cmd in ("move", "click", "drag", "scroll"):
                return self._pointer_cmd(cmd, rest)
            if cmd in ("games", "game", "apps", "launch"):
                return launcher.run(cmd, rest)
            if cmd == "play":
                try:
                    plan = json.loads(" ".join(rest))
                except ValueError:
                    return {"error": "play needs a JSON list of actions"}
                return {"out": self.game.run(self._pic_moves(plan))}
            if cmd == "look":
                return self._look(rest)
            if cmd == "lookraw":                    # for the jarvis MCP server: the newest frames as base64 JSON
                n = int(rest[0]) if rest and rest[0].isdigit() else 1
                sh = self.share
                frames = sh.frames(max(1, min(n, 6)), gap=0.4) if sh and self.sharing else []
                return {"out": json.dumps([{"data": base64.b64encode(d).decode(), "age": round(a, 2)} for d, a in frames])}
            if cmd == "img":
                return images.run(rest, self)
            if cmd == "gamemic":
                return gamemic.run(rest, self.voice)
        except ValueError:
            return {"error": "usage: " + self.CTL_HELP}
        except Exception as e:
            return {"error": str(e)}
        return {"error": "unknown command %r. Commands: %s" % (cmd, self.CTL_HELP)}

    def _look(self, rest):
        """The newest moments of the live view as picture files to Read (for when he has been busy and needs to see what is on screen now)."""
        n = int(rest[0]) if rest and rest[0].isdigit() else 3
        sh = self.share
        frames = sh.frames(max(1, min(n, 8)), gap=0.5) if sh and self.sharing else []
        if not frames:
            return images.snapshot(self.activity.cursor_pos())
        os.makedirs(SHOTS, exist_ok=True)
        rows = []
        for i, (data, age) in enumerate(frames):
            path = os.path.join(SHOTS, "look-%d-%d.jpg" % (int(time.time() * 1000), i))
            with open(path, "wb") as f:
                f.write(data)
            rows.append("%s  (%.1f seconds ago)" % (path, age))
        return {"out": "Live view, oldest first. Read the pictures, then rm them:\n" + "\n".join(rows)}

    def _scr(self, x, y):
        """A spot in picture pixels (what he reads off the pictures and OCR), as the screen pixels the pointer needs."""
        return to_screen(self.activity.cursor_pos(), x, y)

    def _pic_moves(self, plan):
        """The same play plan with every {"move": [x, y]} turned from picture pixels into screen pixels."""
        if isinstance(plan, list):
            return [self._pic_moves(a) for a in plan]
        if isinstance(plan, dict):
            a = dict(plan)
            if isinstance(a.get("move"), list) and len(a["move"]) == 2:
                a["move"] = list(self._scr(float(a["move"][0]), float(a["move"][1])))
            if isinstance(a.get("do"), list):
                a["do"] = self._pic_moves(a["do"])
            return a
        return plan

    def _pointer_cmd(self, cmd, rest):
        nums = [float(a) for a in rest if re.fullmatch(r"-?\d+(?:\.\d+)?", a)]
        if len(nums) in (2, 4):
            nums = [c for i in range(0, len(nums), 2) for c in self._scr(nums[i], nums[i + 1])]
        ptr = self.pointer
        if cmd == "move":
            if len(nums) != 2:
                raise ValueError
            ptr.move_to(nums[0], nums[1])
        elif cmd == "click":
            if len(nums) == 2:
                ptr.move_to(nums[0], nums[1])
            elif nums:
                raise ValueError
            ptr.click("right" if "--right" in rest else "middle" if "--middle" in rest else "left", "--double" in rest)
        elif cmd == "drag":
            if len(nums) != 4:
                raise ValueError
            ptr.drag(*nums)
        elif cmd == "scroll":
            if len(nums) != 1:
                raise ValueError
            ptr.scroll(nums[0])
        return {"out": "done" + (", pointer is now at %d,%d" % to_view(ptr.pos, *ptr.pos) if ptr.pos else "")}
