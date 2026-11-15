# Owl eyes for the UNO Q LED matrix

Two 6x6 owl eyes (left lens = columns 0-5, right lens = 7-12), brightness 0-7. States: **idle** (random blinks and glances), **boot** (wake-up, then idle), **thinking** (pupils up, a spinner runs round each eye), **hint** (leans in, raises a brow, winks), **correct** (^ ^ bouncing, twinkle; back to idle after 7 s), **wrong** (worried brows, a gentle "not quite"; back to idle after 9 s), **listening** (wide eyes, breathing, head tilts), **sleeping** (closed, drifting Z).

- `eyes.py`: every frame, clip and timing as plain Python data. After an edit, run `python3 eyes.py` to regenerate the block inside `sketch/sketch.ino`.
- Preview without the board: `uv run --with pillow preview.py` writes `previews/<state>.gif` (inside the owl glasses) and `previews/contact_sheet.png`. Add `--plain` for the bare matrix.
- Wire into an App Lab app (`/home/arduino/ArduinoApps/<app>/`):
  1. Copy `sketch/sketch.ino` and `sketch/sketch.yaml` into the app's `sketch/` folder. The sketch also provides the skill's `draw` function, so existing `Bridge.call("draw", ...)` code keeps working.
  2. Copy `python/eyes_bridge.py` next to `python/main.py`, then in `main.py`: `from eyes_bridge import set_state`.
  3. Call `set_state("thinking")` before the model call (run it in a thread), then `set_state("correct")`, `"wrong"` or `"hint"` from the result, `"listening"` while waiting for the student's answer, and `"sleeping"` when nobody has used it for a while.
- On the Bridge, this is `Bridge.call("eyes", "<state>")`, which returns True if the state exists. Keep `App.run()` as the last line of `main.py`.
- The sketch plays "boot" on power-up by itself. Repeating the current state doesn't restart it, it only resets its timer.
