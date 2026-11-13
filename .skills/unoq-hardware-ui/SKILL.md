---
name: unoq-hardware-ui
description: Build the user interface of a Math on the Edge copilot on the Arduino UNO Q with Arduino App Lab. Covers the app layout (app.yaml, python/main.py, assets/, sketch/sketch.ino), a web page served by the web_ui brick for the student's input, the Bridge between Linux and the microcontroller, drawing letters, counts, and symbols on the board's 8x13 LED matrix, and calling the local model servers from the app. Use it when students want an App Lab app, a web page, or the LED matrix around their copilot. The datathon uses no external modules: the LED matrix is the only hardware output.
---

# A web page and the LED matrix for the copilot

The UNO Q has two halves. Linux (Qualcomm QRB2210) runs the model servers, the copilot, and the Python half of an App Lab app. The STM32 microcontroller runs the sketch, which drives the board's 8x13 LED matrix. The **Bridge** connects them with remote procedure calls.

In this datathon, teams use **no external modules**: no Modulino nodes, buttons, or sensors. Students interact through a **web page** served by the board, or the terminal, and the board answers on the **LED matrix**. Don't suggest extra hardware.

Ground truth for every API here: the official examples at <https://github.com/arduino/app-bricks-examples>, especially `bricks/arduino/web_ui/02_serve_webapp_and_api` and `core-and-foundational/02-led-matrix/02-led-matrix-frame`. When a detail is in doubt, find an example that does it and copy its pattern.

## The app

App Lab apps live in `/home/arduino/ArduinoApps/<app-name>/` on the board:

```text
app.yaml            name, description, icon, and bricks
python/main.py      runs on Linux
assets/             the web page, served by the web_ui brick
sketch/sketch.ino   runs on the microcontroller
sketch/sketch.yaml  the board platform and the pinned libraries
```

- Create one in App Lab, or on the board with `arduino-app-cli app new "math-matrix"`.
- Start and stop it from App Lab, or with `arduino-app-cli app start user:math-matrix` and `arduino-app-cli app stop user:math-matrix`. Read its output with `arduino-app-cli app logs /home/arduino/ArduinoApps/math-matrix --all`.
- Only one app runs at a time. The sketch compiles when the app starts, which can take a minute.
- `App.run()` must be the last line of `main.py`. Code after it never runs. Pass periodic work as `App.run(user_loop=loop)`.

## The web page

The `web_ui` brick serves the files in `assets/` on port 7000, and `ui.expose_api(method, path, function)` turns a Python function into an endpoint the page can `fetch`. Path parameters such as `{letter}` become the function's arguments.

Open it from the laptop:

- On the same network: `http://<board-ip>:7000`
- Over USB, or with Wi-Fi off: `adb forward tcp:7000 tcp:7000`, then <http://127.0.0.1:7000>
- Over SSH: `ssh -L 7000:127.0.0.1:7000 arduino@<board-ip>`, then <http://127.0.0.1:7000>

Port 7000 is the web_ui brick's. The datathon explorer uses 8000, and the model servers 8081 to 8083: don't reuse them.

## The Bridge

Python side: `Bridge` is a module-level object. Don't create one, and there are no decorators.

```python
from arduino.app_utils import App, Bridge

Bridge.call("draw", frame_bytes)    # call a function the sketch provides
Bridge.provide("name", function)    # let the sketch call Python
```

Sketch side:

```cpp
#include <Arduino_RouterBridge.h>

void setup() {
  Bridge.begin();
  Bridge.provide("draw", draw);     // Python calls it with Bridge.call("draw", ...)
}
```

Keep Bridge calls and API handlers short. A model call takes 5 to 30 seconds, so run it in a thread, show "thinking" on the matrix, and let the page ask for the result.

## The LED matrix

8 rows by 13 columns, with brightness 0 to 7 at the default `setGrayscaleBits(3)`. The simplest pattern, from the `02-led-matrix-frame` example: Python builds the frame with numpy and `Frame`, and the sketch only draws it. Everything you show is decided in Python.

What fits in 8x13: one 5x7 character (a letter A to E, a digit, `?`), two 5x7 characters with one column between them, a small tick or cross, a bar of up to 13 columns (a level, a timer, a vote count), or a few columns of bars side by side (five votes, one column pair each).

## A complete starting app: answer A to E on a web page, see it on the matrix

`app.yaml`:

```yaml
name: Math matrix
icon: 🧮
description: Answer A to E on a web page, and see the answer on the LED matrix
bricks:
  - arduino:web_ui
```

`sketch/sketch.yaml` (the LED matrix and the Bridge come with the board's core, so no libraries are listed, as in the official `02-led-matrix-frame` example):

```yaml
profiles:
  default:
    platforms:
      - platform: arduino:zephyr
    libraries:
default_profile: default
```

`sketch/sketch.ino`:

```cpp
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <vector>

Arduino_LED_Matrix matrix;

const uint8_t FRAME_SIZE = 8 * 13;
uint8_t frame[FRAME_SIZE] = {0};

void draw(std::vector<uint8_t> newFrame) {
  memcpy(frame, newFrame.data(), min(newFrame.size(), (size_t)FRAME_SIZE));
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  matrix.clear();
  Bridge.begin();
  Bridge.provide("draw", draw);
}

void loop() {
  matrix.draw(frame);
  delay(10);
}
```

`python/main.py`:

```python
import json
import threading
import urllib.request

import numpy as np
from arduino.app_bricks.web_ui import WebUI
from arduino.app_utils import App, Bridge, Frame

LLM = "http://127.0.0.1:8081"

# 5x7 characters, drawn in the middle of the 8x13 matrix
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
}

def show(char):
    grid = np.zeros((8, 13), dtype=np.uint8)
    for row, line in enumerate(FONT[char]):
        for col, pixel in enumerate(line):
            if pixel == "#":
                grid[row, 4 + col] = 7
    Bridge.call("draw", Frame(grid).to_board_bytes())

state = {"busy": False, "message": "Choose an answer."}

def work(letter):
    """Runs in a thread: put your copilot here, such as checking the answer or asking for a hint."""
    show("?")
    try:
        with urllib.request.urlopen(LLM + "/health", timeout=5) as response:
            state["message"] = f"You chose {letter}. Model server: {json.loads(response.read())}"
    except OSError as error:
        state["message"] = f"You chose {letter}. Model server unreachable: {error}"
    finally:
        show(letter)
        state["busy"] = False

def answer(letter: str):
    letter = letter.upper()
    if letter not in "ABCDE" or len(letter) != 1:
        return {"error": "choose A to E"}
    if state["busy"]:
        return {"error": "still working"}
    state["busy"] = True
    threading.Thread(target=work, args=(letter,), daemon=True).start()
    return {"ok": True}

ui = WebUI()
ui.expose_api("GET", "/answer/{letter}", answer)
ui.expose_api("GET", "/status", lambda: state)

show("?")
App.run()
```

`assets/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Math matrix</title>
  <style>
    body { font: 18px system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }
    button { font-size: 28px; width: 64px; height: 64px; margin: 4px; }
  </style>
</head>
<body>
  <h1>Math matrix</h1>
  <p id="problem">Your problem goes here.</p>
  <div id="letters"></div>
  <p id="status">Choose an answer.</p>
  <script>
    const status = document.querySelector("#status");
    for (const letter of "ABCDE") {
      const button = document.createElement("button");
      button.textContent = letter;
      button.onclick = async () => {
        const result = await (await fetch("/answer/" + letter)).json();
        status.textContent = result.error || "Thinking…";
      };
      document.querySelector("#letters").append(button);
    }
    setInterval(async () => {
      const state = await (await fetch("/status")).json();
      if (!state.busy) status.textContent = state.message;
    }, 1000);
  </script>
</body>
</html>
```

Keep the page in one file, or split it into `index.html`, `style.css`, and `app.js` as the official example does.

## Calling the copilot from the app

The model servers listen on `127.0.0.1:8081` and `127.0.0.1:8082`, outside App Lab. The starting app checks `/health` when the student answers, and shows the result on the page. Check it before you build on it. If the app can't reach the servers, find out how App Lab runs the app's Python on this board version before you change anything, and tell the student what you found.

To reuse the copilot code, call the servers over HTTP the way `copilot/client.py` does, with `urllib` and no new dependencies, or copy the modules you need into `python/`. Never call the model inside an API handler or a Bridge call: use a thread, and let the page poll `/status`.

## Without App Lab

The LED matrix needs an App Lab app, because the sketch must run on the microcontroller. A web page alone doesn't: `explorer/server.py` in the repository is a standard-library web server that runs with `python3`, and is a good starting point for a page that doesn't need the matrix.

## Rules

- **No external modules:** only the board, its LED matrix, and a web page or the terminal for input.
- **RAM:** App Lab, its containers, and both model servers share 3.6 GB. Check `free -m` with everything running. Don't add a brick that loads another model unless you've measured that it fits.
- **No flashing:** nothing on the matrix should flash more than three times a second.
- **Offline:** no brick, library, font, or script on the page that needs the internet at run time. Don't load anything from a CDN.
- **Keep `predict.py` independent** of the app. The official run doesn't use the matrix or the page.
