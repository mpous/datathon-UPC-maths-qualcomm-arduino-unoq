#!/usr/bin/env python3
"""M3Kang explorer: look at problems, answer them yourself, then ask the model.

    python3 explorer/server.py
    python3 explorer/server.py --input data/val.jsonl --images data/images --rag 1

Then open http://127.0.0.1:8000 in a browser on the board, or forward the
port to your laptop (see the README). Standard library only.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.client import get  # noqa: E402
from copilot.config import CONFIG, ROOT  # noqa: E402
from copilot.llm import build_messages  # noqa: E402
from copilot.pipeline import solve  # noqa: E402
from copilot.rag import Index  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LLM = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
EMBED = f"http://127.0.0.1:{CONFIG['EMBED_PORT']}"
VISION = f"http://127.0.0.1:{CONFIG['VISION_PORT']}"
# Reading an image takes the board much longer than reading text
VISION_TIME_LIMIT = 300


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/val.jsonl", help="problems to explore")
    p.add_argument("--images", default="data/images", help="folder written by prepare_m3kang.py --save-images")
    p.add_argument("--index", default="data/index.db", help="retrieval index from build_index.py")
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it to your network")
    p.add_argument("--port", type=int, default=8000)
    return p.parse_args()


def key_of(problem):
    return f"{problem['id']}_{problem['language']}"


def is_up(base):
    try:
        return get(base + "/health", timeout=2).get("status") == "ok"
    except (OSError, ValueError):
        return False


def sees_images(base):
    try:
        return bool(get(base + "/props", timeout=2).get("modalities", {}).get("vision"))
    except (OSError, ValueError):
        return False


def public(problem, images):
    """A problem without its label, so the page can't give the answer away."""
    shown = {k: v for k, v in problem.items() if k != "label"}
    shown["key"] = key_of(problem)
    shown["image"] = os.path.exists(os.path.join(images, key_of(problem) + ".png"))
    return shown


def printable(messages):
    """The prompt as plain text, with the image replaced by a marker."""
    lines = []
    for m in messages:
        content = m["content"]
        if isinstance(content, list):
            content = "\n".join("[image]" if part["type"] == "image_url" else part["text"] for part in content)
        lines.append(f"--- {m['role']} ---\n{content}")
    return "\n".join(lines)


class App:
    def __init__(self, args):
        os.chdir(ROOT)
        self.images = args.images
        with open(args.input) as f:
            self.problems = [json.loads(line) for line in f if line.strip()]
        self.by_key = {key_of(p): p for p in self.problems}
        self.index = Index(args.index) if os.path.exists(args.index) else None
        self.input = args.input
        # Images the page may ask for: the problems, and the solved problems in the index
        self.image_keys = set(self.by_key)
        if self.index:
            self.image_keys |= {row[0].replace("|", "_") for row in self.index.rows}

    def info(self):
        return {
            "input": self.input,
            "count": len(self.problems),
            "languages": sorted({p["language"] for p in self.problems}),
            "levels": sorted({p["level"] for p in self.problems}),
            "images": sum(os.path.exists(os.path.join(self.images, k + ".png")) for k in self.by_key),
            "index": len(self.index.rows) if self.index else 0,
            "llm": is_up(LLM),
            "embed": is_up(EMBED),
            "vision": is_up(VISION) and sees_images(VISION),
            "time_limit": float(CONFIG["TIME_LIMIT_SECONDS"]),
        }

    def listing(self):
        return [{"key": key_of(p), "id": p["id"], "language": p["language"], "level": p["level"],
                 "options": bool(p.get("options"))} for p in self.problems]

    def image_b64(self, key):
        with open(os.path.join(self.images, key + ".png"), "rb") as f:
            return base64.b64encode(f.read()).decode()

    def check(self, key, choice):
        label = self.by_key[key]["label"]
        return {"correct": choice == label, "label": label}

    def ask(self, key, rag, vision):
        problem = self.by_key[key]
        image = self.image_b64(key) if vision else None
        result = solve(problem, index=self.index if rag else None, k=rag, exclude_id=problem["id"],
                       image_b64=image, llm_url=(VISION if vision else LLM) + "/v1/chat/completions",
                       time_limit=VISION_TIME_LIMIT if vision else float(CONFIG["TIME_LIMIT_SECONDS"]))
        examples = [p for _score, p in result["examples"]]
        return {
            "answer": result["answer"],
            "status": result["status"],
            "seconds": result["seconds"],
            "prompt_tokens": result["prompt_tokens"],
            "correct": result["answer"] == problem["label"],
            "label": problem["label"],
            "prompt": printable(build_messages(problem, examples, image)),
            "examples": [{"score": round(s, 3), **public(p, self.images), "label": p["label"]}
                         for s, p in result["examples"]],
        }

    def similar(self, key, k):
        if not self.index:
            return []
        problem = self.by_key[key]
        hits = self.index.search(problem, k=k, exclude_id=problem["id"])
        return [{"score": round(s, 3), **public(p, self.images), "label": p["label"]} for s, p in hits]


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
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
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/info":
                return self.send(200, app.info())
            if path == "/api/problems":
                return self.send(200, app.listing())
            if path == "/api/problem" and params.get("key") in app.by_key:
                return self.send(200, public(app.by_key[params["key"]], app.images))
            if path == "/api/similar" and params.get("key") in app.by_key:
                return self.send(200, app.similar(params["key"], int(params.get("k", 3))))
            if path.startswith("/image/"):
                key = path[len("/image/"):]
                # Only known keys reach the disk, so a request can't name any other file
                file = os.path.join(app.images, key + ".png")
                if key in app.image_keys and os.path.exists(file):
                    with open(file, "rb") as f:
                        return self.send(200, f.read(), "image/png")
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            key = body.get("key")
            if key not in app.by_key:
                return self.send(404, {"error": "unknown problem"})
            try:
                if self.path == "/api/check" and body.get("choice") in list("ABCDE"):
                    return self.send(200, app.check(key, body["choice"]))
                if self.path == "/api/ask":
                    return self.send(200, app.ask(key, int(body.get("rag", 0)), bool(body.get("vision"))))
            except (OSError, urllib.error.URLError) as error:
                return self.send(502, {"error": f"model server: {error}"})
            return self.send(400, {"error": "bad request"})

    return Handler


def main():
    args = parse_args()
    app = App(args)
    info = app.info()
    print(f"{info['count']} problems from {args.input}, {info['images']} with images, "
          f"{info['index']} in the retrieval index")
    print(f"Servers: language model {'up' if info['llm'] else 'DOWN'}, "
          f"embeddings {'up' if info['embed'] else 'DOWN'}, "
          f"vision {'up' if info['vision'] else 'off'}")
    print(f"Open http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(app)).serve_forever()


if __name__ == "__main__":
    main()
