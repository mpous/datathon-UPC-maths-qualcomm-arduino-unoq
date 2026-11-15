"""Owl eyes for the Arduino UNO Q 8x13 LED matrix: frames and timing, as plain Python data.

The board sits behind the owl's round glasses: the left lens is over columns 0-5 and the right
lens over columns 7-12 (lens centres are about 3 columns either side of the middle, see
shell/owl.scad), so each eye is a 6x6 glyph and column 6 is the gap between them.

Brightness is 0-7 (the matrix default, setGrayscaleBits(3), as in the official
02-led-matrix-frame example and the unoq-hardware-ui skill).

    FRAMES  name -> 8 rows x 13 columns of 0..7
    CLIPS   name -> [(frame name, milliseconds), ...]
    STATES  name -> intro clip, loop clip, random extras, auto-return

Edit this file, then run `python3 eyes.py` to regenerate the frame block inside
sketch/sketch.ino (standard library only). `uv run --with pillow preview.py` renders GIFs.
"""

from __future__ import annotations

import pathlib
import sys

ROWS, COLS = 8, 13
LEFT_X, RIGHT_X = 0, 7      # first column of each eye
EYE_Y = 1                   # top row of an eye glyph in its resting place (rows 1-6)

# Brightness palette (0-7)
RING, PUPIL, LID, ARC, Z = 4, 7, 5, 7, 5


# ------------------------------------------------------------------ glyph helpers
def art(*rows: str) -> list[list[int]]:
    """String art -> grid. '.' is off, a digit 1-7 is that brightness."""
    return [[0 if ch == "." else int(ch) for ch in row] for row in rows]


def blank(h: int = 6, w: int = 6) -> list[list[int]]:
    return [[0] * w for _ in range(h)]


def mirror(g):
    return [list(reversed(r)) for r in g]


RING_MASK = art(
    ".1111.",
    "1....1",
    "1....1",
    "1....1",
    "1....1",
    ".1111.",
)
# ring pixels clockwise from the top-left, used by the "thinking" spinner
RING_PATH = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 5), (2, 5), (3, 5), (4, 5),
             (5, 4), (5, 3), (5, 2), (5, 1), (4, 0), (3, 0), (2, 0), (1, 0)]


def eye(dx=0, dy=0, ring=RING, pupil=PUPIL, iris=0, top=None, bottom=None, side="L"):
    """An open eye: ring, optional iris, 2x2 pupil moved by dx/dy (-1..1).

    top/bottom: lid profile for the LEFT eye, one row index per column (0-5). Everything above
    `top[c]` is cleared and a lid pixel is drawn at top[c]; likewise below `bottom[c]`.
    For the right eye the profiles are mirrored, so a sad slant stays symmetric while the
    pupils keep looking the same way.
    """
    g = [[ring if m else 0 for m in row] for row in RING_MASK]
    if iris:
        for r in range(1, 5):
            for c in range(1, 5):
                g[r][c] = iris
    for r in (2 + dy, 3 + dy):
        for c in (2 + dx, 3 + dx):
            g[r][c] = pupil
    if top is not None:
        prof = top if side == "L" else list(reversed(top))
        for c, lr in enumerate(prof):
            for r in range(lr):
                g[r][c] = 0
            g[lr][c] = LID
    if bottom is not None:
        prof = bottom if side == "L" else list(reversed(bottom))
        for c, lr in enumerate(prof):
            for r in range(lr + 1, 6):
                g[r][c] = 0
            g[lr][c] = LID
    return g


def pair(**kw):
    return eye(side="L", **kw), eye(side="R", **kw)


def frame(left, right=None, y=EYE_Y, yr=None, dots=()):
    """Place two glyphs on the 8x13 matrix. `right` defaults to the mirrored left glyph.
    `dots` are extra (row, col, brightness) pixels drawn on top (sparkles, the z)."""
    if right is None:
        right = mirror(left)
    yr = y if yr is None else yr
    f = [[0] * COLS for _ in range(ROWS)]
    for g, x0, y0 in ((left, LEFT_X, y), (right, RIGHT_X, yr)):
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v and 0 <= y0 + r < ROWS:
                    f[y0 + r][x0 + c] = v
    for r, c, v in dots:
        if 0 <= r < ROWS and 0 <= c < COLS:
            f[r][c] = v
    return f


# closed-eye shapes (left eye; right is mirrored)
CLOSED = art(          # blink: a flat lid
    "......",
    "......",
    "......",
    "555555",
    "......",
    "......",
)
HALF = art(            # blink in-between: lid halfway, bottom of the ring still there
    "......",
    "......",
    "555555",
    "4.77.4",
    "4....4",
    ".4444.",
)
SLEEPY = art(          # asleep: soft downward curve (a "u")
    "......",
    "......",
    "......",
    "4....4",
    ".4444.",
    "......",
)
HAPPY = art(           # ^ ^ : closed, upward arch
    "......",
    ".7777.",
    "7....7",
    "7....7",
    "......",
    "......",
)
WINK = art(            # a cheeky closed eye, arched like a happy eye
    "......",
    "......",
    ".6666.",
    "6....6",
    "......",
    "......",
)
Z_BIG = art(
    "5555",
    "..5.",
    ".5..",
    "5555",
)


def sprite(g, r, c, scale=None):
    """(row, col, brightness) dots for a small sprite placed at (r, c); `scale` caps brightness."""
    return [(r + i, c + j, v if scale is None else min(v, scale))
            for i, row in enumerate(g) for j, v in enumerate(row) if v]


def spinner(head, cw=True, dx=0, dy=-1):
    """Ring with a bright comet at RING_PATH[head], dim elsewhere; pupils looking up."""
    g = eye(dx=dx, dy=dy, ring=1)
    for k, v in ((0, 7), (1, 5), (2, 3)):
        i = (head - k) % 16 if cw else (head + k) % 16
        r, c = RING_PATH[i]
        g[r][c] = v
    return g


SPARKLE = art(".7.", "777", ".7.")
SPARKLE_DIM = art(".2.", "252", ".2.")

# ------------------------------------------------------------------ frames
FRAMES: dict[str, list[list[int]]] = {}


def F(name, f):
    FRAMES[name] = f
    return name


# basic looks
F("off", frame(blank(), blank()))
for name, dx, dy in (("open", 0, 0), ("look_l", -1, 0), ("look_r", 1, 0), ("look_up", 0, -1),
                     ("look_down", 0, 1), ("look_ul", -1, -1), ("look_ur", 1, -1),
                     ("look_dl", -1, 1), ("look_dr", 1, 1)):
    F(name, frame(*pair(dx=dx, dy=dy)))
F("half", frame(HALF))
F("closed", frame(CLOSED))

# boot: two pupils glow up in the dark, the rings appear, a sleepy first blink, a look around
F("boot_dot1", frame(*pair(ring=0, pupil=2)))
F("boot_dot2", frame(*pair(ring=0, pupil=5)))
F("boot_ring1", frame(*pair(ring=1)))
F("boot_ring2", frame(*pair(ring=2)))
F("boot_sleepy", frame(*pair(top=[3] * 6)))           # heavy lids, just the bottom of the pupils

# thinking: comet running round each ring (left anticlockwise, right clockwise), pupils up
for i in range(16):
    for tag, dx in (("r", 1), ("l", -1)):
        left = spinner(i, cw=False, dx=dx)
        # the right ring mirrors the left one, so the two comets swing outwards together
        right = mirror(spinner(i, cw=False, dx=-dx))
        F(f"think_{tag}{i:02d}", frame(left, right))

# hint: lean in (eyes one row lower), look at the student, raise one brow, wink
BROW = [(0, 8, 6), (0, 9, 7), (0, 10, 7), (0, 11, 6)]
SQUINT = [3, 3, 3, 3, 3, 3]
F("hint_look", frame(*pair(dy=1), y=2))
F("hint_brow", frame(eye(dy=1, top=[2] * 6), eye(dy=1, side="R"), y=2, dots=BROW))
F("hint_brow_hi", frame(eye(dy=1, top=SQUINT), eye(dx=-1, dy=1, side="R"), y=2, dots=BROW))
F("hint_wink_half", frame(eye(dy=1), eye(dy=1, side="R", top=[3] * 6), y=2))
F("hint_wink", frame(eye(dy=1), mirror(WINK), y=2))
F("hint_half", frame(HALF, y=2))
F("hint_closed", frame(CLOSED, y=2))

# correct: eyes pop up, then happy ^ ^ bouncing with a twinkle between them
F("happy_pop", frame(*pair(dy=-1), y=0))
F("happy_up", frame(HAPPY, y=0, dots=sprite(SPARKLE, 5, 5)))
F("happy_dn", frame(HAPPY, y=1, dots=sprite(SPARKLE_DIM, 5, 5)))
F("happy_up2", frame(HAPPY, y=0, dots=[(0, 6, 3), (7, 0, 4), (7, 12, 4)]))
F("happy_dn2", frame(HAPPY, y=1, dots=[(6, 6, 2)]))

# wrong: soft and kind, never mocking -- worried "/ \\" brows over slightly squashed eyes,
# pupils down, a gentle side-to-side "not quite", then a softer look back at the student
SAD_EYE = art(
    ".4444.",
    "4....4",
    "4....4",
    "4....4",
    ".4444.",
)


def sad_eye(dx=0, up=False):
    g = [row[:] for row in SAD_EYE]
    for r in ((1, 2) if up else (2, 3)):
        for c in (2 + dx, 3 + dx):
            g[r][c] = PUPIL
    return g


def worried_brows(v):
    return [(1, 1, v), (1, 2, v), (0, 3, v), (0, 4, v), (0, 8, v), (0, 9, v), (1, 10, v), (1, 11, v)]


F("sad_down", frame(sad_eye(), sad_eye(), y=3, dots=worried_brows(6)))
F("sad_dl", frame(sad_eye(-1), sad_eye(-1), y=3, dots=worried_brows(6)))
F("sad_dr", frame(sad_eye(1), sad_eye(1), y=3, dots=worried_brows(6)))
F("sad_soft", frame(sad_eye(up=True), sad_eye(up=True), y=3, dots=worried_brows(3)))
F("sad_closed", frame(CLOSED, y=2, dots=worried_brows(3)))

# listening: wide awake, pupils up toward the student, slow ring "breathing", curious head tilts
for b in (3, 4, 5, 6):
    F(f"listen_{b}", frame(*pair(dy=-1, ring=b)))
F("listen_tilt_l", frame(*pair(dy=-1, ring=5), y=1, yr=0))
F("listen_tilt_r", frame(*pair(dy=-1, ring=5), y=0, yr=1))
F("listen_half", frame(HALF))

# sleeping: heavy lids, then closed and low with a z drifting up and away
F("sleep_droop", frame(*pair(top=[4] * 6)))
F("sleep_0", frame(SLEEPY, y=2))
F("sleep_1", frame(SLEEPY, y=2, dots=sprite(Z_BIG, 0, 4, 2)))
F("sleep_2", frame(SLEEPY, y=2, dots=sprite(Z_BIG, 0, 5, 4)))
F("sleep_3", frame(SLEEPY, y=2, dots=sprite(Z_BIG, 0, 7)))
F("sleep_4", frame(SLEEPY, y=2, dots=sprite(Z_BIG, 0, 9, 3)))
F("sleep_5", frame(SLEEPY, y=2, dots=sprite(Z_BIG, 0, 10, 1)))
F("sleep_b", frame([[min(v, 2) for v in r] for r in SLEEPY], y=2))   # breathing: dimmer lids


# ------------------------------------------------------------------ clips (frame, ms)
def hold(name, ms):
    return [(name, ms)]


BLINK = [("half", 60), ("closed", 90), ("half", 60)]
CLIPS: dict[str, list[tuple[str, int]]] = {
    # idle
    "idle_loop": hold("open", 200),
    "blink": BLINK + hold("open", 120),
    "double_blink": BLINK + hold("open", 180) + BLINK + hold("open", 120),
    "glance_l": hold("look_l", 1100) + hold("open", 150),
    "glance_r": hold("look_r", 1100) + hold("open", 150),
    "glance_lr": hold("look_l", 800) + hold("open", 120) + hold("look_r", 800) + hold("open", 150),
    "look_around": hold("look_ul", 700) + hold("look_up", 300) + hold("look_ur", 700) + BLINK + hold("open", 120),

    # boot / wake-up (about 5 s)
    "boot": [("off", 400), ("boot_dot1", 300), ("boot_dot2", 300),
             ("boot_ring1", 200), ("boot_ring2", 200), ("open", 600),
             ("half", 80), ("closed", 300), ("boot_sleepy", 500), ("closed", 250),
             ("half", 100), ("open", 600),
             ("look_l", 450), ("open", 150), ("look_r", 450), ("open", 300)] + BLINK + hold("open", 300),

    # thinking: comet spins round each ring, pupils look up-right then up-left
    "think_intro": hold("look_up", 250),
    "think_loop": [(f"think_r{i:02d}", 80) for i in range(16)] * 2
                  + [(f"think_l{i:02d}", 80) for i in range(16)] * 2,

    # hint: lean in and look at the student, raise a brow ("hmm, here's a clue"), wink
    "hint_intro": hold("hint_look", 450) + hold("hint_brow", 150) + hold("hint_brow_hi", 1000)
                  + hold("hint_brow", 150) + hold("hint_look", 300) + hold("hint_wink_half", 70)
                  + hold("hint_wink", 500) + hold("hint_wink_half", 70) + hold("hint_look", 300),
    "hint_loop": hold("hint_look", 2400) + hold("hint_brow", 150) + hold("hint_brow_hi", 1300)
                 + hold("hint_brow", 150) + hold("hint_look", 1800)
                 + [("hint_half", 60), ("hint_closed", 90), ("hint_half", 60)],

    # correct: eyes pop up wide, then happy ^ ^ bouncing with a twinkle between them
    "correct_intro": hold("happy_pop", 300),
    "correct_loop": hold("happy_up", 250) + hold("happy_dn", 250) + hold("happy_up2", 250) + hold("happy_dn2", 250),

    # wrong: look down, worried brows, gentle side-to-side "not quite", then a softer look up
    "wrong_intro": hold("open", 150) + hold("look_down", 350) + hold("sad_down", 800)
                   + hold("sad_dl", 500) + hold("sad_dr", 500) + hold("sad_dl", 500) + hold("sad_down", 700),
    "wrong_loop": hold("sad_soft", 2200) + hold("sad_closed", 180) + hold("sad_soft", 1600)
                  + hold("sad_down", 1200),

    # listening: perk up, breathe, tilt the head like a curious owl, blink
    "listen_intro": hold("look_up", 120) + hold("listen_6", 300),
    "listen_loop": [("listen_4", 400), ("listen_5", 400), ("listen_6", 600), ("listen_5", 400),
                    ("listen_tilt_r", 1600), ("listen_5", 300), ("listen_4", 500),
                    ("listen_half", 60), ("closed", 90), ("listen_half", 60),
                    ("listen_4", 400), ("listen_5", 400), ("listen_6", 600), ("listen_5", 400),
                    ("listen_tilt_l", 1600), ("listen_5", 300), ("listen_4", 500)],

    # sleeping: heavy lids, close, then breathe with a z floating away
    "sleep_intro": hold("half", 300) + hold("sleep_droop", 600) + hold("half", 200)
                   + hold("sleep_droop", 900) + hold("sleep_0", 800),
    "sleep_loop": [("sleep_0", 700), ("sleep_1", 300), ("sleep_2", 500), ("sleep_3", 500),
                   ("sleep_4", 500), ("sleep_5", 400), ("sleep_0", 600), ("sleep_b", 1200),
                   ("sleep_0", 600)],
}

# ------------------------------------------------------------------ states
# intro: played once on entry. loop: repeated. extras: one is picked at random after a random
# pause of gap_ms=(min, max) and played at a loop boundary (idle blinks and glances).
# then/after_ms: switch state automatically (after_ms=0 means right after the intro).
STATES: dict[str, dict] = {
    "idle":      dict(intro=None, loop="idle_loop", gap_ms=(1800, 5500),
                      extras=["blink", "blink", "blink", "double_blink", "glance_l", "glance_r",
                              "blink", "glance_lr", "look_around"]),
    "boot":      dict(intro="boot", loop=None, then="idle", after_ms=0),
    "thinking":  dict(intro="think_intro", loop="think_loop"),
    "hint":      dict(intro="hint_intro", loop="hint_loop"),
    "correct":   dict(intro="correct_intro", loop="correct_loop", then="idle", after_ms=7000),
    "wrong":     dict(intro="wrong_intro", loop="wrong_loop", then="idle", after_ms=9000),
    "listening": dict(intro="listen_intro", loop="listen_loop"),
    "sleeping":  dict(intro="sleep_intro", loop="sleep_loop"),
}
STATE_NAMES = list(STATES)


def check():
    for n, f in FRAMES.items():
        assert len(f) == ROWS and all(len(r) == COLS for r in f), n
        assert all(0 <= v <= 7 for r in f for v in r), n
    for n, clip in CLIPS.items():
        for fr, ms in clip:
            assert fr in FRAMES, (n, fr)
            assert 20 <= ms <= 65535, (n, ms)
    for n, s in STATES.items():
        for k in ("intro", "loop"):
            assert s.get(k) is None or s[k] in CLIPS, (n, k)
        assert all(e in CLIPS for e in s.get("extras", [])), n
        assert s.get("then") is None or s["then"] in STATES, n


# ------------------------------------------------------------------ sketch code generation
BEGIN, END = "// ==== BEGIN GENERATED BY eyes.py ====", "// ==== END GENERATED BY eyes.py ===="


def to_c() -> str:
    check()
    used = sorted({fr for c in CLIPS.values() for fr, _ in c}, key=list(FRAMES).index)
    idx = {n: i for i, n in enumerate(used)}
    out = [BEGIN, "// Do not edit by hand: change eyes.py and run `python3 eyes.py`.", ""]
    out.append(f"const uint16_t N_FRAMES = {len(used)};")
    out.append(f"const uint8_t FRAMES[N_FRAMES][FRAME_SIZE] = {{")
    for n in used:
        flat = ",".join(str(v) for r in FRAMES[n] for v in r)
        out.append(f"  {{{flat}}},  // {n}")
    out.append("};")
    out.append("")
    steps, clip_rows, clip_idx = [], [], {}
    for i, (n, clip) in enumerate(CLIPS.items()):
        clip_idx[n] = i
        clip_rows.append(f"  {{{len(steps)}, {len(clip)}}},  // {n}")
        steps += [f"{{{idx[fr]}, {ms}}}" for fr, ms in clip]
    out.append(f"const Step STEPS[] = {{")
    for i in range(0, len(steps), 8):
        out.append("  " + ", ".join(steps[i:i + 8]) + ",")
    out.append("};")
    out.append(f"const Clip CLIPS[] = {{")
    out += clip_rows
    out.append("};")
    extras = []
    st_rows = []
    sidx = {n: i for i, n in enumerate(STATES)}
    for n, s in STATES.items():
        ex = [clip_idx[e] for e in s.get("extras", [])]
        gmin, gmax = s.get("gap_ms", (0, 0))
        st_rows.append(
            f'  {{"{n}", {clip_idx[s["intro"]] if s.get("intro") else -1}, '
            f'{clip_idx[s["loop"]] if s.get("loop") else -1}, {len(extras)}, {len(ex)}, '
            f'{gmin}, {gmax}, {sidx[s["then"]] if s.get("then") else -1}, {s.get("after_ms", 0)}}},')
        extras += ex
    out.append(f"const uint8_t EXTRAS[] = {{{', '.join(map(str, extras)) or '0'}}};")
    out.append(f"const uint8_t N_STATES = {len(STATES)};")
    out.append("const State STATES[N_STATES] = {")
    out.append("  // name, intro, loop, first extra, n extras, gap min, gap max, then, after ms")
    out += st_rows
    out.append("};")
    out.append(f"const int8_t STATE_IDLE = {sidx['idle']};")
    out.append(f"const int8_t STATE_BOOT = {sidx['boot']};")
    out.append(END)
    return "\n".join(out)


def write_sketch(path: pathlib.Path):
    text = path.read_text()
    a, b = text.index(BEGIN), text.index(END) + len(END)
    path.write_text(text[:a] + to_c() + text[b:])


if __name__ == "__main__":
    check()
    sketch = pathlib.Path(__file__).with_name("sketch") / "sketch.ino"
    write_sketch(sketch)
    used = {fr for c in CLIPS.values() for fr, _ in c}
    print(f"{len(used)} frames, {len(CLIPS)} clips, {len(STATES)} states -> {sketch}", file=sys.stderr)
