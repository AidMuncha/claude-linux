"""Finds text on the screen. Runs inside Jarvis' virtualenv (it needs rapidocr) and stays loaded between requests.
stdin: one image path per line.  stdout: one JSON object per line:
    {"w": 1920, "h": 1080, "lines": [{"words": [{"t": "Hello", "x": 10, "y": 20, "w": 50, "h": 18}, ...]}, ...]}   (pixels of that image)
    {"error": "..."}"""
import json
import sys

real_out = sys.stdout
sys.stdout = sys.stderr                  # any chatter from the libraries must not end up in the answers


def reply(obj):
    real_out.write(json.dumps(obj) + "\n")
    real_out.flush()


def main():
    try:
        from rapidocr import RapidOCR
        engine = RapidOCR()
    except Exception as e:
        reply({"error": "could not load the text finder: %s" % e})
        return
    reply({"ready": True})
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
            res = engine(path, return_word_box=True)
            lines = []
            for words in (res.word_results or []):
                ws = []
                for text, _score, box in words:
                    xs, ys = [p[0] for p in box], [p[1] for p in box]
                    if str(text).strip():
                        ws.append({"t": str(text), "x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)})
                if ws:
                    lines.append({"words": ws})
            reply({"w": w, "h": h, "lines": lines})
        except Exception as e:
            reply({"error": "text finding failed: %s" % e})


if __name__ == "__main__":
    main()
