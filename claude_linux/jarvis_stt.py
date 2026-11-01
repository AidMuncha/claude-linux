"""Jarvis' ears. Runs inside Jarvis' own virtualenv (it needs faster-whisper), never inside the app.

Reads the microphone through `parecord`, follows what you say while you are still saying it, and prints one JSON object per line on stdout:
    {"ev": "ready"}                      the model is loaded and the microphone is open
    {"ev": "level", "v": 0.0-1.0}        how loud the room is right now (drives the orb)
    {"ev": "hearing"}                    a phrase has started
    {"ev": "partial", "text": "..."}     what has been said so far, refreshed about twice a second while you talk
    {"ev": "pause", "text": "..."}       you went quiet for a moment: the whole phrase so far, final quality (it may continue)
    {"ev": "resume"}                     you carried on after that pause
    {"ev": "text", "text": "..."}        you really stopped: the finished phrase
    {"ev": "nothing"}                    that was not speech
    {"ev": "error", "text": "..."}
Commands arrive on stdin, one per line: `mute`, `unmute`, `quit`. While muted the audio is thrown away, so Jarvis never hears his own voice.

usage: jarvis_stt.py MODEL_NAME MODEL_DIR [SOURCE]
With a SOURCE (e.g. @DEFAULT_MONITOR@, what the computer is playing) it captions that audio instead: only finished phrases ("text").
"""
import array
import json
import math
import queue
import subprocess
import sys
import threading
import time

RATE = 16000
FRAME = 480                          # 30 ms of 16-bit mono audio
FRAME_BYTES = FRAME * 2
PREROLL = 10                         # frames kept from before the phrase was detected
START_FRAMES = 3                     # this many loud frames in a row begin a phrase
PAUSE_FRAMES = 9                     # ~0.27 s of quiet: a pause (he may start thinking, but not talk)
END_FRAMES = 23                      # ~0.7 s of quiet: the phrase is over
PARTIAL_FRAMES = 16                  # a partial transcript about every half second of speech
MAX_FRAMES = 33 * 20                 # never longer than 20 s
MIN_SPEECH = 9                       # shorter than ~0.27 s of speech is a click or a cough
FLOOR_MIN = 120.0                    # the quietest speech threshold we accept
JUNK = {"", "you", "thank you", "thanks for watching", "thank you for watching", "bye", "the", "uh", "um", "hmm", "mm"}

lock = threading.Lock()
state = {"muted": False, "quit": False, "flush": False}
cur = {"paused": False}               # set by the microphone loop, so a pause that has already been talked over is never announced
write_lock = threading.Lock()


def out(obj):
    with write_lock:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()


def rms(buf):
    a = array.array("h")
    a.frombytes(buf)
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def commands():
    for line in sys.stdin:
        c = line.strip()
        with lock:
            if c == "mute":
                state["muted"] = True
            elif c == "unmute":
                state["muted"], state["flush"] = False, True
            elif c == "quit":
                state["quit"] = True
    with lock:
        state["quit"] = True            # the app went away


def load_model(name, root, threads=6):
    from faster_whisper import WhisperModel
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return WhisperModel(name, device="cuda", compute_type="float16", download_root=root)
    except Exception:
        pass
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=root, cpu_threads=threads)


def transcribe(model, pcm, prompt, quick=False):
    import numpy as np
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segs, _info = model.transcribe(audio, language="en", beam_size=1, vad_filter=not quick, condition_on_previous_text=False, temperature=0.0,
                                   without_timestamps=True, initial_prompt=prompt)
    parts = []
    for s in segs:
        if not quick and ((s.no_speech_prob > 0.6 and s.avg_logprob < -0.8) or s.avg_logprob < -1.4):
            continue
        parts.append(s.text.strip())
    return " ".join(p for p in parts if p).strip()


def is_junk(text):
    return text.strip(" .,!?").lower() in JUNK


def transcriber(model, tasks, prompt, stream):
    """One thread does all the transcribing so the microphone loop never waits. Old partials are skipped when newer work is waiting."""
    last_pause = {"text": None, "samples": 0, "pid": -1}
    while True:
        kind, pid, pcm = tasks.get()
        if kind == "quit":
            return
        if kind == "partial" and not tasks.empty():
            continue
        try:
            if kind == "partial":
                text = transcribe(model, pcm, prompt, quick=True)
                if text and not is_junk(text):
                    out({"ev": "partial", "text": text, "pid": pid})
            elif kind == "pause":
                text = transcribe(model, pcm, prompt)
                last_pause = {"text": text, "samples": len(pcm) // 2, "pid": pid}
                if text and not is_junk(text) and cur["paused"]:
                    out({"ev": "pause", "text": text, "pid": pid})
            else:                                               # "final"
                reuse = stream and last_pause["pid"] == pid and last_pause["samples"] >= len(pcm) // 2 - RATE * 0.9
                text = last_pause["text"] if reuse else transcribe(model, pcm, prompt)
                out({"ev": "text", "text": text, "pid": pid} if text and not is_junk(text) else {"ev": "nothing", "pid": pid})
        except Exception as e:
            out({"ev": "error", "text": "Transcription failed: %s" % e})


def main():
    name, root = sys.argv[1], sys.argv[2]
    source = sys.argv[3] if len(sys.argv) > 3 else ""
    stream = not source
    prompt = None if source else "Jarvis, open Firefox, move the mouse, take a screenshot, what's on my screen."
    if source:                       # captions of the game's audio must never slow down hearing you (or the game)
        try:
            import os
            os.nice(10)
        except OSError:
            pass
    try:
        model = load_model(name, root, 2 if source else 4)
        transcribe(model, b"\0\0" * RATE, None, quick=True)        # one throwaway run so the first real phrase is not the slow one
    except Exception as e:
        out({"ev": "error", "text": "Could not load the speech model: %s" % e})
        return
    threading.Thread(target=commands, daemon=True).start()
    tasks = queue.Queue()
    threading.Thread(target=transcriber, args=(model, tasks, prompt, stream), daemon=True).start()
    rec = subprocess.Popen(["parecord"] + (["-d", source] if source else []) + ["--raw", "--format=s16le", "--rate=%d" % RATE, "--channels=1", "--latency-msec=30"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out({"ev": "ready"})

    floor = 200.0                    # running estimate of the room's background loudness
    pre, phrase, loud, quiet, active, paused = [], [], 0, 0, False, False
    pid, since_partial, last_level = 0, 0, 0.0
    while True:
        with lock:
            if state["quit"]:
                break
            muted, flush = state["muted"], state["flush"]
            state["flush"] = False
        buf = rec.stdout.read(FRAME_BYTES)
        if not buf or len(buf) < FRAME_BYTES:
            if rec.poll() is not None:
                out({"ev": "error", "text": "The microphone stopped (is `parecord` working?)"})
                break
            continue
        if flush or muted:
            pre, phrase, loud, quiet, active, paused = [], [], 0, 0, False, False
            cur["paused"] = False
            if muted:
                continue
        level = rms(buf)
        if not active and level < floor * 2.5:
            floor = floor * 0.98 + level * 0.02
        voiced = level > max(FLOOR_MIN, floor * 3.0)
        now = time.time()
        if now - last_level > 0.07:
            last_level = now
            out({"ev": "level", "v": round(min(1.0, level / 4000.0), 3)})
        if not active:
            pre.append(buf)
            del pre[:-PREROLL]
            loud = loud + 1 if voiced else 0
            if loud >= START_FRAMES:
                active, phrase, quiet, paused, since_partial = True, list(pre), 0, False, 0
                pid += 1
                out({"ev": "hearing"})
            continue
        phrase.append(buf)
        if voiced:
            quiet = 0
            if paused:
                paused = cur["paused"] = False
                out({"ev": "resume", "pid": pid})
            since_partial += 1
            if stream and since_partial >= PARTIAL_FRAMES:
                since_partial = 0
                tasks.put(("partial", pid, b"".join(phrase)))
        else:
            quiet += 1
        if stream and quiet == PAUSE_FRAMES and not paused and len(phrase) - quiet >= MIN_SPEECH:
            paused = cur["paused"] = True
            tasks.put(("pause", pid, b"".join(phrase)))
        if quiet >= END_FRAMES or len(phrase) >= MAX_FRAMES:
            voiced_frames = len(phrase) - quiet
            data = b"".join(phrase)
            pre, phrase, loud, quiet, active, paused = [], [], 0, 0, False, False
            cur["paused"] = False
            if voiced_frames < MIN_SPEECH:
                out({"ev": "nothing", "pid": pid})
                continue
            tasks.put(("final", pid, data))
    tasks.put(("quit", 0, b""))
    rec.terminate()


if __name__ == "__main__":
    main()
