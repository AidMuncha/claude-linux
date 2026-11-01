"""Image matching for Jarvis. Runs inside Jarvis' virtualenv (it needs opencv + numpy + Pillow), one command per run, prints plain text.
usage:  jarvis_img.py onscreen NEEDLE SCREENSHOT GX,GY,GW,GH [THRESHOLD]   where is this picture on the screen? (answers in the GX,GY,GW,GH space)
        jarvis_img.py like NEEDLE DIR [N]                                  image files under DIR that look most like NEEDLE
        jarvis_img.py rank NEEDLE FILE...                                  how well each FILE matches NEEDLE (same picture, crop, copy or just similar)
        jarvis_img.py sheet OUT.png FILE...                                numbered contact sheet, so the files can be looked at in one go"""
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
SKIP_DIRS = {".git", "node_modules", ".cache", "__pycache__", ".local", ".var", "venv", "site-packages"}


def load_bgr(path):
    img = Image.open(path)
    img.seek(0)
    bg = Image.new("RGB", img.size, (255, 255, 255))
    rgba = img.convert("RGBA")
    bg.paste(rgba, mask=rgba.split()[3])
    return cv2.cvtColor(np.array(bg), cv2.COLOR_RGB2BGR)


def peaks(res, thr, w, h, limit=5):
    out, res = [], res.copy()
    for _ in range(limit):
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx < thr:
            break
        out.append((mx, loc[0], loc[1]))
        x0, y0 = max(0, loc[0] - w // 2), max(0, loc[1] - h // 2)
        res[y0:loc[1] + h // 2 + 1, x0:loc[0] + w // 2 + 1] = -1
    return out


def onscreen(needle_path, shot_path, geo, thr):
    hay, needle = load_bgr(shot_path), load_bgr(needle_path)
    gx, gy, gw, gh = geo
    sx, sy = gw / hay.shape[1], gh / hay.shape[0]
    hg, ng = cv2.cvtColor(hay, cv2.COLOR_BGR2GRAY), cv2.cvtColor(needle, cv2.COLOR_BGR2GRAY)
    found = []
    for s in [1.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
        n = cv2.resize(ng, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        h, w = n.shape
        if h < 8 or w < 8 or h >= hg.shape[0] or w >= hg.shape[1] or n.std() < 2:
            continue
        for score, x, y in peaks(cv2.matchTemplate(hg, n, cv2.TM_CCOEFF_NORMED), thr, w, h):
            found.append((score, x, y, w, h))
    kept = []
    for f in sorted(found, reverse=True):                    # one answer per spot: the best scale wins
        if all(abs(f[1] + f[3] / 2 - k[1] - k[3] / 2) > max(f[3], k[3]) / 2 or abs(f[2] + f[4] / 2 - k[2] - k[4] / 2) > max(f[4], k[4]) / 2 for k in kept):
            kept.append(f)
    if kept:
        print("found %d match%s (score 1.0 is identical). Each: center X Y, box x,y,w,h" % (len(kept[:5]), "" if len(kept) == 1 else "es"))
        for score, x, y, w, h in kept[:5]:
            print("score %.2f  center %d %d  box %d,%d,%d,%d" % (score, gx + (x + w / 2) * sx, gy + (y + h / 2) * sy, gx + x * sx, gy + y * sy, w * sx, h * sy))
        return 0
    orb = cv2.ORB_create(2500)                                # not a straight copy: allow other sizes, tilt, a different crop
    k1, d1 = orb.detectAndCompute(ng, None)
    k2, d2 = orb.detectAndCompute(hg, None)
    if d1 is not None and d2 is not None and len(k1) >= 8:
        good = [m for m, n in (p for p in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(good) >= 10:
            M, mask = cv2.findHomography(np.float32([k1[m.queryIdx].pt for m in good]), np.float32([k2[m.trainIdx].pt for m in good]), cv2.RANSAC, 5.0)
            if M is not None and int(mask.sum()) >= 10:
                h, w = ng.shape
                pts = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), M).reshape(-1, 2)
                cx, cy = pts.mean(axis=0)
                print("found one approximate match (%d matching details). center %d %d" % (int(mask.sum()), gx + cx * sx, gy + cy * sy))
                return 0
    print("not on this screen")
    return 1


def dhash(img, size=16):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (size + 1, size), interpolation=cv2.INTER_AREA)
    return (g[:, 1:] > g[:, :-1]).flatten()


def hist(img):
    h = cv2.calcHist([cv2.cvtColor(cv2.resize(img, (96, 96)), cv2.COLOR_BGR2HSV)], [0, 1], None, [12, 6], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def like(needle_path, root, count):
    ref = load_bgr(needle_path)
    rh, rc = dhash(ref), hist(ref)
    rows, seen = [], 0
    ref_real = os.path.realpath(needle_path)
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if not f.lower().endswith(EXTS):
                continue
            p = os.path.join(base, f)
            if os.path.realpath(p) == ref_real:
                continue
            seen += 1
            if seen > 6000:
                break
            try:
                img = load_bgr(p)
            except Exception:
                continue
            shape = 1.0 - float((dhash(img) != rh).mean())
            color = max(0.0, float(cv2.compareHist(hist(img), rc, cv2.HISTCMP_CORREL)))
            rows.append((0.7 * shape + 0.3 * color, p))
    rows.sort(reverse=True)
    print("looked at %d images under %s. Most similar first (1.00 is identical):" % (min(seen, 6000), root))
    for score, p in rows[:count]:
        print("%.2f  %s" % (score, p))
    return 0


def inliers(ref_gray, img):
    """How many small details of the two pictures agree geometrically: a high number means the same picture (even resized, cropped, recolored)."""
    orb = cv2.ORB_create(1500)
    k1, d1 = orb.detectAndCompute(ref_gray, None)
    k2, d2 = orb.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None)
    if d1 is None or d2 is None or len(k1) < 8 or len(k2) < 8:
        return 0
    good = [m for m, n in (p for p in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return 0
    M, mask = cv2.findHomography(np.float32([k1[m.queryIdx].pt for m in good]), np.float32([k2[m.trainIdx].pt for m in good]), cv2.RANSAC, 5.0)
    return int(mask.sum()) if M is not None else 0


def rank(needle_path, files):
    ref = load_bgr(needle_path)
    rh, rc, rg = dhash(ref), hist(ref), cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    for f in files:
        try:
            img = load_bgr(f)
        except Exception:
            print("0.00 0 %s" % f)
            continue
        shape = 1.0 - float((dhash(img) != rh).mean())
        color = max(0.0, float(cv2.compareHist(hist(img), rc, cv2.HISTCMP_CORREL)))
        n = inliers(rg, img)
        score = max(0.7 * shape + 0.3 * color, min(1.0, 0.5 + n / 60.0) if n >= 12 else 0.0)
        print("%.2f %d %s" % (score, n, f))
    return 0


def sheet(out, files):
    cols = 4 if len(files) <= 12 else 6
    cell, pad = 300, 6
    rows = (len(files) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (cell + pad) + pad, rows * (cell + pad) + pad), (24, 24, 28))
    d = ImageDraw.Draw(canvas)
    for i, f in enumerate(files):
        x, y = pad + (i % cols) * (cell + pad), pad + (i // cols) * (cell + pad)
        try:
            im = ImageOps.contain(Image.open(f).convert("RGB"), (cell, cell))
            canvas.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        except Exception:
            d.text((x + 8, y + 8), "unreadable", fill=(200, 80, 80))
        d.rectangle((x, y, x + 34, y + 22), fill=(0, 0, 0))
        d.text((x + 6, y + 5), str(i + 1), fill=(255, 255, 255))
    canvas.save(out)
    print(out)
    for i, f in enumerate(files):
        print("%d  %s" % (i + 1, f))
    return 0


def main(a):
    if a[:1] == ["onscreen"] and len(a) >= 4:
        return onscreen(a[1], a[2], [float(v) for v in a[3].split(",")], float(a[4]) if len(a) > 4 else 0.8)
    if a[:1] == ["like"] and len(a) >= 3:
        return like(a[1], a[2], int(a[3]) if len(a) > 3 else 10)
    if a[:1] == ["rank"] and len(a) >= 3:
        return rank(a[1], a[2:])
    if a[:1] == ["sheet"] and len(a) >= 3:
        return sheet(a[1], a[2:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
