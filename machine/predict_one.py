#!/usr/bin/env python3
"""One prediction for one problem (one line of val.jsonl, or any problems file).

    python -I machine/predict_one.py --list
    python -I machine/predict_one.py --serve Qwen_Qwen3.5-0.8B-Q8_0.gguf --index 1
    python -I machine/predict_one.py --serve Qwen_Qwen3.5-0.8B-Q8_0.gguf --id lvl-0_2015_17 --variant cot

--serve starts a llama-server from qualcomm/models, waits for /health, and shuts it
down afterwards, so the only thing you need is a GGUF in qualcomm/models. Without
--serve the script talks to a server that is already running on --port (18111).

Variants
  letter    the organisers' exact prompt; log-probs of A..E for the first token (no generation)
  cot       one or two sentences of reasoning (<= --max-tokens), then the letter log-probs
  pot       the model writes one Python expression; we evaluate it and match the options
  official  exactly what predict.py submits: pipeline.solve() with the A-E grammar

Token limits (two different knobs)
  --max-tokens N   tokens the model may generate in one answer (default 60; cot/pot only,
                   letter reads a single token, so it does not change)
  --ctx-size N     prompt + generation window of the server started by --serve (default 4096,
                   the board value). 0 = the model's maximum, which is 262144 for the 0.8B.
                   Generation is capped by ctx-size minus the prompt, so --max-tokens above
                   that is refused by llama-server.

letter/cot/pot reuse lab.py's run_one(), so the record written by --out has the same
schema as lab/<name>.jsonl and can sit next to a full run.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import json
import socket
import subprocess
import time
import urllib.error

from paths import ROOT
from lab import run_one

LOG_DIR = os.path.join(ROOT, "lab", "logs")
SERVER = os.path.join(ROOT, "llama.cpp", "build", "bin", "Release", "llama-server.exe")
MODELS = os.path.join(ROOT, "models")
VARIANTS = ["letter", "cot", "pot", "official"]

# Same flags as run_models.bat / run_lab.bat, so laptop numbers stay comparable
# (--ctx-size is added per run, see --ctx-size)
SERVER_ARGS = ["--host", "127.0.0.1", "--threads", "4", "--parallel", "1",
               "--cache-ram", "0", "--ctx-checkpoints", "2", "--jinja",
               "--reasoning", "off", "--reasoning-budget", "0"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pick(problems, args):
    if args.id:
        for n, problem in enumerate(problems, 1):
            if problem["id"] == args.id:
                return n, problem
        sys.exit(f"no problem with id {args.id!r} in {args.input}")
    if not 1 <= args.index <= len(problems):
        sys.exit(f"--index must be between 1 and {len(problems)}")
    return args.index, problems[args.index - 1]


def healthy(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, socket.timeout, OSError):
        return False


def serve(args):
    """Start llama-server for args.serve on args.port; return the process and its log path."""
    model = args.serve if os.path.isabs(args.serve) else os.path.join(MODELS, args.serve)
    if not os.path.exists(model):
        sys.exit(f"model not found: {model}")
    if not os.path.exists(args.server):
        sys.exit(f"llama-server not found: {args.server}")
    if healthy(f"http://127.0.0.1:{args.port}"):
        sys.exit(f"port {args.port} already has a server; drop --serve or use --port")

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"predict-{os.path.basename(model)}-{args.port}.log")
    log = open(log_path, "wb")
    print(f"Starting {os.path.basename(model)} on port {args.port} (log: {log_path})", flush=True)
    proc = subprocess.Popen([args.server, "-m", model, "--port", str(args.port),
                             "--ctx-size", str(args.ctx_size)] + SERVER_ARGS,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)

    for _ in range(180):
        if proc.poll() is not None:
            proc.wait()
            sys.exit(f"llama-server exited with code {proc.returncode}; see {log_path}")
        if healthy(f"http://127.0.0.1:{args.port}"):
            return proc, log
        time.sleep(1)
    stop(proc)
    sys.exit(f"llama-server did not become healthy in 180 s; see {log_path}")


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def show(n, total, problem, rec):
    options = problem.get("options") or {}
    print(f"\n[{n}/{total}] {problem['id']}  {problem.get('language', '')} "
          f"level {problem.get('level', '?')}")
    print("  " + problem["text"].strip().replace("\n", "\n  "))
    if options:
        print("  " + "   ".join(f"{k}) {v}" for k, v in options.items()))
    else:
        print("  (the options are in a picture: only a letter can be guessed)")

    if "lp" not in rec:  # the official variant answers with one letter only
        print(f"\n  prediction: {rec['answer']}  "
              f"({rec['status']}, {rec['seconds']} s, {rec.get('prompt_tokens', 0)} prompt tokens)")
        return

    lp = rec["lp"]
    predicted = max(lp, key=lp.get)
    print("\n  letter log-probs of the first token (higher is better):")
    for letter, value in sorted(lp.items(), key=lambda kv: -kv[1]):
        print(f"    {letter}  {value:8.3f}")

    option = options.get(predicted)
    label = problem.get("label")
    verdict = ""
    if label:
        verdict = "  <- correct" if predicted == label else f"  <- the label is {label}"
    print(f"\n  prediction: {predicted}" + (f" ({option})" if option else "") + verdict)

    for key in ("thought", "expr", "value", "match", "content"):
        if rec.get(key) not in (None, ""):
            print(f"  {key}: {rec[key]}")
    print(f"  read {rec['read_tokens']} tok, wrote {rec['written_tokens']} tok, "
          f"board ~{rec['board_s']} s, wall {rec['laptop_s']} s")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="val", help="val, train, sample_problems, or a jsonl path")
    p.add_argument("--index", type=int, default=1, help="1-based line number (default 1)")
    p.add_argument("--id", help="problem id, e.g. lvl-0_2015_17 (wins over --index)")
    p.add_argument("--variant", default="letter", choices=VARIANTS)
    p.add_argument("--max-tokens", type=int, default=60,
                   help="how many tokens the model may generate (cot/pot); letter reads 1 token")
    p.add_argument("--ctx-size", type=int, default=4096,
                   help="prompt + generation window of the server started by --serve "
                        "(0 = the model's maximum, 262144 for the 0.8B)")
    p.add_argument("--port", type=int, default=18111, help="port of the llama-server")
    p.add_argument("--serve", metavar="GGUF",
                   help="start this model (in qualcomm/models) on --port and stop it afterwards")
    p.add_argument("--keep-server", action="store_true", help="leave the started server running")
    p.add_argument("--server", default=SERVER, help="llama-server.exe to run with --serve")
    p.add_argument("--out", help="append the record as one json line to this file")
    p.add_argument("--list", action="store_true", help="list the entries instead of predicting")
    args = p.parse_args()

    if args.input.endswith(".jsonl"):
        path = args.input
    else:
        path = os.path.join(ROOT, "data", args.input + ".jsonl")
    if not os.path.exists(path):
        sys.exit(f"{path} not found")
    problems = load(path)

    if args.list:
        for n, problem in enumerate(problems, 1):
            kind = "options" if problem.get("options") else "text-only"
            print(f"  {n:3d}  {problem['id']:16s} label {problem.get('label', '?')}  "
                  f"{problem.get('language', '')} level {problem.get('level', '?')}  {kind}")
        return

    n, problem = pick(problems, args)
    for key, default in (("label", ""), ("level", 0), ("language", "eng"), ("text_only", False)):
        problem.setdefault(key, default)
    url = f"http://127.0.0.1:{args.port}"
    if not args.serve and args.ctx_size != 4096:
        print(f"note: --ctx-size only applies with --serve; the server already on port "
              f"{args.port} keeps its own", file=sys.stderr)

    proc = None
    try:
        if args.serve:
            proc, _log = serve(args)
        elif not healthy(url):
            sys.exit(f"no llama-server on port {args.port} (start one, or pass --serve MODEL.gguf)")

        if args.variant == "official":
            from copilot.pipeline import solve
            try:
                result = solve(problem, llm_url=url + "/v1/chat/completions")
            except urllib.error.URLError as error:
                sys.exit(f"llama-server is not reachable on port {args.port}: {error.reason}")
            rec = {k: result[k] for k in ("answer", "seconds", "status", "prompt_tokens")}
        else:
            lab_args = argparse.Namespace(variant=args.variant, max_tokens=args.max_tokens, k=0)
            try:
                rec = run_one(url, problem, lab_args, None)
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8", "replace").strip()
                sys.exit(f"llama-server returned HTTP {error.code}: {body[:300]}")
            except urllib.error.URLError as error:
                sys.exit(f"llama-server is not reachable on port {args.port}: {error.reason}")

        show(n, len(problems), problem, rec)
        if args.out:
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": problem["id"], **rec}, ensure_ascii=False) + "\n")
            print(f"  appended to {args.out}")
    finally:
        if proc is not None and not args.keep_server:
            stop(proc)


if __name__ == "__main__":
    main()
