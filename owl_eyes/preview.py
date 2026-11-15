"""Render every owl-eye state as an animated GIF plus one contact-sheet PNG.

    uv run --with pillow preview.py            # -> previews/<state>.gif, previews/contact_sheet.png
    uv run --with pillow preview.py --plain    # bare matrix, without the owl glasses around it

The timeline replays the sketch's player logic (intro, loop, random extras, auto-return), so
the GIFs show what the board does. LEDs are drawn to the real pitch (2.25 mm x 2.0 mm) inside
the owl's glasses (lens centres +-7 mm, radius 11.2 mm, from shell/owl.scad).
"""

from __future__ import annotations

import pathlib
import random
import sys

from PIL import Image, ImageDraw, ImageFont

import eyes

HERE = pathlib.Path(__file__).parent
OUT = HERE / "previews"
PX_MM = 16                       # pixels per millimetre
CW, CH = round(2.25 * PX_MM), round(2.0 * PX_MM)   # LED pitch in pixels (36 x 32)
LED_R = 12
BG = (0, 0, 0)
FACE = (196, 145, 60)            # owl PLA colour
RIM = (40, 40, 40)


def led_color(v: int) -> tuple[int, int, int]:
    if v == 0:
        return (28, 4, 4)        # unlit LED, faintly visible
    k = (v / 7) ** 0.6           # perceived brightness of PWM levels
    return (int(70 + 185 * k), int(10 + 60 * k * k), int(8 + 40 * k * k))


def draw_matrix(img: Image.Image, frame, x0: int, y0: int, cw=CW, ch=CH, r=LED_R):
    d = ImageDraw.Draw(img)
    for row in range(eyes.ROWS):
        for col in range(eyes.COLS):
            v = frame[row][col]
            cx, cy = x0 + col * cw + cw // 2, y0 + row * ch + ch // 2
            if v:   # soft glow, as through the paper diffuser
                gl = tuple(int(c * 0.35) for c in led_color(v))
                d.ellipse((cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4), fill=gl)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=led_color(v))


def owl_canvas(plain: bool):
    mw, mh = CW * eyes.COLS, CH * eyes.ROWS
    if plain:
        img = Image.new("RGB", (mw + 40, mh + 40), BG)
        return img, 20, 20
    W, H = mw + 240, mh + 260
    img = Image.new("RGB", (W, H), FACE)
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, H // 2
    lens_r, rim = 11.2 * PX_MM, 2.6 * PX_MM
    for s in (-1, 1):            # glasses: two rings and the bridge
        lx = cx + s * 7 * PX_MM
        d.ellipse((lx - lens_r - rim, cy - lens_r - rim, lx + lens_r + rim, cy + lens_r + rim), fill=RIM)
    for s in (-1, 1):
        lx = cx + s * 7 * PX_MM
        d.ellipse((lx - lens_r, cy - lens_r, lx + lens_r, cy + lens_r), fill=FACE)
    # the window over the lit matrix (lit area + 1 mm)
    d.rounded_rectangle((cx - mw // 2 - 8, cy - mh // 2 - 8, cx + mw // 2 + 8, cy + mh // 2 + 8), 24, fill=BG)
    # beak under the bridge
    d.polygon([(cx - 4 * PX_MM, cy + lens_r - 2 * PX_MM), (cx + 4 * PX_MM, cy + lens_r - 2 * PX_MM),
               (cx, cy + lens_r + 7 * PX_MM)], fill=(30, 30, 30))
    return img, cx - mw // 2, cy - mh // 2


# ------------------------------------------------------------------ player (mirrors sketch.ino)
def timeline(state: str, total_ms: int, seed: int = 7):
    """List of (frame name, ms, state) as the sketch would show them."""
    rng = random.Random(seed)
    out, now = [], 0
    cur = {"state": None, "start": 0, "next_extra": 0}

    def enter(name):
        s = eyes.STATES[name]
        cur.update(state=name, start=now)
        gmin, gmax = s.get("gap_ms", (0, 0))
        cur["next_extra"] = now + rng.randint(gmin, gmax) if s.get("extras") else 0
        if s.get("intro"):
            return s["intro"]
        if s.get("loop"):
            return s["loop"]
        return enter(s["then"])

    clip = enter(state)
    while now < total_ms:
        for fr, ms in eyes.CLIPS[clip]:
            out.append((fr, ms, cur["state"]))
            now += ms
        s = eyes.STATES[cur["state"]]
        if s.get("then") and now - cur["start"] >= s.get("after_ms", 0):
            clip = enter(s["then"])
        elif s.get("extras") and now >= cur["next_extra"]:
            gmin, gmax = s["gap_ms"]
            cur["next_extra"] = now + rng.randint(gmin, gmax)
            clip = rng.choice(s["extras"])
        elif s.get("loop"):
            clip = s["loop"]
        else:
            out.append((out[-1][0], total_ms - now, cur["state"]))
            break
    return out


PREVIEW_MS = {"idle": 16000, "boot": 6500, "thinking": 6000, "hint": 9000, "correct": 9000,
              "wrong": 12000, "listening": 13000, "sleeping": 12000}


def make_gif(state: str, plain: bool):
    tl = timeline(state, PREVIEW_MS.get(state, 8000))
    frames, durs, prev = [], [], None
    for fr, ms, _ in tl:
        if eyes.FRAMES[fr] == prev:        # same picture: just hold it longer
            durs[-1] += ms
            continue
        prev = eyes.FRAMES[fr]
        img, x0, y0 = owl_canvas(plain)
        draw_matrix(img, prev, x0, y0)
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=64))
        durs.append(ms)
    path = OUT / f"{state}.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0, disposal=1)
    return path, tl


def key_frames(state: str, n=7):
    """Distinct frames of the state's intro and loop, in order, sampled to at most n."""
    s = eyes.STATES[state]
    seq = []
    for k in ("intro", "loop"):
        for fr, _ in eyes.CLIPS.get(s.get(k) or "", []):
            if not seq or seq[-1] != fr:
                seq.append(fr)
    if state == "idle":
        seq = ["open", "half", "closed", "look_l", "look_r", "look_ul", "look_ur"]
    seen, uniq = set(), []
    for fr in seq:
        if fr not in seen:
            seen.add(fr)
            uniq.append(fr)
    if len(uniq) > n:
        uniq = [uniq[round(i * (len(uniq) - 1) / (n - 1))] for i in range(n)]
    return uniq


def contact_sheet(path: pathlib.Path):
    cw, ch, r = 18, 16, 6
    tw, th = cw * eyes.COLS + 28, ch * eyes.ROWS + 34
    label_w, n = 120, 7
    sheet = Image.new("RGB", (label_w + n * tw + 10, len(eyes.STATES) * th + 10), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        small = ImageFont.truetype("DejaVuSans.ttf", 10)
    except OSError:
        font = small = ImageFont.load_default()
    for i, st in enumerate(eyes.STATES):
        y = 5 + i * th
        d.text((10, y + th // 2 - 14), st, fill=(230, 230, 230), font=font)
        for j, fr in enumerate(key_frames(st, n)):
            x = label_w + j * tw
            d.rectangle((x - 4, y - 4, x + cw * eyes.COLS + 4, y + ch * eyes.ROWS + 4), fill=BG)
            draw_matrix(sheet, eyes.FRAMES[fr], x, y, cw, ch, r)
            d.text((x + 2, y + ch * eyes.ROWS + 3), fr, fill=(140, 140, 140), font=small)
    sheet.save(path)


if __name__ == "__main__":
    plain = "--plain" in sys.argv
    eyes.check()
    OUT.mkdir(exist_ok=True)
    for st in eyes.STATES:
        p, tl = make_gif(st, plain)
        print(f"{p.name:16s} {len(tl):4d} steps  {sum(ms for _, ms, _ in tl) / 1000:5.1f} s")
    contact_sheet(OUT / "contact_sheet.png")
    print("contact_sheet.png")
