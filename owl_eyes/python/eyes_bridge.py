"""Linux-side helper: tell the owl's eyes (sketch/sketch.ino) what to show.

    from eyes_bridge import set_state
    set_state("thinking")      # before a model call (run the call itself in a thread)
    set_state("correct")       # or "wrong", "hint", "listening", "idle", "sleeping", "boot"

Uses the Bridge exactly as the unoq-hardware-ui skill shows: the module-level `Bridge` object
from arduino.app_utils and Bridge.call(name, *args). The sketch registers "eyes" (a state
name) and "draw" (one custom 8x13 frame, e.g. a letter A-E made with Frame(...).to_board_bytes()).
"correct" and "wrong" fall back to "idle" by themselves after a few seconds; "boot" goes to
"idle" when it ends. Every other state stays until you set another one.
"""

import logging
import threading

from arduino.app_utils import Bridge

STATES = ("idle", "boot", "thinking", "hint", "correct", "wrong", "listening", "sleeping")

log = logging.getLogger("owl_eyes")
_lock = threading.Lock()      # one Bridge call at a time from this helper
_current = None


def set_state(name: str) -> bool:
    """Show an eye animation. Returns True if the sketch accepted it. Never raises, so a
    missing or busy microcontroller can't break the copilot."""
    global _current
    name = name.strip().lower()
    if name not in STATES:
        log.warning("owl eyes: unknown state %r (choose from %s)", name, ", ".join(STATES))
        return False
    with _lock:
        try:
            ok = bool(Bridge.call("eyes", name))
        except Exception as error:  # timeout, sketch not running, ...
            log.warning("owl eyes: Bridge.call('eyes', %r) failed: %s", name, error)
            return False
    if ok:
        _current = name
    return ok


def show_frame(frame_bytes) -> bool:
    """Show one custom frame (bytes from Frame(grid).to_board_bytes()) until the next
    set_state(). Same as the skill's Bridge.call("draw", ...)."""
    global _current
    with _lock:
        try:
            Bridge.call("draw", frame_bytes)
        except Exception as error:
            log.warning("owl eyes: Bridge.call('draw') failed: %s", error)
            return False
    _current = None
    return True


def current_state():
    """The last state this helper set (the sketch may have moved on from correct/wrong/boot)."""
    return _current
