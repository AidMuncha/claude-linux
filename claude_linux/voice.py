"""Jarvis' voice, built for speed and for leaving nothing behind.

Piper stays loaded between sentences (loading the voice was most of the old half-second per sentence) and each sentence's audio is
streamed into one player that stays open, so sentences join up without gaps. A sentence's audio lives in RAM (/dev/shm) for the
instant it takes to read it and is deleted straight away; nothing is cached or kept."""
import io
import json
import os
import queue
import select
import shutil
import subprocess
import tempfile
import threading
import time
import wave

from .paths import DATA

JDIR = os.path.join(DATA, "jarvis")
PIPER = os.path.join(JDIR, "piper-bin", "piper", "piper")
VOICE = os.path.join(JDIR, "voice", "jarvis-medium.onnx")
OUT = os.path.join("/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir(), "jarvis-tts-%d" % os.getuid())
SPEED = "0.9"                    # piper's length_scale: below 1 talks faster
LATENCY = 0.05                   # seconds between handing audio over and hearing it


class Voice:
    def __init__(self):
        self.lock = threading.Lock()
        self.piper = None
        self.player = None
        self.player_rate = 0
        self.q = queue.Queue()
        self.gen = 0
        self.audio_end = 0.0             # when everything handed over so far will have finished playing
        self.writer = None

    def ready(self):
        return os.path.isfile(PIPER) and os.path.isfile(VOICE)

    # ---------- making the audio ----------
    def warm(self):
        """Loads the voice now, so the first sentence does not pay for it."""
        if self.ready():
            with self.lock:
                self._piper_start()

    def _piper_start(self):
        self._piper_kill()
        os.makedirs(OUT, exist_ok=True)
        env = dict(os.environ, LD_LIBRARY_PATH=os.path.dirname(PIPER) + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
        self.piper = subprocess.Popen([PIPER, "--model", VOICE, "--output_dir", OUT, "--json-input", "--sentence_silence", "0.08", "--length_scale", SPEED],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=os.path.dirname(PIPER), env=env)

    def _piper_kill(self):
        p, self.piper = self.piper, None
        if p and p.poll() is None:
            p.kill()

    def synth(self, text):
        """Returns (16-bit mono PCM bytes, sample rate)."""
        if self.ready():
            try:
                return self._synth_piper(text)
            except Exception:
                pass
        if not shutil.which("espeak-ng"):
            raise RuntimeError("no voice is installed")
        r = subprocess.run(["espeak-ng", "-v", "en-gb+m3", "-s", "168", "-p", "30", "--stdout", text], capture_output=True, timeout=60, check=True)
        with wave.open(io.BytesIO(r.stdout)) as w:
            return w.readframes(w.getnframes()), w.getframerate()

    def _synth_piper(self, text):
        with self.lock:
            for _attempt in range(2):
                if not self.piper or self.piper.poll() is not None:
                    self._piper_start()
                path = ""
                try:
                    self.piper.stdin.write(json.dumps({"text": text}) + "\n")
                    self.piper.stdin.flush()
                    if select.select([self.piper.stdout], [], [], 15)[0]:
                        path = self.piper.stdout.readline().strip()
                except OSError:
                    pass
                if path and os.path.isfile(path):
                    break
                self._piper_kill()               # it hung or died: start it fresh and try once more
            else:
                raise RuntimeError("the voice stopped answering")
        try:
            with wave.open(path) as w:
                return w.readframes(w.getnframes()), w.getframerate()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ---------- playing it ----------
    def play(self, pcm, rate):
        """Queues the audio behind whatever is already playing. Returns (seconds until it starts, seconds it lasts)."""
        dur = len(pcm) / (2.0 * rate)
        delay = self.schedule(dur)
        self._enqueue(pcm, rate)
        return delay, dur

    def schedule(self, dur):
        """Reserves `dur` seconds on the audio clock, even for silent text, and returns the seconds until it starts."""
        now = time.time()
        start = max(now + LATENCY, self.audio_end)
        self.audio_end = start + dur
        return start - now

    def _enqueue(self, pcm, rate):
        if not self.writer:
            self.writer = threading.Thread(target=self._write_loop, daemon=True)
            self.writer.start()
        self.q.put((self.gen, pcm, rate))

    def _write_loop(self):
        while True:
            gen, pcm, rate = self.q.get()
            if gen != self.gen:
                continue
            try:
                self._ensure_player(rate)
                self.player.stdin.write(pcm)
                self.player.stdin.flush()
            except (OSError, ValueError, AttributeError):
                self._kill_player()              # stopped on purpose, or the player died

    def _ensure_player(self, rate):
        if self.player and self.player.poll() is None and self.player_rate == rate:
            return
        self._kill_player()
        if shutil.which("paplay"):
            cmd = ["paplay", "--raw", "--rate=%d" % rate, "--channels=1", "--format=s16le", "--latency-msec=40"]
        elif shutil.which("aplay"):
            cmd = ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(rate), "-c", "1", "-"]
        else:
            raise OSError("no audio player (paplay) found")
        env = dict(os.environ)
        try:                                     # a "jarvis_voice" sink, if set up, feeds the voice into calls
            if "jarvis_voice" in subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=2).stdout:
                env["PULSE_SINK"] = "jarvis_voice"
        except (OSError, subprocess.SubprocessError):
            pass
        self.player, self.player_rate = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env), rate

    def _kill_player(self):
        p, self.player = self.player, None
        if p and p.poll() is None:
            p.kill()

    def busy(self):
        return time.time() < self.audio_end

    def stop(self):
        """Silence, immediately."""
        self.gen += 1
        self.audio_end = 0.0
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self._kill_player()

    def close(self):
        self.stop()
        with self.lock:
            self._piper_kill()
        shutil.rmtree(OUT, ignore_errors=True)
