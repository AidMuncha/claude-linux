"""Jarvis' voice as a microphone, for games and calls that listen to you (Scam With Your Friends' AI callers, voice chat).

`on`:  his voice plays into a "jarvis_voice" sink (voice.py already looks for it), which is looped to your speakers so you still hear him,
       and into a "jarvis_mic" sink together with your real microphone. Apps that are recording (the game) are switched to jarvis_mic's monitor,
       so they hear you and him; apps that refuse to be moved (Wine games) are rewired port by port, no restart needed.
       Jarvis' own ears keep listening to the real microphone only, so he never hears himself.
`off`: everything put back and removed."""
import subprocess

VOICE_SINK, MIC_SINK = "jarvis_voice", "jarvis_mic"
OWN = ("parecord", "python", "python3")                  # Jarvis' own recorders (ears, captions) stay where they are


def sh(*args):
    return subprocess.run(list(args), capture_output=True, text=True, timeout=5)


def pactl(*args):
    return sh("pactl", *args).stdout.strip()


def modules():
    """Ids of the modules this file loaded."""
    ids = []
    for line in pactl("list", "short", "modules").splitlines():
        parts = line.split("\t")
        if len(parts) > 2 and ("sink_name=%s" % VOICE_SINK in parts[2] or "sink_name=%s" % MIC_SINK in parts[2]
                               or "source=%s.monitor" % VOICE_SINK in parts[2] or "sink=%s" % MIC_SINK in parts[2]):
            ids.append(parts[0])
    return ids


def real_mic():
    src = pactl("get-default-source")
    return None if not src or src.startswith(MIC_SINK) else src


def recorders():
    """[(source output id, app binary, app name)] of apps recording a microphone right now, Jarvis' own left out."""
    out, cur = [], None
    for line in pactl("list", "source-outputs").splitlines():
        line = line.strip()
        if line.startswith("Source Output #"):
            cur = {"id": line.split("#")[1], "bin": "", "name": ""}
            out.append(cur)
        elif cur and line.startswith("application.process.binary"):
            cur["bin"] = line.split("=", 1)[1].strip().strip('"')
        elif cur and line.startswith("application.name"):
            cur["name"] = line.split("=", 1)[1].strip().strip('"')
    return [(r["id"], r["bin"], r["name"]) for r in out if r["name"] and r["bin"] not in OWN and not r["bin"].startswith("python")
            and not r["name"].startswith(("parecord", "Jarvis"))]


def links():
    """{input port: [output ports feeding it]} from pw-link."""
    res, port = {}, None
    for line in sh("pw-link", "-l").stdout.splitlines():
        if not line.startswith(" "):
            port = line.strip()
        elif port and "|<-" in line:
            res.setdefault(port, []).append(line.split("|<-", 1)[1].strip())
    return res


def rewire(app, source_ports):
    """Feed the app's microphone inputs from source_ports only (for streams that refuse a normal move)."""
    ins = [p for p in sh("pw-link", "-i").stdout.splitlines() if p.startswith(app + ":input")]
    feeds = links()
    for port in ins:
        for src in feeds.get(port, []):
            if src not in source_ports:
                sh("pw-link", "-d", src, port)
        for src in source_ports:
            sh("pw-link", src, port)
    return bool(ins)


def ports_of(node):
    return [p for p in sh("pw-link", "-o").stdout.splitlines() if p.startswith(node + ":")]


def on(voice=None):
    mic = real_mic()
    if not mic:
        return "no microphone found"
    if not modules():
        pactl("load-module", "module-null-sink", "sink_name=%s" % VOICE_SINK, "sink_properties=device.description=Jarvis-Voice")
        pactl("load-module", "module-null-sink", "sink_name=%s" % MIC_SINK, "sink_properties=device.description=Jarvis-Mic")
        pactl("load-module", "module-loopback", "source=%s.monitor" % VOICE_SINK, "sink=@DEFAULT_SINK@", "latency_msec=30")
        pactl("load-module", "module-loopback", "source=%s.monitor" % VOICE_SINK, "sink=%s" % MIC_SINK, "latency_msec=30")
        pactl("load-module", "module-loopback", "source=%s" % mic, "sink=%s" % MIC_SINK, "latency_msec=30")
    moved = []
    for i, _b, name in recorders():
        if sh("pactl", "move-source-output", i, "%s.monitor" % MIC_SINK).returncode == 0 or rewire(name, ports_of(MIC_SINK)):
            moved.append(name)
    if voice:
        voice._kill_player()                             # the next sentence opens a player on jarvis_voice
    return "game mic on: your voice and mine go into %s" % (", ".join(sorted(set(moved))) or "apps that start recording now (pick Jarvis-Mic in their settings if they ask)")


def off(voice=None):
    mic = real_mic()
    if mic:
        for i, _b, name in recorders():
            if sh("pactl", "move-source-output", i, mic).returncode != 0:
                rewire(name, [p for p in ports_of(mic) if ":capture" in p])
    for m in reversed(modules()):
        pactl("unload-module", m)
    if voice:
        voice._kill_player()
    return "game mic off"


def run(argv, voice=None):
    if argv[:1] == ["on"]:
        return {"out": on(voice)}
    if argv[:1] == ["off"]:
        return {"out": off(voice)}
    return {"out": "game mic is %s" % ("on" if modules() else "off")}
