"""The Cangur Coach's face: the board's 8x13 LED matrix.

The Teach server (coach/server.py, port 8000) calls this app over HTTP:

    GET /led/tick/0      a tick, for a right answer
    GET /led/cross/0     a cross, for a wrong answer
    GET /led/level/5     the student's level, 0 to 7, with a bar under it
    GET /led/hint/2      a question mark and the rung of the hint ladder
    GET /led/letter/C    the solution's letter
    GET /led/think/0     three dots, while the model answers a student's question
    GET /led/face/0      the idle face

A tick, a cross, a hint or a letter stays for a few seconds, then the level
comes back. Nothing flashes.
"""
import time

import numpy as np
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge, Frame

ON = 7
HOLD = 4.0  # seconds a tick, a cross, a hint or a letter stays on

# 5x7 characters
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
}

# Whole 8x13 pictures
TICK = [".............",
        "...........#.",
        "..........##.",
        ".........##..",
        ".#......##...",
        ".##....##....",
        "..##..##.....",
        "...####......"]
CROSS = [".............",
         "...#.....#...",
         "....#...#....",
         ".....#.#.....",
         "......#......",
         ".....#.#.....",
         "....#...#....",
         "...#.....#..."]
FACE = [".............",
        "..###...###..",
        "..#.#...#.#..",
        "..###...###..",
        ".............",
        "...#.....#...",
        "....#####....",
        "............."]


THINK = [".............",
         ".............",
         ".............",
         ".##..##..##..",
         ".##..##..##..",
         ".............",
         ".............",
         "............."]


def picture(rows):
    grid = np.zeros((8, 13), dtype=np.uint8)
    for r, line in enumerate(rows):
        for c, pixel in enumerate(line):
            if pixel == "#":
                grid[r, c] = ON
    return grid


def text(chars, bar=0):
    """One or two 5x7 characters, with an optional bar on the bottom row."""
    grid = np.zeros((8, 13), dtype=np.uint8)
    left = 4 if len(chars) == 1 else 1
    for i, char in enumerate(chars):
        for r, line in enumerate(FONT[char]):
            for c, pixel in enumerate(line):
                if pixel == "#":
                    grid[r, left + 6 * i + c] = ON
    grid[7, :bar] = 3
    return grid


state = {"level": None, "until": 0.0, "shown": "face"}


def draw(grid):
    Bridge.call("draw", Frame(grid).to_board_bytes())


def rest():
    """What the matrix shows when nothing is happening: the level, or the face."""
    if state["level"] is None:
        draw(picture(FACE))
    else:
        draw(text(str(state["level"]), bar=state["level"] + 1))


def led(kind: str, value: str):
    hold = True
    if kind == "tick":
        draw(picture(TICK))
    elif kind == "cross":
        draw(picture(CROSS))
    elif kind == "level" and value in list("01234567"):
        state["level"] = int(value)
        hold = False
        rest()
    elif kind == "hint" and value in list("1234"):
        draw(text("?" + value))
    elif kind == "letter" and value.upper() in list("ABCDE"):
        draw(text(value.upper()))
    elif kind == "think":
        hold = False  # stays until the model has answered and the server sends the level again
        draw(picture(THINK))
    elif kind == "face":
        state["level"] = None
        hold = False
        rest()
    else:
        return {"error": "unknown picture"}
    state["shown"] = kind
    state["until"] = time.time() + HOLD if hold else 0.0
    return {"ok": True, "shown": kind}


def loop():
    """Go back to the level when a tick, a cross, a hint or a letter has been on long enough."""
    if state["until"] and time.time() > state["until"]:
        state["until"] = 0.0
        state["shown"] = "level"
        rest()
    time.sleep(0.2)


ui = WebUI()
ui.expose_api("GET", "/led/{kind}/{value}", led)
ui.expose_api("GET", "/status", lambda: state)

rest()
App.run(user_loop=loop)
