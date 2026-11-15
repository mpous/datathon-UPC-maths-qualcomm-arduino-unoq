# Cangur Coach: the Teach copilot

A maths coach that runs on the Arduino UNO Q, offline. A student answers Kangaroo problems on a web page served by the board. When they get one wrong, the coach doesn't give the answer: it offers a ladder of hints, starting with a similar, easier problem from M3Kang. The board's LED matrix shows a tick, a cross, the student's level, or the rung of the ladder.

> Written on 15 Nov 2026. Numbers marked *(board)* were measured on our UNO Q with `coach/measure.py`, which writes `results/teach-measure.json`.
>
> The same Coach is also a page of the team's combined web app: `python3 web3/server.py --host 0.0.0.0`, then open `/coach`.

## Why it works this way

We measured the board's language model before we designed anything (see [What we measured about the model](#what-we-measured-about-the-model)):

- On 862 M3Kang problems, Qwen3.5 0.8B gives the correct answer a probability of 20.6% on average. Guessing gives 20%.
- When we showed it a similar solved problem (RAG), it copied that problem's letter 42 times out of 50.

So the small model can't use a similar problem, but a student can. The coach gives the retrieval to the student, and keeps the model out of the loop: every step of the ladder is a lookup or a rule, and takes milliseconds.

## What the student sees

1. They type a name, and choose Catalan or English and a starting level (0 to 7, grades 5 to 12).
2. They answer A to E. The LED matrix shows a tick or a cross.
3. **Right at the first try:** the next problem is one level harder, and close to the last one.
4. **Wrong:** the page says "not yet", and never shows the answer. The student can try again or climb the ladder:

| Rung | What | Where it comes from | Time |
| --- | --- | --- | --- |
| 1 | A similar problem at a lower level, to solve first | The nearest neighbours in the bge-small embeddings | Milliseconds |
| 2 | The topic and a method | Keyword rules on the problem text, and a tip we wrote per topic | Milliseconds |
| 3 | A one-sentence idea from the model | Written ahead of time by Qwen3.5 0.8B, and checked in code | Milliseconds to show |
| 4 | The solution | The M3Kang label | Milliseconds |

5. If they needed the solution, the next problem is one level easier, on the same topic when there is one.

At any time before the solution, the student can also **ask the coach a question** in their own words. This is the only step that waits for the language model: about 20 to 30 seconds, while the LED matrix shows three dots. The model gets a coach's system prompt ("name the next step, don't calculate, never give the answer"). A system prompt isn't enough with a small model, so the code checks the reply before the student sees it. If it fails, the student gets the method tip for the topic instead, and the page says so. Asking counts as help: the level doesn't go up on that problem.

The student's progress stays in a SQLite file on the board (`data/teach_profile.db`). Nothing leaves the device.

## How it uses M3Kang

- **A bank of problems a student can solve from the page:** the 514 problems that need no figure and whose five options OCR could read, in Catalan and English (1,016 rows).
- **A difficulty map:** each problem has its level and its 40 nearest neighbours. "Easier and similar" is a lookup.
- **A multilingual bridge:** bge-small is an English embedding model, so the similarity always comes from the English text. A Catalan student gets the neighbours of the English twin (same `id`), shown in Catalan.
- **Topics:** M3Kang has no topic field. Keyword rules on the English text give one of eight topics, and every translation of the problem shares it.

## Run it

On the board, with the services from step 7 and the index from step 12.1:

```bash
cd ~/datathon-UPC-maths-qualcomm-arduino-unoq
python3 coach/build_bank.py            # once: about 50 seconds on the board
python3 coach/server.py --host 0.0.0.0
```

Open `http://<board-ip>:8000` on a laptop on the same network.

The model's hints (optional, about 17 seconds per hint):

```bash
python3 coach/make_hints.py --limit 120
```

The LED matrix (optional). Copy `coach/applab/` into an App Lab app and start it:

```bash
arduino-app-cli app new "cangur-face" -b arduino:web_ui
cp -r coach/applab/python coach/applab/sketch coach/applab/assets coach/applab/app.yaml ~/ArduinoApps/cangur-face/
arduino-app-cli app start user:cangur-face
```

The server calls the LED app at `http://127.0.0.1:7000`. If the app isn't running, the page works the same.

Check everything from your laptop, and measure:

```bash
python3 coach/check.py http://<board-ip>:8000 --ask   # 26 checks, as a student
python3 coach/check.py http://<board-ip>:8000 --ask --api=/api/coach   # the same, when web3/server.py serves it
python3 coach/measure.py                         # on the board
```

## What we measured

| What | Result |
| --- | --- |
| Time per step *(board)* | Start 2.2 ms, answer 0.5 ms, hint 0.2 ms, next problem 1.7 ms (medians). The worst call took 2.7 ms. |
| Problems with a similar problem at a lower level | 489 of 514 in English (95%), 477 of 502 in Catalan |
| Median similarity of that problem | 0.80, and it's 2 levels easier (median) |
| Same topic as the original | 296 of 513 (58%): the keyword topics are rough |
| Simulated student, always right up to level 3 and always wrong above it | Reaches level 3 in 3 problems, then stays between 3 and 4 |
| The same, for levels 1, 5 and 6 | Settles between its level and the next one in 1 to 3 problems |
| Same topic after a failure (simulated students) | 11/13 to 15/15 |
| A wrong answer reveals the solution | Never: `check.py` reads every reply |
| Model hints written ahead of time *(board)* | 120 (60 problems, Catalan and English), 16.8 s each (median) |
| Hints the code checks rejected | 24 of 120 (20%): 22 because the model calculated a new number, 2 because they gave the answer. English 21 of 61, Catalan 3 of 59. |
| Hints a person has read so far | 9 of 120, and 4 of those were rejected for a wrong method. **The other 111 have not been read yet.** |
| Live questions to the coach *(board)* | 2 asked while hints were being written: 23 s and 30 s. Both passed the checks. Too few to give a rate. |

## The model's hints: what the checks catch, and what they don't

A hint, or a live answer, is rejected in code when it contains the correct value or a letter, when it contains a number that isn't in the problem or in the student's question (the model calculated), or when it's cut off. `server.py --review` adds a page where a teacher reads each hint next to its problem and keeps or rejects it.

The checks can't tell whether the method is right. In our first hints, the model suggested "Pascal's theorem" for a problem about boxes in a cube. So the page labels this rung as an idea from the board's small model, and it comes after the two rungs that are always right. **Read the hints before a demo, and delete the wrong ones** (`DELETE FROM hints WHERE id = ...` in `data/teach.db`).

## What we measured about the model

All on the board, at temperature 0, with the baseline prompt unless noted.

| Experiment | Result |
| --- | --- |
| Baseline, Qwen3.5 0.8B, full validation set (562) | 22.6% (127/562). Always answering D gets 23.1%. |
| The same, practice set from the organisers (100, every letter correct 20 times) | 22% |
| RAG with 1 example (50 problems) | 14%, and 13 seconds slower. It copied the example's letter 42/50 times. |
| Probability the model gives the correct letter (862 problems) | 20.6% on average. Mean rank of the correct letter: 2.94 of 5 (3.0 is chance). |
| Correcting the letter bias with log probabilities, fitted on 300 train problems | 30.0% on train, 19.2% on validation: it overfits, because there's no signal to recover |
| Qwen3.5 2B Q4_0, practice set | 22%, at 17 seconds per problem. It answered B 87 times out of 100. |
| Qwen3.5 2B Q4_0, first 50 validation problems | 40%. On 145 problems, 31%: the first number was luck plus a taste for B. |
| One line of reasoning, then the letter (0.8B, practice set) | 26%, at 25 seconds per problem. Inside the margin of error (±9 points). |

None of these beat the baseline by more than the margin of error. The team's `predict.py` takes a different route, where the model writes a Python program (`copilot/reason.py`): that one isn't measured in this table.

## Limits

- The bank has no problems with figures, and none whose options OCR couldn't read.
- The topics are keyword rules. Only 58% of the first-rung problems share the original's topic.
- The level moves one step at a time, from one answer. A real student needs a slower, steadier estimate.
- The simulated students are deterministic. We haven't tested the coach with real students.
- The model's hints are checked for leaks, not for mathematical sense.

## Files

| File | What it does |
| --- | --- |
| `build_bank.py` | Builds `data/teach.db`: the problems and their neighbours |
| `core.py` | The hint ladder, the adaptive trainer, the topics, and the leak check |
| `server.py` | The web server. Standard library only. |
| `public/index.html` | The student's page, in Catalan and English |
| `coach.py` | The live question to the model: the system prompt and the request |
| `make_hints.py` | Writes and checks the model's hints ahead of time |
| `applab/` | The App Lab app that draws on the LED matrix |
| `check.py` | Checks a running server from start to finish |
| `measure.py` | Speed, first-rung quality, hints, and simulated students |

`data/teach.db` holds M3Kang problem text: don't commit it. `.gitignore` already excludes `data/` and `*.db`.
