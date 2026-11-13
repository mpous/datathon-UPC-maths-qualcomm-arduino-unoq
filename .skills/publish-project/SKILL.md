---
name: publish-project
description: Prepare a Math on the Edge team's final deliverables, a public GitHub repository and a step-by-step write-up on Arduino Project Hub, and check them before they're shared. Use it when students write their README, document the architecture, results, and error analysis, prepare the Project Hub project, or are about to make their repository public.
---

# Publish the project

Every team publishes two things, and sends both links to the organizers:

1. **A public GitHub repository** with the code and the documentation
2. **A step-by-step project on [Arduino Project Hub](https://projecthub.arduino.cc/)**

Both must let someone with a fresh Arduino UNO Q 4 GB rebuild the copilot, and understand what the team measured.

## Before anything is public: the M3Kang check

M3Kang is licensed for research use only. Nothing derived from its problems goes into the repository or the write-up. Run this from the repository folder, and fix every line it prints:

```bash
git ls-files | grep -E '^data/' | grep -v -E '^data/(sample_problems\.jsonl|README\.md)$'
git ls-files | grep -E '\.(db|gguf|jsonl|png)$' | grep -v '^data/sample_problems\.jsonl$'
git log --all --name-only --format= | sort -u | grep -E '^data/(train|val)\.jsonl$|^data/images/|\.db$'
```

- The first two list tracked files that shouldn't be there. Remove them with `git rm --cached`.
- The third finds them in the history. If it prints anything, removing the file now isn't enough: the history still holds it. Tell the team, and rewrite the history before the repository goes public, or start a fresh repository.
- Also check results files: the `eval-*.csv` files only hold ids and letters, but don't add the problem text to them.
- Link to the [dataset card](https://huggingface.co/datasets/qualcomm/M3Kang) instead, and cite the paper: Torres-Camps et al., 2026, [arXiv:2601.16218](https://arxiv.org/abs/2601.16218).

Never commit secrets: tokens, Wi-Fi passwords, or the board's password.

## The GitHub repository

The code:

- Everything that runs on the board, with `config.env` pinning the models (repository, revision, file, SHA256) and llama.cpp (commit)
- The service files, and the App Lab app if there is one
- A license for the team's own code, such as MIT, and the credits for what they reused

The README, in this order:

1. **What it does**, in two or three sentences, with a photo or a short video of it working on the board
2. **The architecture**: what runs on Linux, what runs on the microcontroller, how the Bridge connects them, which model servers it calls, and how it uses M3Kang. A diagram helps.
3. **How to replicate it**: start from a board set up with steps 0 to 12 of the datathon README, and list every further step, with the commands and what you should see
4. **Results**: a table from `results/ablations.csv`, each experiment against the baseline (22.5% on 40 English problems with OCR options), with accuracy, mean and worst latency, and the number of problems
5. **Error analysis** by topic, language, and difficulty (level), with the number of problems next to each accuracy, and a few wrong answers explained
6. **What didn't work**, and what the team would try next
7. **The team**

Checks before sharing:

- Every number in the README comes from a run in `ablations.csv`, on stated problems. Results on 50 problems or fewer say so.
- Clone the repository into a new folder and follow the README. Fix every step that fails.
- Every link works.

## The Arduino Project Hub write-up

Sign in at <https://projecthub.arduino.cc/> with an Arduino account, and create a new project. A good example of the format: [How to Run High-Performance LLMs Locally on the Arduino UNO Q](https://projecthub.arduino.cc/marc-edgeimpulse/running-local-llms-and-vlms-on-the-arduino-uno-q-with-yzma-74e288).

Sections:

1. **Introduction:** who the copilot helps, why it runs offline, and a photo or video of it working
2. **Components and apps:** the Arduino UNO Q 4 GB, any Modulino nodes, Arduino App Lab, llama.cpp, Qwen3.5 0.8B, bge-small-en-v1.5
3. **Architecture:** the diagram from the README, explained
4. **Step by step:** from a fresh board to the demo. One step per section, each with its commands and what you should see. Link to the GitHub repository for the full code, instead of pasting all of it.
5. **Results and error analysis**
6. **What we learned**, and what's next

Use photos and screenshots the team made. Don't upload M3Kang data. To show an example problem, check the license on the dataset card first.

## Writing

Write for a student who wasn't at the datathon. Short sentences, one idea each. Say what each command does and what you should see. Report what didn't work as plainly as what did.
