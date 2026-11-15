// The sketch only draws the frame that Python sends. Everything shown is decided in python/main.py.
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
