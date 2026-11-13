---
name: unoq-board
description: Operate the Arduino UNO Q 4 GB used in the Math on the Edge datathon. Connect over SSH or adb, check and restart the llama.cpp model services, watch RAM and disk, and fix common failures. Use it whenever a command must run on the board, a model server doesn't answer, the board runs out of memory, or the connection drops.
---

# Operate the Arduino UNO Q

The board runs Debian Linux on a Qualcomm QRB2210 (4 Arm cores, 3.6 GB of RAM usable), next to an STM32 microcontroller. Students work from a laptop. Every command you give must say where it runs: **on the board** or **on the laptop**.

## Connect

- **SSH, over Wi-Fi:** `ssh arduino@<board-ip>`. The IP is in App Lab, or `hostname -I` on the board. The password is the one set in App Lab.
- **adb, over USB (fallback):** `adb shell`, which logs in as `arduino`. Use it when SSH refuses the connection, or when Wi-Fi is off.
- With more than one board on USB, pick one: `export ANDROID_SERIAL=<serial>` (from `adb devices`). In zsh, don't store a command with arguments in a variable and run it as `$A shell`: zsh doesn't split it.
- Copy files: `scp file arduino@<ip>:~/datathon-UPC-maths-qualcomm-arduino-unoq/data/`, or `adb push file /home/arduino/datathon-UPC-maths-qualcomm-arduino-unoq/data/`.
- Open a web page from the board: `ssh -L 8000:127.0.0.1:8000 arduino@<ip>`, or `adb forward tcp:8000 tcp:8000`, then <http://127.0.0.1:8000>.

The repository lives in `~/datathon-UPC-maths-qualcomm-arduino-unoq` on the board, and every Python command runs from that folder.

## The model services

| Service | Port | Model | Unit |
| --- | --- | --- | --- |
| Language model | 8081 | Qwen3.5 0.8B Q8_0 (835 MB) | `math-llm` |
| Embeddings | 8082 | bge-small-en-v1.5 Q8_0 (37 MB, 384 dimensions) | `math-embed` |
| Vision (optional, by hand) | 8083 | Qwen3.5 0.8B with `--mmproj` | none |

Both servers listen on `127.0.0.1` only. All the settings are in `config.env`, which the Python code and the scripts in `board/` read.

Check them, on the board:

```bash
systemctl status math-llm math-embed --no-pager
curl -s http://127.0.0.1:8081/health
curl -s http://127.0.0.1:8082/health
journalctl -u math-llm -n 50 --no-pager
```

Restart them with `sudo systemctl restart math-llm math-embed`. After changing a service file: `sudo systemctl daemon-reload` first.

## Memory: the most common failure

The board has 3.6 GB for everything: Debian, App Lab, both model servers, and your code.

- Every `llama-server` must keep `--parallel 1 --cache-ram 0`. The language model also uses `--ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0`. Without them, the server allocates several slots or a prompt cache and the kernel kills it.
- If a server disappears, look for the OOM killer: `journalctl -k | grep -i "out of memory"`.
- Check RAM with `free -m` while everything runs, before adding anything new: a vision server, an App Lab app, or a Docker brick.
- Don't start a second server on a port that's in use. `couldn't bind HTTP server socket` means one already runs: `pgrep -a llama-server`.
- Stop servers you started by hand with `Ctrl+C`, or `pkill -f "port 8083"` for one port. Don't kill processes you didn't start, and don't stop other people's servers.

## Speed

Measured on the board: the model reads about 11 tokens per second and writes about 6. A one-letter answer takes about 9 seconds, and 2 RAG examples take it to about 30. The limit is 60 seconds per problem. Before you suggest a longer prompt, estimate its tokens and the time they cost.

## Other problems

| Symptom | Fix |
| --- | --- |
| `ssh: connect to host … port 22: Connection refused` | Empty SSH host keys. Connect with adb and run `sudo ssh-keygen -A && sudo systemctl restart ssh`. |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | On the laptop: `ssh-keygen -R <ip>`. |
| `apt` or downloads fail with certificate or time errors | The clock is wrong. Check `timedatectl`. |
| SSH drops when Wi-Fi goes off | Expected. Use adb. |
| `predict.py` answers `D` with status `timeout` | The prompt is too long. Fewer RAG examples, or a shorter prompt. |
| The disk is full | `df -h`. Old models in `~/models` and Docker images (`arduino-app-cli system cleanup`) take the most space. |

## Rules

- Never guess a `sudo` password. Ask the student to type it.
- Don't turn the board off by pulling the power while it writes. Run `sudo poweroff` and wait.
- Everything must work with the network off. Never add code that downloads at run time.
