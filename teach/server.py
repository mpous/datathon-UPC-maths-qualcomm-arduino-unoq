#!/usr/bin/env python3
"""Teach mode web page: the student tries a problem, asks for hints, checks an answer, practises a similar one.

    python3 teach/server.py
    python3 teach/server.py --input data/demo/practice.jsonl --input data/val.jsonl --host 0.0.0.0

Then open http://127.0.0.1:8000 on the board, or from a laptop after `adb forward tcp:8000 tcp:8000`.
Needs the language model (LLM_PORT) for hints and the embedding server (EMBED_PORT) for similar problems.
Standard library only. The owl's eyes follow along when owl_eyes/python/eyes_bridge.py is available.
"""
import argparse
import json
import os
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from copilot.client import get  # noqa: E402
from copilot.config import CONFIG  # noqa: E402
from copilot.rag import Index  # noqa: E402
from copilot import teach  # noqa: E402

HERE = Path(__file__).resolve().parent

try:  # the LED matrix, only inside an App Lab app on the board
    sys.path.insert(0, str(ROOT / "owl_eyes" / "python"))
    from eyes_bridge import set_state as _eyes  # type: ignore
except Exception:  # noqa: BLE001 - laptop, or no Bridge: the page works without the eyes
    _eyes = None


def eyes(state):
    if _eyes:
        try:
            _eyes(state)
        except Exception:  # noqa: BLE001 - the eyes must never break the lesson
            pass


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", action="append", help="jsonl of problems (repeatable); default: practice + val")
    p.add_argument("--images", action="append", help="image folders (repeatable)")
    p.add_argument("--index", default="data/index.db", help="retrieval index from build_index.py")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 opens it to your network")
    p.add_argument("--port", type=int, default=8000)
    return p.parse_args()


def key_of(problem):
    return f"{problem['id']}_{problem.get('language', 'eng')}"


def is_up(port):
    try:
        return get(f"http://127.0.0.1:{port}/health", timeout=2).get("status") == "ok"
    except (OSError, ValueError):
        return False


class App:
    def __init__(self, args):
        inputs = args.input or [p for p in ("data/demo/practice.jsonl", "data/val.jsonl") if (ROOT / p).exists()]
        self.images = [ROOT / d for d in (args.images or ["data/demo/images", "data/images"])]
        self.problems, self.source = [], {}
        for path in inputs:
            for line in open(ROOT / path, encoding="utf-8"):
                if line.strip():
                    p = json.loads(line)
                    self.problems.append(p)
                    self.source[key_of(p)] = Path(path).stem
        self.by_key = {key_of(p): p for p in self.problems}
        self.lessons = {}  # key -> teach.Lesson (solving in the background since the problem was opened)
        self.index = Index(str(ROOT / args.index)) if (ROOT / args.index).exists() else None
        if self.index:  # similar problems come from the index: make them checkable too
            for _key, p, _vec in self.index.rows:
                self.by_key.setdefault(key_of(p), p)
                self.source.setdefault(key_of(p), "bank")

    def image_path(self, key):
        for folder in self.images:
            f = folder / f"{key}.png"
            if f.exists():
                return f
        return None

    def public(self, p):
        """A problem without its label, so the page can't give the answer away."""
        shown = {k: v for k, v in p.items() if k != "label"}
        shown.update(key=key_of(p), source=self.source.get(key_of(p), ""), image=bool(self.image_path(key_of(p))))
        return shown

    def lesson(self, key, problem):
        """The lesson for this problem, started on first use. Typed problems get a fresh one each time."""
        if key not in self.lessons:
            if len(self.lessons) > 50:
                self.lessons.clear()
            self.lessons[key] = teach.Lesson(problem)
            eyes("thinking")
            threading.Thread(target=lambda: (self.lessons[key].done.wait(120), eyes("idle")), daemon=True).start()
        return self.lessons[key]

    def info(self):
        return {"count": len(self.problems), "index": len(self.index.rows) if self.index else 0,
                "llm": is_up(CONFIG["LLM_PORT"]), "embed": is_up(CONFIG["EMBED_PORT"]), "eyes": bool(_eyes)}

    def listing(self):
        return [{"key": key_of(p), "id": p["id"], "language": p.get("language", ""), "level": p.get("level"),
                 "source": self.source.get(key_of(p), ""), "options": bool(p.get("options"))}
                for p in self.problems]


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            sys.stderr.write("  " + fmt % args + "\n")

        def send(self, code, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path, _, query = self.path.partition("?")
            params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
            if path == "/":
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/info":
                return self.send(200, app.info())
            if path == "/api/problems":
                return self.send(200, app.listing())
            if path == "/api/problem" and params.get("key") in app.by_key:
                return self.send(200, app.public(app.by_key[params["key"]]))
            if path.startswith("/image/"):
                key = path[len("/image/"):]
                f = app.image_path(key) if key in app.by_key else None  # only known keys reach the disk
                if f:
                    return self.send(200, f.read_bytes(), "image/png")
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/eyes":
                eyes(str(body.get("state", "idle")))
                return self.send(200, {"ok": True})
            # A problem from the list, or one the student typed (no answer key: hints only)
            key = body.get("key")
            problem = app.by_key.get(key)
            if problem is None and isinstance(body.get("problem"), dict):  # typed by the student: no answer key
                problem = {k: body["problem"].get(k) for k in ("text", "options", "language", "level")}
                problem["id"] = key = "typed-" + str(abs(hash(json.dumps(problem, sort_keys=True))))
            if not isinstance(problem, dict) or not problem.get("text"):
                return self.send(404, {"error": "unknown problem"})
            try:
                if self.path == "/api/open":  # start thinking while the student reads
                    lesson = app.lesson(key, problem)
                    return self.send(200, {"key": key, "solving": not lesson.done.is_set()})
                if self.path == "/api/hint":
                    return self.stream_hint(problem, int(body.get("level", 1)), app.lesson(key, problem))
                if self.path == "/api/check" and body.get("choice") in list("ABCDE"):
                    result = teach.check(problem, body["choice"])
                    eyes("correct" if result["correct"] else "wrong" if result["correct"] is False else "idle")
                    return self.send(200, result)
                if self.path == "/api/similar":
                    if not app.index:
                        return self.send(200, [])
                    hits = teach.similar(problem, app.index, k=int(body.get("k", 3)))
                    return self.send(200, [{"score": round(s, 3), **app.public(p)} for s, p in hits])
            except (OSError, urllib.error.URLError) as error:
                eyes("idle")
                return self.send(502, {"error": f"model server: {error}"})
            return self.send(400, {"error": "bad request"})

        def stream_hint(self, problem, level, lesson):
            """Server-sent events: one 'data:' line per sentence ({source, text}), then 'event: done'."""
            level = min(max(level, 1), 3)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if level > 1 and not lesson.done.is_set():
                eyes("thinking")
                self.wfile.write(b"event: thinking\ndata: 1\n\n")
                self.wfile.flush()
            sent = 0
            try:
                for source, sentence in teach.stream_hint(problem, level, lesson):
                    if sent == 0:
                        eyes("hint")
                    item = {"source": source, "text": sentence}
                    self.wfile.write(f"data: {json.dumps(item, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                    sent += 1
            except (OSError, urllib.error.URLError) as error:
                self.wfile.write(f"event: error\ndata: {json.dumps(str(error))}\n\n".encode())
            self.wfile.write(f"event: done\ndata: {sent}\n\n".encode())
            self.wfile.flush()
            self.close_connection = True

    return Handler


def main():
    args = parse_args()
    os.chdir(ROOT)
    app = App(args)
    info = app.info()
    print(f"{info['count']} problems, {info['index']} in the similar-problem index; "
          f"language model {'up' if info['llm'] else 'DOWN'}, embeddings {'up' if info['embed'] else 'DOWN'}, "
          f"owl eyes {'on' if info['eyes'] else 'off'}")
    print(f"Open http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(app)).serve_forever()


if __name__ == "__main__":
    main()
