#!/usr/bin/env python3
"""The Teach copilot's web server: a hint ladder and an adaptive trainer.

    python3 coach/build_bank.py          # once, after step 12
    python3 coach/server.py --host 0.0.0.0

Then open http://<board-ip>:8000. Standard library only, like the rest of the
code on the board. No language model runs while the student waits, except when
they choose to ask the coach a question (about 20 seconds, checked in code).

If the LED app (coach/applab) is running, the board's matrix shows a tick, a
cross, the level, or the rung of the ladder. Without it, the page works the same.

    python3 coach/server.py --host 0.0.0.0 --review

adds /review, where a teacher reads the model's hints and keeps or rejects each one.
"""
import argparse
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from copilot.config import ROOT  # noqa: E402
from coach.coach import ask_model  # noqa: E402
from coach.core import LEVELS, Bank, Trainer  # noqa: E402

# Pages that come with the repository's web client, served as they are if present
EXTRA_PAGES = {"/home": "index.html", "/analytics": "analytics.html"}


def make_led(base):
    """Return led(kind, value) that tells the LED app what to draw, and never blocks."""
    def send(kind, value):
        try:
            urllib.request.urlopen(f"{base}/led/{kind}/{value}", timeout=1).read()
        except OSError:
            pass  # the LED app is optional

    def led(kind, value=0):
        threading.Thread(target=send, args=(kind, value), daemon=True).start()
    return led


def make_handler(trainer, bank, review=False):
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

        def page(self, path):
            with open(path, "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            params = dict(urllib.parse.parse_qsl(url.query))
            if url.path == "/":
                return self.page(os.path.join(HERE, "public", "index.html"))
            if url.path in EXTRA_PAGES:
                extra = os.path.join(ROOT, "web", "public", EXTRA_PAGES[url.path])
                if os.path.exists(extra):
                    return self.page(extra)
            if url.path == "/api/info":
                return self.send(200, {
                    "problems": len(bank.level), "languages": bank.languages, "levels": list(LEVELS),
                    "hints": bank.hint_count(), "coach": trainer.coach is not None,
                    "extra_pages": [p for p, f in EXTRA_PAGES.items()
                                    if os.path.exists(os.path.join(ROOT, "web", "public", f))]})
            if review and url.path == "/review":
                return self.page(os.path.join(HERE, "public", "review.html"))
            if review and url.path == "/api/hints":
                return self.send(200, bank.all_hints())
            if url.path == "/api/progress":
                return self.call(trainer.progress, params.get("name", ""))
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                return self.send(400, {"error": "bad JSON"})
            if review and self.path == "/api/review":
                if not bank.has(body.get("id"), body.get("language")):
                    return self.send(400, {"error": "unknown problem"})
                return self.send(200, bank.review_hint(body["id"], body["language"], bool(body.get("keep"))))
            name = str(body.get("name", "")).strip()[:40]
            if not name:
                return self.send(400, {"error": "who are you?"})
            if self.path == "/api/start":
                return self.call(trainer.start, name, body.get("language"), body.get("level"))
            if self.path == "/api/answer":
                return self.call(trainer.answer, name, body.get("id"), body.get("choice"))
            if self.path == "/api/hint":
                return self.call(trainer.hint, name, body.get("id"))
            if self.path == "/api/ask":
                return self.call(trainer.ask, name, body.get("id"), body.get("question", ""))
            if self.path == "/api/next":
                return self.call(trainer.next, name)
            return self.send(404, {"error": "not found"})

        def call(self, function, *args):
            try:
                return self.send(200, function(*args))
            except (KeyError, ValueError) as error:
                return self.send(400, {"error": str(error).strip("'")})

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db", help="written by coach/build_bank.py")
    p.add_argument("--profile", default="data/teach_profile.db", help="the students' progress, kept on the board")
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it to your network")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--led", default="http://127.0.0.1:7000", help="the LED app's address")
    p.add_argument("--no-coach", action="store_true",
                   help="turn off 'ask the coach', the only step that waits for the language model")
    p.add_argument("--review", action="store_true",
                   help="also serve /review, the teacher's page to keep or reject the model's hints. "
                        "It shows the answers: don't use it while students are on the network")
    args = p.parse_args()
    os.chdir(ROOT)
    if not os.path.exists(args.bank):
        sys.exit(f"{args.bank} not found. Build it first: python3 coach/build_bank.py")

    bank = Bank(args.bank)
    trainer = Trainer(bank, args.profile, led=make_led(args.led), coach=None if args.no_coach else ask_model)
    print(f"{len(bank.level)} problems in {', '.join(bank.languages)}, {bank.hint_count()} model hints ready")
    print(f"Open http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    if args.review:
        print(f"Teacher's review page: http://{args.host}:{args.port}/review (it shows the answers)")
    ThreadingHTTPServer((args.host, args.port), make_handler(trainer, bank, review=args.review)).serve_forever()


if __name__ == "__main__":
    main()
