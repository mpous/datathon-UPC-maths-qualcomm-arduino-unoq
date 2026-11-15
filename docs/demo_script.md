# 3-minute demo script (draft)

**Setup before the slot:** board in the owl, powered from a USB-C power bank, services up (`curl -s 127.0.0.1:8081/health`). Laptop on `adb forward tcp:8000 tcp:8000`, browser full screen on http://127.0.0.1:8000. Pre-open the kangaroo problem in Catalan, lvl-0_2026_2_cat, about 1 minute before, so the board has already solved it. Backup: a screen recording of the same flow.

| Time | Who / what | Say (roughly) | Show |
| --- | --- | --- | --- |
| 0:00–0:20 | Hook | "This owl is a maths tutor. Everything runs on this €-board, offline: no cloud, no Wi-Fi." | Owl boot animation; unplug the Wi-Fi dongle / show airplane mode |
| 0:20–0:35 | Teach: the student is stuck | "Laia, 11, gets this Kangaroo problem in Catalan. She guesses 11." | Click C (11): ✗, the owl looks worried |
| 0:35–1:05 | Hint ladder | "The owl never gives the answer. Hint 1 is a strategy question. Hint 2 explains the method, and the board worked that method out itself, by writing and running a small program while Laia was reading." | Hint 1 (strategy), hint 2 (purple "worked out by the board"); the eyes switch to the hint look |
| 1:05–1:20 | She gets it | "Now she counts in pairs of jumps…" | Click B (10): ✓, happy owl eyes |
| 1:20–1:35 | Practice | "Then she practises a similar problem at her level." | "Try a similar one" → 3 related problems |
| 1:35–2:15 | Reason | "For the exam half, the same trick: the 0.8B model can't think long on this chip, but it can write code. Letter probabilities + code + balancing: 35% on the 100 practice problems, against 20% chance and 22% for the organisers' baseline. Bigger models are too slow here: the 4B model takes over 60 s just to read a problem." | Results chart (one slide or the README table) |
| 2:15–2:45 | What we learned | "We also fine-tuned the model on the whole bank: it learned all 1,747 answers by heart, and stayed at chance on new problems. Small models memorise; they don't learn maths from letters. That's why our tutor grounds every hint in something it computed." | One line on screen: memorised 24/24, unseen 22% |
| 2:45–3:00 | Close | "Offline, bilingual, never gives the answer away, and the owl shows how it feels about your work." | Owl idle blink |

**Questions to expect**
- *Does it work on a problem I make up?* Yes: "type your own". Hint 1 is always a strategy hint; hints 2–3 come from the board's own solution when its program matches an option.
- *How do you avoid giving away the answer?* A guard drops any sentence that names the right letter, says "the answer is", or states an option's value as a result.
- *Why not a bigger model?* Measured on the board: 2B writes 2.2 tokens/s, 4B 1.1. Reading one problem takes the 4B ~68 s.
- *Is the 35% real?* It's measured on 100 rows (50 problems, two languages), so ±~9 points. We picked the method among ~10 variants, so expect a bit less on the real test.
