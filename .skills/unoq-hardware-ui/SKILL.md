---
name: unoq-hardware-ui
description: Build the physical side of a Math on the Edge copilot on the Arduino UNO Q with Arduino App Lab. Covers the app layout (app.yaml, python/main.py, sketch/sketch.ino, sketch.yaml), the Bridge between Linux and the microcontroller, drawing letters and counts on the 8x13 LED matrix, reading Modulino Buttons, and calling the local model servers from the app. Use it when students want buttons, lights, sensors, or an App Lab app around their copilot.
---

# Buttons, lights, and App Lab apps for the copilot

The UNO Q has two halves. Linux (Qualcomm QRB2210) runs the model servers, the copilot, and the Python half of an App Lab app. The STM32 microcontroller runs the sketch, which drives the LED matrix and the Modulino nodes. The **Bridge** connects them with remote procedure calls.

Ground truth for every API here: the official examples at <https://github.com/arduino/app-bricks-examples>. When a detail is in doubt, find an example that does it and copy its pattern.

## The app

App Lab apps live in `/home/arduino/ArduinoApps/<app-name>/` on the board:

```text
app.yaml            name, description, icon, and bricks
python/main.py      runs on Linux
sketch/sketch.ino   runs on the microcontroller
sketch/sketch.yaml  the board platform and the pinned libraries
```

- Create one in App Lab, or on the board with `arduino-app-cli app new "math-buttons"`.
- Start and stop it from App Lab, or with `arduino-app-cli app start user:math-buttons` and `arduino-app-cli app stop user:math-buttons`. Read its output with `arduino-app-cli app logs /home/arduino/ArduinoApps/math-buttons --all`.
- Only one app runs at a time. The sketch compiles when the app starts, which can take a minute.
- `App.run()` must be the last line of `main.py`. Code after it never runs. Pass periodic work as `App.run(user_loop=loop)`.

## The Bridge

Python side: `Bridge` is a module-level object. Don't create one, and there are no decorators.

```python
from arduino.app_utils import App, Bridge

def on_button(index: int):          # the sketch calls this with Bridge.notify("button", i)
    print("button", index)

Bridge.provide("button", on_button)
Bridge.call("draw", frame_bytes)    # call a function the sketch provides
```

Sketch side:

```cpp
#include <Arduino_RouterBridge.h>

void setup() {
  Bridge.begin();
  Bridge.provide("draw", draw);     // Python calls it with Bridge.call("draw", ...)
}
// Bridge.notify("button", 2);     fire and forget, to Python
// Bridge.call("name", x).result(y) waits for Python, and returns false on failure
```

Keep Bridge handlers short. A model call takes 5 to 30 seconds, so run it in a thread, and show "thinking" on the matrix meanwhile.

## The LED matrix

8 rows by 13 columns, with brightness 0 to 7 at the default `setGrayscaleBits(3)`. The simplest pattern, from the `02-led-matrix-frame` example: Python builds the frame, and the sketch only draws it.

## Modulino Buttons

Three buttons with LEDs, on the Qwiic connector. On the UNO Q, start the bus with `Modulino.begin(Wire1)`. Use `buttons.update()`, which is true when something changed, then `buttons.isPressed(i)` for i 0 to 2, and `buttons.setLeds(a, b, c)`. Check these names against the `Arduino_Modulino` examples for the installed version.

Five answers with three buttons: button 0 moves left, button 1 moves right, and button 2 confirms. The matrix shows the selected letter.

## A complete starting app: choose A to E with the buttons

`sketch/sketch.yaml` (versions from the official `home-climate-monitoring-and-storage` example; copy newer ones from a recent example if the build can't find a library):

```yaml
profiles:
  default:
    platforms:
      - platform: arduino:zephyr
    libraries:
      - Arduino_Modulino (0.7.0)
      - dependency: ArduinoGraphics (1.1.4)
      - dependency: Arduino_HS300x (1.0.0)
      - dependency: Arduino_LPS22HB (1.0.2)
      - dependency: Arduino_LSM6DSOX (1.1.2)
      - dependency: Arduino_LTR381RGB (1.0.0)
      - dependency: STM32duino VL53L4CD (1.0.5)
      - dependency: STM32duino VL53L4ED (1.0.1)
default_profile: default
```

`sketch/sketch.ino`:

```cpp
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_Modulino.h>
#include <vector>

Arduino_LED_Matrix matrix;
ModulinoButtons buttons;

const uint8_t FRAME_SIZE = 8 * 13;
uint8_t frame[FRAME_SIZE] = {0};

void draw(std::vector<uint8_t> newFrame) {
  memcpy(frame, newFrame.data(), min(newFrame.size(), (size_t)FRAME_SIZE));
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  matrix.clear();
  Modulino.begin(Wire1);
  buttons.begin();
  Bridge.begin();
  Bridge.provide("draw", draw);
}

void loop() {
  if (buttons.update()) {
    for (int i = 0; i < 3; i++) {
      if (buttons.isPressed(i)) Bridge.notify("button", i);
    }
  }
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
from arduino.app_utils import App, Bridge, Frame

LLM = "http://127.0.0.1:8081"

# 5x7 letters, drawn in the middle of the 8x13 matrix
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

letters = "ABCDE"
selected = 0
busy = False

def on_answer(letter):
    """Runs in a thread: put your copilot here, such as checking the answer or asking for a hint."""
    global busy
    show("?")
    try:
        with urllib.request.urlopen(LLM + "/health", timeout=5) as response:
            print("model server:", json.loads(response.read()))
        print("the student answered", letter)
    except OSError as error:
        print("model server unreachable:", error)
    finally:
        show(letter)
        busy = False

def on_button(index: int):
    global selected, busy
    if busy:
        return
    if index == 0:
        selected = (selected - 1) % 5
    elif index == 1:
        selected = (selected + 1) % 5
    else:
        busy = True
        threading.Thread(target=on_answer, args=(letters[selected],), daemon=True).start()
        return
    show(letters[selected])

Bridge.provide("button", on_button)
show(letters[selected])
App.run()
```

## Calling the copilot from the app

The model servers listen on `127.0.0.1:8081` and `127.0.0.1:8082`, outside App Lab. The starting app checks `/health` when you confirm an answer: look for `model server:` in the app's logs before you build on it. If the app can't reach the servers, find out how App Lab runs the app's Python on this board version before you change anything, and tell the student what you found.

To reuse the copilot code, call the servers over HTTP the way `copilot/client.py` does, with `urllib` and no new dependencies, or copy the modules you need into `python/`. Never call the model from inside a Bridge handler: use a thread.

## Rules

- **RAM:** App Lab, its containers, and both model servers share 3.6 GB. Check `free -m` with everything running. Don't add a brick that loads another model unless you've measured that it fits.
- **No flashing:** nothing on the matrix should flash more than three times a second.
- **Offline:** no brick or library that needs the internet at run time.
- **Keep `predict.py` independent** of the app. The official run doesn't use the hardware.
