# Datathon FME 2026: Qualcomm challenge

<img width="1526" height="927" alt="UPC-datathon" src="https://github.com/user-attachments/assets/daa7be34-b91a-4703-9581-7b5142f75d91" />

## Math on the Edge: Build a Math Copilot with Arduino and M3Kang

### The challenge

Mathematical proficiency in Catalonia is declining in international assessments such as PISA. Teachers are stretched, and many students feel left behind by one-size-fits-all classrooms. AI can help, but only if it guides reasoning instead of doing the homework, and only if student data stays private.

[M3Kang](https://huggingface.co/datasets/qualcomm/M3Kang) is a multilingual dataset of thousands of problems from the [Kangaroo Math Competition](https://mathkangaroo.org/mks/), across many languages and difficulty levels. It is a perfect raw material for a learning companion: a bank of problems to practise with, a library of examples to retrieve from, a map of mathematical topics and a benchmark to measure against.

The Arduino UNO Q (4 GB) has two brains on one board: a Linux on a quad-core Arm CPU, the Qualcomm QRB2210, which can run small language models, embedding models and retrieval offline. And a real-time microcontroller that drives LEDs, buttons, motion sensors and cameras. Nothing leaves the device.

The challenge of the Datathon FME 2026 is:

> Design and build a Math copilot that runs entirely on the Arduino UNO Q and uses M3Kang in an innovative way to help students learn to reason mathematically.

Your copilot must do one of these two things:

* **Teach**: It must turn that ability into an experience that sparks curiosity and guides the student without giving away the answer, for example through hints, adaptive practice, error analysis, physical interaction or collaboration.
* **Reason**: When given a Kangaroo-style problem, it must be able to choose the correct answer. Organizers will measure this objectively on a hidden test set.

How you use M3Kang is up to you. It can be a retrieval knowledge base, a training set, a source of problem embeddings, a difficulty map, a multilingual bridge, or something nobody has thought of yet. The most original uses will score highest.

Take into account that the [Arduino UNO Q board](https://store.arduino.cc/pages/uno-q) is slow for this type of work, but it's capable. It only reads about 11 tokens per second and writes about 5 tokens per second. Every word you put into a prompt costs time. Retrieval and embeddings cost a fraction of a second, but generation costs tens of seconds. Great solutions measure these trade-offs and design around them.

#### Deliverables

* The project and source code documented in an open Github repository and at the [Arduino Project Hub](https://projecthub.arduino.cc/) with the architecture, experiences, how to replicate the project, error analysis by topic, language and difficulty
* A live demo and a 3-minute pitch on the board
 
#### References:
* [Generative AI at the Edge with the UNO Q and its RAG](https://mjrovai.github.io/genai-uno-q/content/rag/rag.html) at the Edge chapter (Marcelo Rovai)
* [How to Run High-Performance LLMs Locally on the Arduino UNO Q](https://projecthub.arduino.cc/marc-edgeimpulse/running-local-llms-and-vlms-on-the-arduino-uno-q-with-yzma-74e288)
* [qualcomm/M3Kang (dataset and paper)](https://huggingface.co/datasets/qualcomm/M3Kang)


### The repository

This repository sets up what every team must run on the Arduino UNO Q (4 GB) before the datathon starts: a small language model that answers M3Kang math problems offline, an embedding model for retrieval, and the scripts to measure, test, and freeze your submission.

Follow the steps in order. Each one ends with a check, so you know it worked before you move on.

By the end, you'll have:

- `llama.cpp` built on the board by hand, at a pinned commit
- `Qwen3.5 0.8B` (the language model) and `bge-small-en-v1.5` (the embedding model) downloaded and verified
- A `hello world` with each model, so you know what the servers do
- Both models running as services that start when the board boots
- `predict.py`, which answers a file of problems with one letter each, A to E
- Your `M3Kang` training and validation sets, and the baseline accuracy you need to beat
- A test that runs with the network off

## What you need

- An Arduino UNO Q with 4 GB of RAM, a USB-C cable, and a USB-C power supply (5 V, 3 A). You will need to update it.
- [Arduino App Lab](https://bit.ly/arduino-applab) to download the latest Arduino UNO Q versions.
- A laptop with Python 3.10 or later, Git, and [Arduino App Lab](https://www.arduino.cc/en/software/#app-lab-section) installed
- A Wi-Fi network that the board and the laptop share, with Internet access

## The steps at a glance

| Step | Where | What | Time |
| --- | --- | --- | --- |
| [0. Connect to the board](#step-0-connect-to-the-board) | Laptop | First setup in App Lab, then SSH | 15 min |
| [1. Check the board](#step-1-check-the-board) | Board | Memory, disk, clock, internet | 2 min |
| [2. Install the build tools](#step-2-install-the-build-tools) | Board | `sudo apt-get install` | 5 min |
| [3. Build llama.cpp](#step-3-build-llamacpp) | Board | `git fetch`, `cmake` | 30 min |
| [4. Download the models](#step-4-download-the-models) | Board | `wget`, `sha256sum` | 5 min |
| [5. Hello world: language model](#step-5-hello-world-with-the-language-model) | Board | `llama-server`, `curl` | 10 min |
| [6. Hello world: embeddings](#step-6-hello-world-with-the-embedding-model) | Board | `llama-server --embedding` | 5 min |
| [7. Run as services](#step-7-run-both-models-as-services) | Board | `systemctl` | 5 min |
| [8. First test](#step-8-get-the-datathon-code-and-run-the-first-test) | Board | `git clone`, `predict.py` | 5 min |
| [9. Prepare M3Kang](#step-9-prepare-m3kang-on-your-laptop) | Laptop | `prepare_m3kang.py` | 30 min |
| [10. Copy the data](#step-10-copy-the-data-to-the-board) | Laptop | `scp` | 1 min |
| [11. Measure the baseline](#step-11-measure-the-baseline) | Board | `eval.py` | 10 min |
| [12. Try retrieval](#step-12-try-retrieval-rag) | Board | `build_index.py`, `--rag` | 15 min |
| [Optional: explorer](#optional-explore-the-problems-in-your-browser) | Board, in a browser | `explorer/server.py` | 10 min |
| [13. Test offline](#step-13-test-offline-like-the-jury) | Board, over USB | `check_offline.sh` | 5 min |
| [14. Freeze](#step-14-freeze-your-submission) | Board | `make_freeze.sh` | 2 min |

Steps 1 to 8 are the minimum every team must have working on the board. Each command is shown in full, with what it does and what you should see.

Every code block holds only what you type: copy it and paste it into the terminal. Commands run on the board, unless the text says **On your laptop**. When there's output to check, it's in a separate block after **You should see**.

---

## Step 0: Connect to the board

The UNO Q runs Debian Linux on its Qualcomm QRB2210 processor. You'll work in a terminal on it, over SSH.

### 0.1 First setup in App Lab

1. Connect the board to your laptop with the USB-C cable.
2. Open [Arduino App Lab](https://bit.ly/arduino-applab). It finds the board and starts the first setup.
3. Give the board a name, set a password for the `arduino` user, and connect it to your Wi-Fi network. Use the password `opensource`.
4. **Let App Lab install any updates it offers, and wait for the board to restart**. This may take some minutes.

Write the password down. You will need it for SSH and for `sudo`.

### 0.2 Find the board's IP address

In App Lab, the board's details show its IP address. Or, from the board's terminal in App Lab, run:

```bash
hostname -I
```

The first address, such as `192.168.1.131` (e.g.), is the one you want.

### 0.3 Connect over SSH

On your laptop:

```bash
ssh arduino@192.168.1.131
```

Type `yes` the first time, then your password. You should see a prompt like `arduino@name-of-your-board:~$`.

### 0.4 If SSH doesn't work, connect over USB with adb (fallback)

The board also accepts `adb`, the Android Debug Bridge, over the USB-C cable. App Lab uses it, and you'll need it in step 13, when Wi-Fi is off. Install it with [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), or `brew install --cask android-platform-tools` on macOS.

On your laptop, list the boards connected over USB:

```bash
adb devices
```

You should see your board's serial number:

```text
List of devices attached
2663959333      device
```

Then open a shell on the board:

```bash
adb shell
```

`adb shell` logs you in as `arduino`. If more than one board is connected, pick one with `adb -s <serial> shell`.

### 0.5 Turning the board off

Always shut down from the terminal before you unplug the board. Pulling the power can corrupt the files on it.

```bash
sudo poweroff
```

---

## Step 1: Check the board

Before you install anything, check that the board has what the next steps need. These commands only read: they change nothing.

### 1.1 Memory and disk

```bash
free -h
```

You should see:

```text
               total        used        free      shared  buff/cache   available
Mem:           3.6Gi       480Mi       2.8Gi        38Mi       505Mi       3.1Gi
Swap:          1.8Gi          0B       1.8Gi
```

```bash
df -h ~
```

You need about 3.6 GB of memory in `total`. In the `df` output, you need at least 2 GB in `Avail`. llama.cpp takes about 350 MB once it's built, the models take 870 MB, and the packages take a few hundred MB more.

### 1.2 The clock

```bash
timedatectl | grep synchronized
```

You should see:

```text
System clock synchronized: yes
```

If it says `no`, the board has no internet yet, and `apt` and HTTPS downloads will fail with certificate errors. Check the Wi-Fi in App Lab.

### 1.3 Internet access

```bash
curl -sI https://huggingface.co | head -1
```

You should see:

```text
HTTP/2 200
```

You need internet for steps 2 to 4. After that, everything runs offline.

---

## Step 2: Install the build tools

### 2.1 Update the package list

```bash
sudo apt-get update
```

`sudo` asks for the password you set in App Lab.

### 2.2 Install the packages

```bash
sudo apt-get install -y build-essential cmake git pkg-config libssl-dev curl wget ca-certificates python3 sqlite3 jq
```

| Package | Why you need it |
| --- | --- |
| `build-essential` | The C and C++ compilers (`gcc`, `g++`) and `make` |
| `cmake` | Configures the llama.cpp build |
| `git` | Downloads llama.cpp and this repository |
| `pkg-config`, `libssl-dev` | Let llama.cpp download over HTTPS |
| `curl`, `wget`, `ca-certificates` | Download files and talk to the model servers |
| `python3`, `sqlite3` | Run the datathon code and store the retrieval index |
| `jq` | Read the JSON answers from the servers |

**If `apt` says a package "is not installable"** (we saw `cmake` failing on `librhash1`, and `libc6-dev` on `rpcsvc-proto`), the package list was downloaded incompletely. Delete it, download it again, and repeat 2.2:

```bash
sudo rm -rf /var/lib/apt/lists/*
sudo apt-get clean
sudo apt-get update
sudo apt-get install -y build-essential cmake git pkg-config libssl-dev curl wget ca-certificates python3 sqlite3 jq
```

### 2.3 Check

```bash
gcc --version | head -1
cmake --version | head -1
python3 --version
```

You should see:

```text
gcc (Debian 14.2.0-19) 14.2.0
cmake version 3.31.6
Python 3.13.5
```

Your version numbers may be slightly different. What matters is that each command answers.

---

## Step 3: Build llama.cpp

[llama.cpp](https://github.com/ggml-org/llama.cpp) runs language models on a CPU. It's the engine for both models, and it's what you'll build here.

### 3.1 Download the source at the pinned commit

Every team uses the same llama.cpp commit, `2cbe0ec`, so results compare fairly. These commands download only that commit (about 40 MB), not the project's whole history:

```bash
mkdir -p ~/llama.cpp
cd ~/llama.cpp
git init
git remote add origin https://github.com/ggml-org/llama.cpp.git
git fetch --depth 1 origin 2cbe0ec429b849a88664e0f62388fc92a5abd699
git checkout FETCH_HEAD
```

**Check:**

```bash
git log -1 --format=%h
```

You should see:

```text
2cbe0ec
```

### 3.2 Configure the build

```bash
cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
```

- `-B build` puts the build files in `~/llama.cpp/build`.
- `-DGGML_NATIVE=ON` optimizes for this processor, including its NEON vector instructions.
- `-DCMAKE_BUILD_TYPE=Release` turns on the compiler optimizations. Without it, the models run several times slower.

### 3.3 Compile

```bash
cmake --build build --config Release -j4 --target llama-server llama-cli
```

- `-j4` uses all four cores.
- `--target llama-server llama-cli` builds only the two programs you need, not the dozens of examples and tests.

This took about 30 minutes on our board. Leave it running.

**If the SSH session drops during the build**, the build stops. Connect again, go back to `~/llama.cpp`, and run the same command: it continues where it stopped. To keep it running even if you disconnect, start it inside `tmux` (`sudo apt-get install -y tmux`, then `tmux`, then the build command; reattach with `tmux attach`).

### 3.4 Check

```bash
~/llama.cpp/build/bin/llama-server --version
```

You should see:

```text
version: 0.9.0-dev (build 1, commit 2cbe0ec)
built with GNU 14.2.0 for Linux aarch64
```

---

## Step 4: Download the models

You'll download two models from Hugging Face into `~/models`:

| Model | File | Size | Role |
| --- | --- | --- | --- |
| [Qwen3.5 0.8B](https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF), Q8_0 | `Qwen_Qwen3.5-0.8B-Q8_0.gguf` | 835 MB | Reads the problem and picks the answer |
| [bge-small-en-v1.5](https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf), Q8_0 | `bge-small-en-v1.5-q8_0.gguf` | 37 MB | Turns a text into 384 numbers, so you can find similar problems |

GGUF is llama.cpp's model file format. Q8_0 means each weight is stored in about 8 bits, which keeps the quality close to the original model at a quarter of the size.

### 4.1 Download

Each URL is pinned to a fixed revision of the model repository, so everyone gets exactly the same file:

```bash
mkdir -p ~/models
cd ~/models
wget --continue https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/f36b1ea49a332ede8fe5f389bbf5b3575ef71f48/Qwen_Qwen3.5-0.8B-Q8_0.gguf
wget --continue https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf/resolve/d32f8c040ea3b516330eeb75b72bcc2d3a780ab7/bge-small-en-v1.5-q8_0.gguf
```

If a download breaks, run the same command again. `--continue` resumes it.

### 4.2 Check the files

A SHA256 hash is a fingerprint of a file. If one byte is different, the hash is completely different. Check both files:

```bash
sha256sum --check <<'EOF'
7182e2362766bb9569209bbc24cf1a4cdfbb8ab161babdb2080c84fa62c08c2f  Qwen_Qwen3.5-0.8B-Q8_0.gguf
ec38e8da142596baa913124ae50550de284b6916bf59577ef2f0cb9660c2f514  bge-small-en-v1.5-q8_0.gguf
EOF
```

You should see:

```text
Qwen_Qwen3.5-0.8B-Q8_0.gguf: OK
bge-small-en-v1.5-q8_0.gguf: OK
```

If a file says `FAILED`, delete it with `rm`, and download it again.

---

## Step 5: Hello world with the language model

Now run the language model by hand, and talk to it. You'll need two terminals on the board: one runs the server, and the other sends it questions.

### 5.1 Start the server (terminal 1)

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf \
  --host 127.0.0.1 --port 8081 \
  --threads 4 --ctx-size 4096 \
  --parallel 1 --cache-ram 0 --ctx-checkpoints 2 \
  --jinja --reasoning off --reasoning-budget 0 \
  --alias qwen3.5-0.8b
```

| Option | What it does |
| --- | --- |
| `-m` | The model file |
| `--host 127.0.0.1 --port 8081` | Listen on this board only, on port 8081. Nothing is exposed to the network. |
| `--threads 4` | Use the four CPU cores |
| `--ctx-size 4096` | Up to 4,096 tokens per request: a problem, its options, and a few examples |
| `--parallel 1` | One request at a time. Several slots would split the memory and the cores. |
| `--cache-ram 0 --ctx-checkpoints 2` | **Keep memory in check.** By default, this llama.cpp version keeps up to 8 GB of prompt cache in RAM, and the board has 3.6 GB. In our tests, the default settings got `llama-server` killed for running out of memory. |
| `--jinja` | Use the chat template stored in the model file |
| `--reasoning off --reasoning-budget 0` | Answer directly, without a hidden thinking phase that costs time |
| `--alias` | The model name the API reports |

Wait until the log shows these lines, after about 5 seconds:

```
srv  server_run_i: model loaded
srv  server_on_li: listening on http://127.0.0.1:8081
```

Leave this terminal open. To stop the server later, press Ctrl+C here.

If you see `couldn't bind HTTP server socket` instead, another `llama-server` already uses port 8081. Run `pgrep -a llama-server` to see it, stop it with `pkill llama-server`, and start again.

### 5.2 Open a second terminal (terminal 2)

On your laptop, open a new terminal window and connect again:

```bash
ssh arduino@192.168.1.131
```

### 5.3 Is it alive?

```bash
curl http://127.0.0.1:8081/health
```

You should see:

```text
{"status":"ok"}
```

### 5.4 Hello world

The server speaks the same chat API as OpenAI, so any OpenAI client works with it. Send it a question:

```bash
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "messages": [{"role": "user", "content": "Hello! What is 7 times 8? Answer in one sentence."}],
        "temperature": 0,
        "max_tokens": 40
      }' | jq -r '.choices[0].message.content'
```

You should see:

```text
7 times 8 equals 56.
```

It took about 4 seconds on our board. `"temperature": 0` makes the answer the same every time, which the datathon rules require.

### 5.5 How fast is it?

Run the same request, but print the timings instead of the answer:

```bash
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello! What is 7 times 8? Answer in one sentence."}], "temperature": 0, "max_tokens": 40}' \
  | jq '.timings | {prompt_n, prompt_per_second, predicted_n, predicted_per_second}'
```

You should see:

```text
{
  "prompt_n": 27,
  "prompt_per_second": 11.277385250516671,
  "predicted_n": 10,
  "predicted_per_second": 5.875521207693799
}
```

- `prompt_per_second`: the board **reads** about 11 tokens per second. A competition problem with its options has 80 to 300 tokens, so reading it takes 7 to 25 seconds.
- `predicted_per_second`: it **writes** about 6 tokens per second. Every word you let the model write costs time against the 60-second limit.

These two numbers shape every idea you'll try in the datathon.

### 5.6 One letter, A to E

In the datathon, the answer must be one letter. A grammar forces the model to write only what the grammar allows: here, one character from A to E.

```bash
curl -s http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "messages": [{"role": "user", "content": "What is 2 + 3 x 4?\nA) 20\nB) 14\nC) 24\nD) 9\nE) 10\nReply with the letter of the correct option."}],
        "grammar": "root ::= [A-E]",
        "temperature": 0,
        "max_tokens": 1
      }' | jq -r '.choices[0].message.content'
```

You should see:

```text
C
```

The format is right: one letter. The answer is wrong: 2 + 3 × 4 is 14, which is B. That's the challenge of the datathon, in one example.

---

## Step 6: Hello world with the embedding model

The embedding model turns a text into a list of 384 numbers (a vector). Texts with similar meanings get vectors that point in similar directions. You'll use it to find solved problems that look like a new one.

### 6.1 Start the server

In terminal 1, stop the language model with Ctrl+C if you like (or open a third terminal), and run:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/bge-small-en-v1.5-q8_0.gguf \
  --embedding \
  --host 127.0.0.1 --port 8082 \
  --threads 4 --ctx-size 512 --batch-size 512 --ubatch-size 512 \
  --parallel 1 --cache-ram 0
```

- `--embedding` serves vectors instead of chat answers.
- `--ctx-size 512`: bge-small was trained on texts up to 512 tokens.
- `--batch-size 512 --ubatch-size 512`: an embedding model reads the whole text in one go, so the batch must be as large as the longest text.

### 6.2 Hello world

In terminal 2:

```bash
curl http://127.0.0.1:8082/health
```

You should see:

```text
{"status":"ok"}
```

```bash
curl -s http://127.0.0.1:8082/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "How many apples are left?"}' \
  | jq -c '.data[0].embedding | length, .[0:4]'
```

You should see:

```text
384
[-0.017603538930416107,-0.06429719924926758,-0.014960619620978832,-0.09050412476062775]
```

The first line is the length: 384 numbers, so it works. The second line shows the first four. Your last digits may differ.

### 6.3 Stop both servers

Press Ctrl+C in each terminal that runs a server, or run:

```bash
pkill llama-server
```

In the next step, systemd runs them for you.

---

## Step 7: Run both models as services

Running the servers by hand is good for experiments. For the datathon, they should start when the board boots, and restart if they crash. systemd, the Linux service manager, does that.

### 7.1 Create the service for the language model

This command writes the service file. Copy and paste it as a whole:

```bash
sudo tee /etc/systemd/system/math-llm.service > /dev/null <<'EOF'
[Unit]
Description=Math on the Edge: small language model (llama.cpp, port 8081)
After=local-fs.target

[Service]
Type=simple
User=arduino
ExecStart=/home/arduino/llama.cpp/build/bin/llama-server -m /home/arduino/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf --host 127.0.0.1 --port 8081 --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 --alias qwen3.5-0.8b
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

The `ExecStart` line is the same command as in step 5.1, with full paths: systemd doesn't know what `~` means.

### 7.2 Create the service for the embedding model

```bash
sudo tee /etc/systemd/system/math-embed.service > /dev/null <<'EOF'
[Unit]
Description=Math on the Edge: embedding model (llama.cpp, port 8082)
After=local-fs.target

[Service]
Type=simple
User=arduino
ExecStart=/home/arduino/llama.cpp/build/bin/llama-server -m /home/arduino/models/bge-small-en-v1.5-q8_0.gguf --embedding --host 127.0.0.1 --port 8082 --threads 4 --ctx-size 512 --parallel 1 --cache-ram 0 --batch-size 512 --ubatch-size 512
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### 7.3 Start them

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now math-llm math-embed
```

- `daemon-reload` makes systemd read the new files.
- `enable --now` starts both services now, and at every boot.

### 7.4 Check

Wait about 10 seconds for the models to load, then:

```bash
systemctl is-active math-llm math-embed
curl http://127.0.0.1:8081/health; echo
curl http://127.0.0.1:8082/health; echo
free -h
```

You should see `active` twice, then `{"status":"ok"}` twice, then the memory table.

The two servers use about 1.1 GB of RAM together, and leave about 2.5 GB free.

Run the hello world from step 5.4 again: it should answer the same way.

Commands you'll use often:

```bash
systemctl status math-llm               # is it running?
journalctl -u math-llm -f               # follow its log (Ctrl+C to stop)
sudo systemctl restart math-llm         # restart it, for example after changing the model
sudo systemctl stop math-llm math-embed # free the RAM for an experiment
```

To try other server options, stop the service first (`sudo systemctl stop math-llm`), because only one program can use port 8081.

---

## Step 8: Get the datathon code and run the first test

### 8.1 Clone this repository on the board

```bash
cd ~
git clone https://github.com/mpous/datathon-maths-arduino-unoq.git
cd datathon-maths-arduino-unoq
```

Every later command on the board runs from this folder, `~/datathon-maths-arduino-unoq`. If your team forks the repository, clone your fork instead, and commit your changes there.

The code uses only Python's standard library. There's no `pip` on the board, and you don't need it.

### 8.2 Answer the sample problems

`data/sample_problems.jsonl` holds five made-up problems in the M3Kang format. Answer them with `predict.py`, the program the jury runs:

```bash
mkdir -p results
python3 predict.py --input data/sample_problems.jsonl --output results/smoke.csv
cat results/smoke.csv
```

**Check:** `results/smoke.csv` has one row per problem, each `answer` is one letter from A to E, each `status` is `ok`, and each `seconds` value is well under 60.

The test checks that the pipeline runs, not that it's right. Don't be surprised if most of the five answers are wrong. Compare them with the `label` field in `data/sample_problems.jsonl`.

**This is the minimum every team must have working.** The steps that follow give you the data and the tools to improve it.


---

## Step 9: Prepare M3Kang on your laptop

[M3Kang](https://huggingface.co/datasets/qualcomm/M3Kang) has 1,747 Kangaroo math competition problems, from 2007 to 2024, at 8 levels (level 0 is grade 5), translated into 108 languages. Each problem has a label: the correct letter, A to E.

**There's a catch: the five options are only in the image, not in the text.** The `text` field has the question, but A to E are drawn in the picture. The preparation script reads them with OCR (optical character recognition) on your laptop, which is much faster than the board.

### 9.1 Install the requirements

On your laptop:

```bash
git clone https://github.com/mpous/datathon-maths-arduino-unoq.git
cd datathon-maths-arduino-unoq
python3 -m venv .venv
source .venv/bin/activate
pip install -r laptop/requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

### 9.2 Run it

On your laptop:

```bash
python3 laptop/prepare_m3kang.py --languages eng,cat
```

It downloads the first `high_quality` file of the dataset (393 MB, once), keeps English and Catalan, reads the options from each image, and splits the problems into training and validation sets. It takes about 15 minutes per language. If you stop it, run it again: it caches the OCR results in `data/.ocr_cache.jsonl`.

To test it quickly first, add `--limit 20`.

Useful options:

| Option | What it does |
| --- | --- |
| `--languages eng,cat,esp` | Which languages to keep. Spanish is `esp`. The first file has all 1,747 problems in English and Catalan, and fewer in the others: `fra` 1,427, `esp` 1,368, `deu` 716, and more. |
| `--shards all` | Download all four `high_quality` files, for more languages |
| `--val-fraction 0.15` | Share of problems held out for validation (the default) |
| `--val-years 2023,2024` | Hold out whole years instead, which is closer to an unseen test |
| `--save-images` | Also save every image as a PNG, so you can look at the problems |
| `--no-ocr` | Skip OCR. Every problem then has empty options. |

The same problem has the same `id` in every language, so the split is made by `id`: a problem's translations are never split between training and validation.

**Check:** the script ends with a summary like this one, from our English run:

```
Wrote data/train.jsonl and data/val.jsonl
  train eng: 1466
  val   eng: 281
Options read from the image: 1078/1747 (62%)
  of which text-only problems: 601/811 (74%)
Most common answer in train: D (25.0%). ...
```

### 9.3 What the OCR gets wrong

OCR reads all five options for 62% of the problems. The rest have `"options": {}`, and the model sees only the question. The usual reasons:

- The options are pictures: shapes, graphs, or figures
- Fractions and formulas come out garbled, such as `1/2` read as `12`
- In a few problems, two options come out the same

Better option reading is one of the easiest ways to improve your score. Look at the problems with empty options with `--save-images`.

### 9.4 The data format

One problem per line in `data/train.jsonl` and `data/val.jsonl`:

```json
{"id": "lvl-0_2015_13", "language": "eng", "level": 0, "year": 2015, "text_only": true,
 "text": "13. For 3 days, the cat Joy has been catching mice. ...",
 "options": {"A": "12", "B": "15", "C": "18", "D": "20", "E": "24"}, "label": "C"}
```

**Don't commit these files, or share them outside the datathon.** M3Kang is licensed for research use only. `.gitignore` already excludes them.

---

## Step 10: Copy the data to the board

From the repository folder on your laptop:

On your laptop:

```bash
scp data/train.jsonl data/val.jsonl arduino@192.168.1.131:~/datathon-maths-arduino-unoq/data/
```

Or over USB:

On your laptop:

```bash
adb push data/train.jsonl data/val.jsonl /home/arduino/datathon-maths-arduino-unoq/data/
```

**Check:**

```bash
wc -l data/train.jsonl data/val.jsonl
```

---

## Step 11: Measure the baseline

### 11.1 How the baseline works

`predict.py` is the entry point the jury runs:

```bash
python3 predict.py --input data/val.jsonl --output results/predictions.csv
```

For each problem, `copilot/pipeline.py`:

1. Formats the question and the options as `A) ...` to `E) ...`
2. Sends them to the language model with a short instruction
3. Forces the answer to be exactly one letter, A to E, with a grammar (`root ::= [A-E]`), so the model can't reply with anything else
4. Stops waiting before 60 seconds, and answers `D` if the model is too slow or fails

The output is a CSV file with one row per problem: `id`, `language`, `answer`, `seconds`, and `status`.

**The rules your code must keep:**

- One letter, A to E, for every problem
- At most 60 seconds per problem (`TIME_LIMIT_SECONDS` in `config.env`)
- No network: everything runs on the board
- The same answers every time: temperature 0 and a fixed seed

### 11.2 Run the evaluation

```bash
python3 eval.py --limit 50 --name baseline
```

It answers 50 validation problems, chosen the same way each time, and compares them with the labels. It prints:

- **Accuracy**, next to two numbers to beat: always answering `D` (about 25%, because D is the most common answer) and guessing at random (20%)
- **Latency**: mean, median, worst, and how many problems went over the limit
- Accuracy **by language, by level, and with or without options**
- **Letter counts**, predicted against true. If the model picks one letter far too often, you'll see it here.

Every run is saved in `results/eval-<time>-<name>.csv`, and gets one line in `results/ablations.csv`, with the Git commit, so you can compare experiments. Use `--limit 0` for the whole validation set (about 45 minutes for 281 problems), and `--languages cat` for one language.

### 11.3 What we measured

On 40 English text-only problems whose options OCR read, with the default settings:

| Approach | Accuracy | Mean time | Worst time |
| --- | --- | --- | --- |
| Always `D` | 25% on the training set | 0 s | 0 s |
| **Baseline: one letter, grammar A to E** | **22.5%** (9/40) | 8.7 s | 12.7 s |
| The option's value instead of its letter | 17.5% (7/40) | 9.3 s | 13.5 s |
| One line of reasoning, then the letter | 17.5% (7/40) | 26.3 s | 35.0 s |

All three are close to random guessing, and below the always-D floor. That's the starting point: an 0.8B model reading a competition problem in one go is close to guessing. The baseline also has a strong letter bias. It answered `D` 21 times and `A` 14 times out of 40, while the true answers were spread over all five letters. Your job is to do better, inside 60 seconds and 4 GB of RAM.

The time is mostly prompt reading (prefill): the board reads about 12 tokens per second, so an 85-token problem takes about 7 seconds before the first answer token.

---

## Step 12: Try retrieval (RAG)

Retrieval-augmented generation (RAG) finds solved problems that look like the new one, and shows them to the model as examples.

### 12.1 Build the index

```bash
python3 build_index.py --input data/train.jsonl --db data/index.db --only-with-options
```

It embeds every training problem with bge-small and stores the vectors in a SQLite file, `data/index.db`. `--only-with-options` skips problems whose options OCR couldn't read. `--languages eng` keeps one language.

### 12.2 Use it

```bash
python3 eval.py --limit 50 --rag 1 --name rag1
python3 predict.py --input data/val.jsonl --output results/predictions.csv --rag 1
```

`--rag 1` adds the most similar training problem, with its answer, before the question. `--rag 2` adds two. `eval.py` never retrieves the problem it's answering (`exclude_id`), so the score stays honest.

Every example makes the prompt longer, and the board reads about 12 tokens per second. Check the latency columns, not just the accuracy.

---

## Optional: Explore the problems in your browser

The explorer is a small web app on the board. For each validation problem, it shows the image and the options OCR read. You can:

- Answer it yourself, A to E, and see if you're right
- Ask the model, with or without RAG examples, and see its answer, its time, and the exact prompt it got
- See the 3 most similar training problems found with the embeddings, with their images and answers

It uses only the Python standard library, like the rest of the code on the board.

### Export the images

On your laptop, run the preparation from step 9 again with `--save-images`. The OCR is cached, so it's quick the second time:

```bash
python3 laptop/prepare_m3kang.py --languages eng --save-images
```

It writes one PNG per problem to `data/images/`, such as `lvl-0_2015_14_eng.png`: 1,747 files and 71 MB for English. Copy them to the board:

On your laptop:

```bash
scp -r data/images arduino@192.168.1.131:~/datathon-maths-arduino-unoq/data/
```

Or over USB:

On your laptop:

```bash
adb push data/images /home/arduino/datathon-maths-arduino-unoq/data/
```

The images are M3Kang data too: don't commit them. `.gitignore` already excludes `data/`.

### Start the explorer

On the board, with the services from step 7 running and the index from step 12.1 built:

```bash
cd ~/datathon-maths-arduino-unoq
python3 explorer/server.py
```

You should see:

```text
281 problems from data/val.jsonl, 281 with images, 911 in the retrieval index
Servers: language model up, embeddings up, vision off
Open http://127.0.0.1:8000 (Ctrl+C to stop)
```

The explorer only listens on the board itself. To open it on your laptop, forward the port in a second terminal.

On your laptop:

```bash
ssh -L 8000:127.0.0.1:8000 arduino@192.168.1.131
```

Or over USB:

On your laptop:

```bash
adb forward tcp:8000 tcp:8000
```

Then open <http://127.0.0.1:8000> in your browser. Keys: `A` to `E` answer, `M` asks the model, `N` goes to the next problem, `R` picks a random one. `--input data/train.jsonl` explores the training set instead.

**What we saw:** the model answers a problem in 5 to 10 seconds without examples, and in about 30 seconds with 2 RAG examples. The similar problems are often about the same topic (cubes, for example), but their answers don't tell the model this problem's answer.

### Let the model see the image (experiment)

Qwen3.5 0.8B can read images with a projector file. That runs a third server, on port 8083. Download it once:

```bash
cd ~/models
wget --continue https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/f36b1ea49a332ede8fe5f389bbf5b3575ef71f48/mmproj-Qwen_Qwen3.5-0.8B-f16.gguf
sha256sum --check <<'EOF'
1dc1351c82e41b48edb55fd6ddfa7ca60fb5a16b3d5abf3ce7054880dd022847  mmproj-Qwen_Qwen3.5-0.8B-f16.gguf
EOF
```

Start it in its own terminal:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf \
  --mmproj ~/models/mmproj-Qwen_Qwen3.5-0.8B-f16.gguf \
  --image-max-tokens 128 \
  --host 127.0.0.1 --port 8083 \
  --threads 4 --ctx-size 4096 \
  --parallel 1 --cache-ram 0 --ctx-checkpoints 2 \
  --jinja --reasoning off --reasoning-budget 0
```

Restart the explorer, and tick **Send the image** before you ask the model.

`--image-max-tokens 128` shrinks the image to at most about 128 tokens. Without it, an image takes 300 to 650 tokens. What we measured on the board:

| Image tokens | Time per problem |
| --- | --- |
| Default (292 and 656 tokens) | 68 s and 185 s |
| `--image-max-tokens 128` (140 to 235 tokens) | 28 to 38 s |

Only the smaller images fit in the 60-second limit. On the two problems we tried, the model got the answer wrong with the image too. Treat this as an experiment, and measure it with `eval.py` before you build on it. When you're done, stop the server with `Ctrl+C` to free its RAM.

---

## Step 13: Test offline, like the jury

At the official run, the board has no network. Test that now. Turning Wi-Fi off drops your SSH session, so connect over USB with `adb shell` (step 0.4) first.

On your laptop:

```bash
adb shell
```

Then, in that shell on the board:

```bash
cd ~/datathon-maths-arduino-unoq
sudo nmcli radio wifi off
./freeze/check_offline.sh data/val.jsonl 20
sudo nmcli radio wifi on
```

Add the same options you'll submit, such as `--rag 1`, after the count:

```bash
./freeze/check_offline.sh data/val.jsonl 20 --rag 1
```

The script checks that there's no route to the internet, that both servers are up, and then runs `predict.py` twice on the same problems. It fails if:

- Any answer isn't a single letter, A to E
- The two runs give different answers
- Any problem timed out, failed, or went over the time limit

**Check:** it ends with `OK` and no `FAIL` lines.

---

## Step 14: Freeze your submission

Before the test set is released, freeze what you'll run:

```bash
./freeze/make_freeze.sh my-team-name
```

It writes `freeze/manifest.txt` (your Git commit, the llama.cpp version, the SHA256 of every model in `~/models`, and the service command lines), and packs your code, indexes, and manifest into `freeze/my-team-name-<time>.tar.gz`. It doesn't pack `train.jsonl` or `val.jsonl`.

It prints one SHA256 hash. **Send that hash to the organizers before the deadline.** At the official run, they check that your board matches it.

After you freeze, don't change the code, the models, or `config.env`.

---

## Ideas to beat the baseline

Change one thing at a time, and record each run with `eval.py --name`.

- **Fix the letter bias.** Look at the letter counts in `eval.py`. Ask for the model's log probabilities (`"logprobs": true, "top_logprobs": 5`) and correct for a letter it picks too often.
- **Ask for the value, not the letter**, or **let it reason** in one line before `Answer: X`. Neither helped on their own in our test (step 11.3), but they may help combined with a better prompt, examples, or a bigger model. Reasoning triples the time per problem.
- **Break the problem down.** Classify the problem type first, compute with Python where you can (arithmetic, counting), and ask the model only for what it's good at.
- **Read the options better.** Improve the OCR, or crop the bottom of the image before OCR.
- **Use the image.** Qwen3.5 0.8B can see images with its projector file (205 MB). Try it in the [explorer](#let-the-model-see-the-image-experiment) first: it costs RAM and time, so measure both.
- **Retrieve better.** Combine embeddings with keyword search, or only use examples above a similarity score.
- **Try a different model.** Any GGUF model that fits in RAM, answers in time, and has a license you can use. Update `config.env` with its repository, revision, file, and SHA256.

---

## Reference

### Repository layout

```
config.env                  every setting: versions, models, ports, time limit
board/
  common.sh                 shared helpers for the board scripts
  00_check_board.sh         read-only health check
  01_install_packages.sh    apt packages, with an index repair
  02_build_llama_cpp.sh     llama.cpp at the pinned commit
  03_download_models.sh     pinned, hash-checked model downloads
  04_install_services.sh    installs and starts the systemd services
  05_smoke_test.sh          end-to-end check
  systemd/                  service templates
copilot/
  config.py                 reads config.env
  client.py                 HTTP to the local servers
  llm.py                    prompt, grammar, one-letter answer
  embed.py                  embeddings
  rag.py                    SQLite index and search
  pipeline.py               solve one problem within the time limit
predict.py                  the official entry point
eval.py                     accuracy, latency, and breakdowns
build_index.py              builds data/index.db
explorer/
  server.py                 the web app: problems, images, model, similar problems
  index.html                its page
laptop/
  prepare_m3kang.py         M3Kang download, OCR, and split
  requirements.txt
data/
  sample_problems.jsonl     five made-up problems
freeze/
  check_offline.sh          the offline, repeatable test
  make_freeze.sh            the submission archive and hash
results/                    eval outputs and ablations.csv (not committed)
```

The scripts in `board/` run steps 1 to 8 without stopping, using the settings in `config.env`. Do the steps by hand on your first board, so you know what each one does. Use the scripts to set up more boards, or to repair one.

### Settings in config.env

| Setting | Default | Meaning |
| --- | --- | --- |
| `LLAMA_CPP_REF` | `2cbe0ec…` | llama.cpp commit to build |
| `LLM_REPO`, `LLM_REVISION`, `LLM_FILE`, `LLM_SHA256` | Qwen3.5 0.8B Q8_0 | Language model download |
| `LLM_CTX` | 4096 | Context length, in tokens |
| `LLM_THREADS`, `EMBED_THREADS` | 4 | CPU threads (the board has 4 cores) |
| `EMBED_CTX` | 512 | Embedding context; bge-small was trained on 512 tokens |
| `TIME_LIMIT_SECONDS` | 60 | Time limit per problem |
| `SEED` | 42 | Random seed |
| `FALLBACK_ANSWER` | D | Answer when the model is too slow or fails |
| `VISION_PORT` | 8083 | Optional server that can see images, for the explorer |

`config.env` is read by the Python code and by the scripts in `board/`. If you change the model or a server option, also change the service files from step 7, then run `sudo systemctl daemon-reload` and `sudo systemctl restart math-llm math-embed`.

### Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ssh: connect to host … port 22: Connection refused` | Empty SSH host keys. See [step 0.3](#03-connect-over-ssh). |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED` | The board's keys were recreated. Run `ssh-keygen -R <ip>` on your laptop. |
| `apt`: package "is not installable" | Incomplete package lists. See [step 2.2](#22-install-the-packages). |
| `apt` or downloads fail with certificate or time errors | The clock is wrong. Check `timedatectl`, and connect to a network with internet. |
| `llama-server` disappears, and `journalctl -k` shows `Out of memory` | Use `--parallel 1 --cache-ram 0` as in [step 5.1](#51-start-the-server-terminal-1), and stop servers you started by hand: `pkill llama-server`. |
| `couldn't bind HTTP server socket, hostname: 127.0.0.1, port: 8081` | Another `llama-server` already uses the port: the service from step 7, or one you started in another terminal. See what runs with `pgrep -a llama-server`. Stop the service with `sudo systemctl stop math-llm math-embed`, or the other server with `pkill llama-server`. |
| SSH drops when you turn Wi-Fi off | Expected. Use `adb shell` over USB. |
| `predict.py` answers `D` with status `timeout` | The prompt is too long for 60 seconds. Use fewer RAG examples or a shorter prompt. |
| `Connection refused` on port 8081 or 8082 | The service is down. Check `systemctl status math-llm` and `journalctl -u math-llm`. |

### Credits and licenses

- **M3Kang**: Torres-Camps et al., 2026, [arXiv:2601.16218](https://arxiv.org/abs/2601.16218). Qualcomm. [Dataset card and license](https://huggingface.co/datasets/qualcomm/M3Kang): research use only. Problems from the Kangaroo math competition.
- **llama.cpp**: [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp), MIT license.
- **Qwen3.5 0.8B**: by the Qwen team, GGUF by bartowski. Check the license on the [model card](https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF).
- **bge-small-en-v1.5**: by BAAI, GGUF by CompendiumLabs. Check the license on the [model card](https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf).
- **RapidOCR**: [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR), Apache 2.0 license.
- For more on generative AI on this board, including RAG, see Marcelo Rovai's book [Generative AI at the Edge: Running Small Language Models with Arduino UNO Q and llama.cpp](https://mjrovai.github.io/genai-uno-q/).
