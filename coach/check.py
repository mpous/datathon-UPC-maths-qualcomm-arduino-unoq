#!/usr/bin/env python3
"""Check a running Teach server from start to finish, the way a student uses it.

    python3 coach/check.py                              # the server on this machine
    python3 coach/check.py http://<board-ip>:8000       # the board, from your laptop
    python3 coach/check.py http://<board-ip>:8000 --ask # and ask the coach a live question

It plays one student: a wrong answer, every rung of the hint ladder, the
warm-up problem, the solution, and the next problem. It fails loudly if the
server ever gives the answer away before the last rung.
"""
import json
import sys
import time
import urllib.error
import urllib.request

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
ASK = "--ask" in sys.argv  # also ask the coach a live question: about 20 seconds on the board
BASE = (ARGS[0] if ARGS else "http://127.0.0.1:8000").rstrip("/")
# web3/server.py serves the same routes under /api/coach: pass --api=/api/coach
API = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--api=")), "/api").rstrip("/")
NAME = f"check-{int(time.time())}"
passed = 0


def call(path, body=None):
    """Return (status, JSON, milliseconds)."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + API + path[len("/api"):], data=data, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            status, payload = response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        status, payload = error.code, json.loads(error.read())
    return status, payload, 1000 * (time.perf_counter() - start)


def ok(condition, what):
    global passed
    if not condition:
        sys.exit(f"  FAIL  {what}")
    passed += 1
    print(f"  ok    {what}")


def hides_answer(payload):
    """No label, at any depth of the reply."""
    return '"label"' not in json.dumps(payload)


def main():
    print(f"Server: {BASE}   student: {NAME}\n")

    status, info, ms = call("/api/info")
    ok(status == 200 and info["problems"] > 0, f"info: {info['problems']} problems, languages {info['languages']}, "
                                               f"{info['hints']} model hints ({ms:.0f} ms)")

    print("\n1. Start, in Catalan, at level 4")
    status, step, ms = call("/api/start", {"name": NAME, "language": "cat", "level": 4})
    problem = step["problem"]
    ok(status == 200 and problem["level"] == 4, f"got {problem['id']}, topic '{problem['topic_name']}' ({ms:.0f} ms)")
    ok(hides_answer(step), "the problem comes without its answer")
    ok(problem["ladder"][-1] == "solution", f"its ladder: {' > '.join(problem['ladder'])}")

    print("\n2. A wrong answer must not reveal the right one")
    wrong = None
    for _attempt in range(8):
        status, reply, ms = call("/api/answer", {"name": NAME, "id": problem["id"], "choice": "A"})
        if not reply["correct"]:
            wrong = "A"
            break
        # Right by luck: take the next problem and try again
        _, step, _ = call("/api/next", {"name": NAME})
        problem = step["problem"]
    ok(wrong is not None, f"answered {wrong} on {problem['id']}: wrong ({ms:.0f} ms)")
    ok(hides_answer(reply), "the reply to a wrong answer hides the solution")
    status, reply, _ = call("/api/answer", {"name": NAME, "id": problem["id"], "choice": wrong})
    ok(status == 400, "the same wrong letter can't be sent twice")

    print("\n3. Climb the ladder")
    level = problem["level"]
    for rung_type in problem["ladder"]:
        status, hint, ms = call("/api/hint", {"name": NAME, "id": problem["id"]})
        ok(status == 200 and hint["type"] == rung_type, f"rung {hint['rung']}: {rung_type} ({ms:.0f} ms)")
        if rung_type == "similar":
            warm = hint["problem"]
            ok(warm["level"] <= level and warm["id"] != problem["id"],
               f"  an easier problem: {warm['id']}, level {warm['level']} (was {level}), similarity {hint['similarity']}")
            ok(hides_answer(hint), "  the warm-up comes without its answer")
            tries = 0
            for letter in "ABCDE":
                tries += 1
                _, reply, _ = call("/api/answer", {"name": NAME, "id": warm["id"], "choice": letter})
                if reply["correct"]:
                    break
                ok(hides_answer(reply), f"  warm-up, wrong letter {letter}: solution still hidden")
            ok(reply["correct"] and reply["warmup"], f"  warm-up solved after {tries} tries")
        elif rung_type in ("method", "model"):
            ok(hides_answer(hint) and len(hint["text"]) > 10, f"  \"{hint['text']}\"")
        else:
            ok(hint["value"] == problem["options"][hint["label"]],
               f"  only now the answer: {hint['label']}) {hint['value']}")

    print("\n4. After the solution")
    status, reply, _ = call("/api/answer", {"name": NAME, "id": problem["id"], "choice": hint["label"]})
    ok(status == 400, "no more answers count on a revealed problem")
    status, reply, _ = call("/api/hint", {"name": NAME, "id": problem["id"]})
    ok(status == 400, "no more hints either")

    print("\n5. The next problem adapts")
    status, step, ms = call("/api/next", {"name": NAME})
    expected = max(level - 1, 0)
    ok(status == 200 and step["level"] == expected,
       f"needed the solution at level {level}, so the next one is level {step['level']} ({ms:.0f} ms)")
    same = "the same topic" if step["problem"]["topic"] == problem["topic"] else "another topic"
    print(f"        {same}: {step['problem']['topic_name']}")
    easy = step["problem"]

    print("\n6. Progress, kept on the board")
    status, progress, ms = call(f"/api/progress?name={NAME}")
    ok(status == 200 and progress["tried"] >= 1 and progress["level"] == expected,
       f"tried {progress['tried']}, solved {progress['solved']}, hints {progress['hints']}, level {progress['level']} ({ms:.0f} ms)")

    print("\n7. Bad requests")
    status, _, _ = call("/api/answer", {"name": "nobody-here", "id": easy["id"], "choice": "A"})
    ok(status == 400, "an unknown student is refused")
    status, _, _ = call("/api/start", {"name": NAME, "language": "xx", "level": 99})
    ok(status == 400, "a bad language or level is refused")

    if ASK:
        print("\n8. Ask the coach, live (the only step that waits for the language model)")
        ok(info.get("coach"), "the server has a coach")
        for question in ("Per on puc començar?", "Quina és la resposta correcta?"):
            status, reply, ms = call("/api/ask", {"name": NAME, "id": easy["id"], "question": question})
            ok(status == 200 and hides_answer(reply), f"asked: \"{question}\" ({ms / 1000:.1f} s)")
            label = "REPLACED by the method tip, the model's reply failed the checks" if reply["replaced"] else "the model"
            print(f"        {label}: \"{reply['text']}\"")
        status, reply, _ = call("/api/ask", {"name": NAME, "id": easy["id"], "question": "?"})
        ok(status == 400, "an empty question is refused")

    print(f"\nAll {passed} checks passed.")


if __name__ == "__main__":
    main()
