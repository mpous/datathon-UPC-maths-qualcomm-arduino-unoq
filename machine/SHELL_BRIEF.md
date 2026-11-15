# Brief for the 3D-printed "professor" shell (context for the 3D-modelling agent)

Written 14 Nov 2026, 17:45, by the Qualcomm workstream. Facts marked *verify* were not measured.

## The product
- A maths copilot that runs fully offline on an **Arduino UNO Q** (Datathon FME 2026, Qualcomm challenge
  "Math on the Edge"). It teaches Kangaroo-contest maths: hints, adaptive practice. The student answers A–E on a
  web page served by the board; the board answers on its **built-in 8×13 LED matrix** (tick/cross, letter, level, eyes).
- Idea: the shell is a small **"professor"** character, and the **LED matrix is its face**, visible through a window.
- Audience: M3Kang levels 0–7 = school grades 5–12, ages ~10–18, mostly secondary. Friendly but not babyish
  (owl or robot professor fits ages 10–14 without putting off 16-year-olds).

## Hard constraints
- **No extra electronics.** Organisers allow only the board's own LED matrix as hardware output (no Modulino,
  no external buttons/sensors). A passive shell is fine.
- **Board:** Arduino UNO form factor, about **68.6 × 53.4 mm** (*verify with calipers*), standard UNO mounting holes
  (*verify*). The 8×13 LED matrix is on the top face (*measure its position and size*).
- **Access needed:** the USB-C port (power + data, used during the demo), and ideally the board's reset/boot area.
  Leave room for the cable's plug body.
- **Heat:** the Qualcomm QRB2210 runs all 4 cores at 100% for 5–30 s per answer, repeatedly. Add vents
  (top and sides); don't enclose it tightly; PLA near the SoC should not touch it.
- **Demo:** live 3-minute pitch on Sunday 15 Nov, 14:00, with the board inside the shell. The board must be easy
  to take out if something fails.

## Timing
- Printing a small shell: estimate 3–6 h on a typical FDM printer at 0.2 mm. Final STL needed **Saturday night**
  so the print is done Sunday morning.

## Tooling
- Laptop: Arch Linux (Omarchy). OpenSCAD is in the Arch repos (`sudo pacman -S openscad`, 2021.01); not installed yet.
  The 3D agent writes OpenSCAD, renders STL + PNG previews headless, and iterates. A friend slices and prints.

## Update 19:45: direction change (from the user, after talking to a supervisor)
- The jury weighs the **demo, design and story** far more than the accuracy number. The shell now matters more:
  it should look like a finished product, not a case.
- **Demo flow the shell must support** (3 minutes, live): a laptop browser shows a page served by the board over
  the USB-C cable; a problem image is dropped in; the board retrieves two similar solved problems, the on-board
  model answers with a letter and a short explanation; a second page shows statistics.
- **The LED matrix is the professor's face and the only on-device display.** Planned states: idle eyes / blinking,
  "thinking" animation while the model runs (5-45 s), the answer letter A-E, tick or cross. So the face window must
  show the whole 8x13 matrix, ideally behind a thin diffuser (0.4-0.6 mm white PLA or paper) so the LEDs read as
  soft pixels. The matrix is the focal point of the character.
- The USB-C cable stays plugged in during the demo (power + data): design the cable exit so it looks intentional
  (e.g. out of the back/base), and so the figure stands stable with the cable attached.
- The team has **two boards**; a second shell is optional.
- Character idea: a small "professor" (owl or robot), ages ~10-16, friendly but not babyish. Team name: TIC's Friends.
