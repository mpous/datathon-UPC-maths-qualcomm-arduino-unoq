"""Reason mode: the hybrid that scored best on the 50 Discord practice problems (35/100 rows, chance 20).

For each problem, within one clock:
1. Plain letter: the model reads the problem and we keep its probability for each letter A-E (~10 s on the board).
   This is the answer if nothing better comes.
2. Python: if time is left, the model writes a short program. We run it in a sandbox; if the number it prints
   matches exactly one option, that option is the answer (right 11 times out of 14 on the practice set).
3. Balancing (predict.py, after all problems): the practice answers are balanced by design (10 per letter), and
   the model over-uses A and D. The letters that came from step 1 are re-assigned so each letter is used about
   n/5 times, keeping the most probable assignment. Answers from step 2 are never changed.

Measured on the board (Qwen3.5 0.8B Q8_0): reads ~11 tokens/s, writes ~5.7 tokens/s.
"""
import ast
import math
import os
import re
import subprocess
import sys
import tempfile
import time

from .client import post
from .config import CONFIG
from .llm import SYSTEM, format_problem

LETTERS = "ABCDE"
BASE_URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
WRITE_TPS = float(CONFIG.get("WRITE_TOKENS_PER_SECOND", 5.7))
CODE_INSTRUCTION = ("\nWrite a short Python program that computes the answer and prints only the final value. "
                    "Reply with the code only.")
ALLOWED_IMPORTS = {"math", "itertools", "fractions", "functools", "collections"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "input", "__import__", "globals", "locals", "vars",
                "getattr", "setattr", "delattr", "breakpoint", "help", "exit", "quit"}


def chat_prompt(problem, instruction=""):
    """Qwen chat template with thinking switched off, as llama-server builds it with --reasoning off."""
    user = format_problem(problem) + (instruction or "\nAnswer:")
    return (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def letter_logprobs(prompt, timeout, url=BASE_URL):
    """Log-probability of each letter as the next token (-99 when it's not among the top 50)."""
    r = post(url + "/completion", {"prompt": prompt, "n_predict": 1, "temperature": 0, "n_probs": 50,
                                   "seed": int(CONFIG["SEED"]), "cache_prompt": True}, timeout=timeout)
    lp = {c: -99.0 for c in LETTERS}
    first = (r.get("completion_probabilities") or [{}])[0]
    for t in first.get("top_logprobs") or first.get("probs") or []:
        token = (t.get("token") or t.get("tok_str") or "").strip()
        value = t.get("logprob", t.get("prob"))
        if token in lp and value is not None:
            lp[token] = max(lp[token], value if "logprob" in t else math.log(max(value, 1e-30)))
    return lp


def number(text):
    """'12', '-3.5', '3/4', '12 cm', '$7$' -> float; anything else -> None."""
    m = re.match(r"^\s*\$?\s*([-+−]?\d+(?:[.,]\d+)?)(?:\s*/\s*(\d+))?\s*\$?\s*[^\d\s]{0,8}\s*$", str(text or ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", ".").replace("−", "-"))
    return v / float(m.group(2)) if m.group(2) and float(m.group(2)) else v


def is_safe(src):
    """Only plain computation: imports from a short list, no dunders, no files, no exec."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(n.split(".")[0] not in ALLOWED_IMPORTS for n in names):
                return False
        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            return False
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return False
    return True


def run_program(reply, timeout=3.0):
    """Run the model's program in a separate, isolated Python. Returns (value or None, reason)."""
    fence = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", reply, flags=re.S)
    src = (fence.group(1) if fence else reply).strip()
    if not src:
        return None, "empty"
    if not is_safe(src):
        return None, "syntax or unsafe"
    env = {"PYTHONIOENCODING": "utf-8"}
    if os.name == "nt" and "SYSTEMROOT" in os.environ:  # Windows Python can't start without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    try:
        out = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True,
                             timeout=timeout, cwd=tempfile.gettempdir(), env=env)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    lines = out.stdout.strip().splitlines()
    if out.returncode != 0:
        return None, "crash"
    if not lines:
        return None, "no output"
    nums = re.findall(r"[-−]?\d+(?:\.\d+)?(?:/\d+)?", lines[-1])
    return (number(nums[-1]), "ok") if nums else (None, "not a number")


def matching_option(value, options):
    """The one option equal to value, or None (none or several match)."""
    hits = [k for k, v in (options or {}).items()
            if number(v) is not None and math.isclose(number(v), value, rel_tol=1e-6, abs_tol=1e-6)]
    return hits[0] if len(hits) == 1 else None


def solve_hybrid(problem, deadline, url=BASE_URL):
    """Fill and return a dict: answer, how ('letter' or 'code'), lp, code_value, code_reason.

    deadline is a time.perf_counter() value; every request is cut so we finish before it.
    The letter from step 1 is kept whatever happens in step 2.
    """
    out = {"how": "letter", "lp": None, "code_value": None, "code_reason": "", "prompt_tokens": 0}
    left = deadline - time.perf_counter()
    lp = letter_logprobs(chat_prompt(problem), timeout=max(left, 1.0), url=url)
    out.update(lp=lp, answer=max(lp, key=lp.get))

    if not problem.get("options"):  # options are pictures: nothing to compute against
        out["code_reason"] = "no text options"
        return out
    left = deadline - time.perf_counter()
    # The code prompt shares the problem text with step 1, so it reads only the new instruction (~2 s)
    budget = int((left - 4.0) * WRITE_TPS)
    if budget < 40:
        out["code_reason"] = "no time left"
        return out
    try:
        r = post(url + "/completion", {
            "prompt": chat_prompt(problem, CODE_INSTRUCTION), "n_predict": min(budget, 300), "temperature": 0,
            "seed": int(CONFIG["SEED"]), "cache_prompt": True,
            "t_max_predict_ms": int(max(left - 3.0, 1.0) * 1000),
        }, timeout=max(left - 1.0, 1.0))
    except Exception as error:  # timeout or server trouble: keep the letter from step 1
        out["code_reason"] = f"generation: {type(error).__name__}"
        return out
    out["prompt_tokens"] = r.get("timings", {}).get("prompt_n", 0)
    value, reason = run_program(r.get("content", ""), timeout=min(3.0, max(deadline - time.perf_counter() - 0.5, 0.2)))
    out.update(code_value=value, code_reason=reason)
    if value is not None:
        letter = matching_option(value, problem.get("options"))
        if letter:
            out.update(answer=letter, how="code")
        else:
            out["code_reason"] = "no option matches"
    return out


def hungarian(cost):
    """Minimum-cost assignment of every row to a different column (rows <= columns). Pure Python, O(n^2 m)."""
    n, m = len(cost), len(cost[0])
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    rows = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            rows[p[j] - 1] = j - 1
    return rows


def balance(results):
    """Re-assign the 'letter' answers so each letter is used about n/5 times over the batch.

    results: list of dicts with answer, how and lp. Answers with how == 'code' (or without lp) stay.
    Returns the list of balanced letters, in the same order.
    """
    n = len(results)
    final = [r["answer"] for r in results]
    free = [i for i, r in enumerate(results) if r.get("how") == "letter" and r.get("lp")]
    if len(free) < 2:
        return final
    quota = {c: -(-n // 5) for c in LETTERS}  # ceil(n/5) per letter
    for i, r in enumerate(results):
        if i not in free and r["answer"] in quota:
            quota[r["answer"]] = max(0, quota[r["answer"]] - 1)
    slots = [c for c in LETTERS for _ in range(quota[c])]
    while len(slots) < len(free):  # the fixed answers used up the quotas: allow extra slots
        slots += list(LETTERS)
    cost = [[-max(results[i]["lp"].get(c, -99.0), -99.0) for c in slots] for i in free]
    for i, j in zip(free, hungarian(cost)):
        final[i] = slots[j]
    return final
