#!/usr/bin/env python3
"""One web app for the team, served by the board: web2's shell, web1's Agent and Uploader, and the Coach.

    python3 coach/build_bank.py            # once
    python3 web3/server.py --host 0.0.0.0  # then open http://<board-ip>:8000

Standard library only: the board has no Node.

- The Coach's routes are the ones of coach/server.py, under /api/coach/.
- The Agent's and the Uploader's routes have the shapes of web1/server.js. "Ask the model"
  runs machine/predict_one.py against the llama-server that is already running (LLM_PORT in
  config.env), so nothing starts a second model.
- Reading a picture needs RapidOCR (m3kang/image_to_json.py). Where it isn't installed, the
  Uploader says so, and the pasted-text route still works.
- "Save" appends to data/uploaded.jsonl. It never touches val.jsonl, the evaluation set.
"""
import argparse
import base64
import datetime
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from copilot.config import CONFIG, ROOT  # noqa: E402
from coach.coach import ask_model  # noqa: E402
from coach.core import Bank, Trainer  # noqa: E402
from coach.server import make_handler as coach_handler, make_led  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

ROOT = str(ROOT)
PUBLIC = os.path.join(HERE, "public")
SHELL_ROUTES = {"/", "/home", "/coach", "/teach", "/solver", "/agent", "/uploader", "/analytics"}
VARIANTS = ("letter", "cot", "pot", "official")
UPLOADER_ROUTES = ("/api/upload-ocr", "/api/upload-solve", "/api/structure-text", "/api/solve-json",
                   "/api/save-problem")
LLM = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
LETTERS = "ABCDE"
MAX_BODY = 15 * 1024 * 1024
UPLOADED = os.path.join(ROOT, "data", "uploaded.jsonl")
IMAGES = os.path.join(ROOT, "data", "images")
OCR_SCRIPT = os.path.join(ROOT, "m3kang", "image_to_json.py")
# RapidOCR lives in the laptop's virtual environment, when there is one
OCR_PYTHON = os.environ.get("OCR_PYTHON") or next(
    (p for p in (os.path.join(ROOT, ".venv", "bin", "python"), os.path.join(ROOT, ".venv", "Scripts", "python.exe"))
     if os.path.exists(p)), sys.executable)


class Refused(Exception):
    """A request we answer with an error message and a status code."""
    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code, self.extra = code, extra


def model_name():
    try:
        with urllib.request.urlopen(LLM + "/v1/models", timeout=2) as r:
            return os.path.basename(json.load(r)["data"][0]["id"])
    except (OSError, ValueError, KeyError, IndexError):
        return ""


def key_of(problem):
    return f"{problem['id']}_{problem['language']}"


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Problems:
    """The problems the Agent lists: data/val.jsonl (or the first file that exists), then the uploaded ones."""
    def __init__(self):
        self.path = next((p for p in (os.path.join(ROOT, "data", n) for n in
                                      ("val.jsonl", "train.jsonl", "sample_problems.jsonl")) if os.path.exists(p)), "")
        self.lock = threading.Lock()
        self.load()

    def load(self):
        self.by_key = {}  # key -> (file, 1-based line, problem)
        for path in (self.path, UPLOADED):
            for n, problem in enumerate(read_jsonl(path) if path else [], 1):
                self.by_key[key_of(problem)] = (path, n, problem)

    def all(self):
        return [entry[2] for entry in self.by_key.values()]

    def image(self, key):
        path = os.path.join(IMAGES, key + ".png")
        return path if key in self.by_key and os.path.exists(path) else ""

    def public(self, key):
        problem = {k: v for k, v in self.by_key[key][2].items() if k != "label"}
        return {**problem, "key": key, "image": bool(self.image(key))}

    def save(self, problem, image=b""):
        with self.lock:
            with open(UPLOADED, "a", encoding="utf-8") as f:
                f.write(json.dumps(problem, ensure_ascii=False) + "\n")
            if image:
                os.makedirs(IMAGES, exist_ok=True)
                with open(os.path.join(IMAGES, key_of(problem) + ".png"), "wb") as f:
                    f.write(image)
            self.load()


# --- Text to a structured problem (web1's parser, in Python) ---

LANGUAGE_WORDS = (
    ("cat", r"\b(què|quants|quantes|quin|quina|quins|quines|dels|pels|amb|això|és|són)\b"),
    ("esp", r"\b(qué|cuántos|cuántas|cuál|cuáles|los|las|del|con|una|está|son)\b"),
    ("fra", r"\b(quel|quelle|quels|quelles|combien|les|des|avec|dans|est|sont)\b"),
    ("deu", r"\b(welche|welcher|welches|wie viele|der|die|das|und|mit|ist|sind)\b"),
)
MARKER = re.compile(r"(?:^|[\s\n])[\(\[]?([A-E])[\)\]\.:]\s*")


def detect_language(text):
    lower = f" {str(text or '').lower()} "
    return next((lang for lang, words in LANGUAGE_WORDS if re.search(words, lower)), "eng")


def number(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def label_of(value):
    value = str(value or "").upper()
    return value if value in tuple(LETTERS) else ""


def this_year():
    return datetime.date.today().year


def normalize(problem):
    """Any JSON a person typed -> a problem with every M3Kang field."""
    options = problem.get("options") if isinstance(problem.get("options"), dict) else {}
    options = {l: str(options[l]).strip() for l in LETTERS if str(options.get(l, "")).strip()}
    text = str(problem.get("text") or "").strip()
    level = number(problem.get("level"), 0)
    return {"id": str(problem.get("id") or f"lvl-{level}_{this_year()}_custom").strip(),
            "language": str(problem.get("language") or detect_language(text)).lower(),
            "level": level, "year": number(problem.get("year"), this_year()),
            "text_only": len(options) == 5, "text": text, "options": options, "label": label_of(problem.get("label"))}


def structure(raw, given):
    """Split pasted text into the statement and the options A-E: the last run of markers A, B, C, D, E."""
    raw = str(raw or "").replace("\r\n", "\n").strip()
    marks = [(m.group(1), m.start(), m.end()) for m in MARKER.finditer(raw)]
    statement, options = raw, {}
    for i in range(len(marks) - 1, -1, -1):
        if marks[i][0] != "A":
            continue
        run = [marks[i]]
        for mark in marks[i + 1:]:
            if len(run) < 5 and mark[0] == LETTERS[len(run)]:
                run.append(mark)
        if len(run) == 5:
            ends = [mark[1] for mark in run[1:]] + [len(raw)]
            found = {LETTERS[k]: re.sub(r"\s+", " ", raw[run[k][2]:ends[k]]).strip() for k in range(5)}
            if all(found.values()):
                statement, options = raw[:run[0][1]].strip(), found
            break
    question = re.match(r"(\d{1,2})\s*[.)]\s+", statement)
    level = number(given.get("level"), 0)
    year = number(given.get("year"), this_year())
    language = str(given.get("language") or "auto").lower()
    return {"id": str(given.get("id") or "").strip() or f"lvl-{level}_{year}_{question.group(1) if question else 1}",
            "language": detect_language(statement) if language == "auto" else language,
            "level": level, "year": year, "text_only": len(options) == 5, "text": statement, "options": options,
            "label": label_of(given.get("label"))}


def structure_with_model(raw, given):
    """The same, then the board's model cleans the text. If its JSON is no good, the parser's result stays."""
    problem = structure(raw, given)
    prompt = ("Extract the math problem statement and the five options A, B, C, D, E from the raw text below. "
              "Fix obvious OCR spacing issues without changing the language or numbers. "
              "Reply ONLY with valid JSON matching: "
              '{"text": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}.\n\n'
              "Raw text:\n" + str(raw))
    payload = {"messages": [{"role": "system", "content": "You convert raw math exam text into clean JSON."},
                            {"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 512}
    request = urllib.request.Request(LLM + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=170) as r:
            content = json.load(r)["choices"][0]["message"]["content"]
        cleaned = json.loads(re.search(r"\{[\s\S]*\}", content).group(0))
    except (OSError, ValueError, KeyError, IndexError, AttributeError):
        return {"problem": problem, "method": "parser (the model's reply wasn't valid JSON)"}
    if isinstance(cleaned.get("text"), str) and cleaned["text"].strip():
        problem["text"] = cleaned["text"].strip()
    options = cleaned.get("options") if isinstance(cleaned.get("options"), dict) else {}
    options = {l: str(options[l]).strip() for l in LETTERS if str(options.get(l, "")).strip()}
    if len(options) == 5:
        problem["options"], problem["text_only"] = options, True
    return {"problem": problem, "method": f"ai ({model_name().replace('.gguf', '') or 'model'})"}


# --- A picture to a structured problem (m3kang/image_to_json.py, RapidOCR) ---

_ocr_ready = None


def ocr_ready():
    global _ocr_ready
    if _ocr_ready is None:
        try:
            _ocr_ready = os.path.exists(OCR_SCRIPT) and subprocess.run(
                [OCR_PYTHON, "-c", "import rapidocr_onnxruntime"], capture_output=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _ocr_ready = False
    return _ocr_ready


def decode_image(data_url, filename=""):
    match = re.match(r"data:image/([a-zA-Z0-9+.-]+);base64,(.+)$", str(data_url or ""), re.S)
    if not match:
        raise Refused(400, "That isn't a picture we can read. Upload a PNG, JPG or WEBP file.")
    kinds = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg", "webp": ".webp", "bmp": ".bmp"}
    try:
        return base64.b64decode(match.group(2)), kinds.get(match.group(1).lower()) or os.path.splitext(filename)[1] or ".png"
    except ValueError:
        raise Refused(400, "The picture arrived damaged. Try again.")


def ocr(body):
    """Read an uploaded picture. A file name like lvl-0_2026_1_eng.png gives the id, level, year and language."""
    if not ocr_ready():
        raise Refused(501, "This device can't read pictures: RapidOCR isn't installed here. "
                           "Paste the problem's text in step 2 instead.")
    image, ext = decode_image(body.get("image_base64"), str(body.get("filename") or ""))
    stem = os.path.splitext(os.path.basename(str(body.get("filename") or "uploaded.png")))[0]
    named = re.match(r"(lvl-(\d+)_(\d{4})_([^_]+))_([a-z]{2,3})$", stem, re.I)
    year = number(body.get("year"), int(named.group(3)) if named else this_year())
    level = number(body.get("level") if body.get("level") not in (None, "") else None, int(named.group(2)) if named else 0)
    language = str(body.get("language") or "auto").lower()
    language = (named.group(5).lower() if named else "") if language == "auto" else language
    pid = str(body.get("id") or "").strip() or (
        named.group(1) if named else f"lvl-{level}_{year}_{re.sub(r'[^a-zA-Z0-9_-]', '', stem)[:20] or 'custom'}")

    with tempfile.TemporaryDirectory() as folder:
        picture, out = os.path.join(folder, "picture" + ext), os.path.join(folder, "ocr.jsonl")
        with open(picture, "wb") as f:
            f.write(image)
        try:
            run = subprocess.run([OCR_PYTHON, OCR_SCRIPT, "--image", picture, "--out", out, "--no-cache",
                                  "--default-language", language or "eng"], capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise Refused(500, "Reading the picture took more than 120 seconds.")
        rows = read_jsonl(out)
        if run.returncode != 0 or not rows:
            raise Refused(500, "Reading the picture failed: " + (run.stderr or run.stdout).strip()[-400:])
    text = str(rows[0].get("text") or "")
    options = rows[0].get("options") or {}
    problem = {"id": pid, "language": language or detect_language(text), "level": level, "year": year,
               "text_only": len(options) == 5, "text": text, "options": options, "label": label_of(body.get("label"))}
    option_line = "   ".join(f"{l}) {options[l]}" for l in LETTERS if options.get(l))
    return {"problem": problem, "rawText": "\n".join(part for part in (text, option_line) if part)}


# --- Ask the model (machine/predict_one.py, the same script web1 runs) ---

def prompt_of(problem):
    options = problem.get("options") or {}
    lines = [f"{l}) {options[l]}" for l in LETTERS if options.get(l) not in (None, "")]
    return problem["text"] + ("\n\n" + "\n".join(lines) if lines else "")


def predict(path, index, problem, body, default_tokens):
    """Run predict_one.py on line `index` of `path` and shape the result like web1's buildPredictionResponse."""
    variant = body.get("variant") if body.get("variant") in VARIANTS else "cot"
    tokens = max(1, min(2048, number(body.get("max_tokens"), default_tokens)))
    script = os.path.join(ROOT, "machine", "predict_one.py")
    out = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    out.close()
    command = [sys.executable, script, "--input", path, "--index", str(index), "--variant", variant,
               "--max-tokens", str(tokens), "--port", str(CONFIG["LLM_PORT"]), "--out", out.name]
    shown = "python3 machine/predict_one.py " + " ".join(command[2:-2])
    started = time.time()
    try:
        run = subprocess.run(command, cwd=os.path.dirname(script), capture_output=True, text=True, timeout=150)
        rows = read_jsonl(out.name)
    except subprocess.TimeoutExpired:
        raise Refused(500, "The model took more than 150 seconds.", command=shown)
    finally:
        os.unlink(out.name)
    if run.returncode != 0 or not rows:
        raise Refused(500, f"predict_one.py ended with code {run.returncode}",
                      raw_output=(run.stdout + "\n" + run.stderr).strip()[-3000:], command=shown)
    rec = rows[-1]
    lp = rec.get("lp")
    answer = max(LETTERS, key=lambda l: lp.get(l, float("-inf"))) if lp else rec.get("answer")
    text = [rec.get("thought"), f"Expression: {rec['expr']}" if rec.get("expr") else "",
            f"Value: {rec['value']}" if rec.get("value") is not None else "",
            f"Match: {rec['match']}" if rec.get("match") else "",
            rec.get("content") if not rec.get("thought") else ""]
    label = label_of(problem.get("label"))
    return {"answer": answer, "thought": "\n".join(str(part) for part in text if part),
            "model": model_name().replace(".gguf", ""), "variant": variant, "status": rec.get("status", "ok"),
            "seconds": round(time.time() - started, 1),
            "prompt_tokens": rec.get("read_tokens", rec.get("prompt_tokens", 0)),
            "written_tokens": rec.get("written_tokens", 0), "lp": lp, "has_label": bool(label),
            "correct": answer == label if label else None, "label": label, "prompt": prompt_of(problem),
            "command": shown, "examples": []}


def predict_new(problem, body):
    """The same for a problem that isn't in a file yet: write it to a file of one line."""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(json.dumps(problem, ensure_ascii=False) + "\n")
    try:
        return predict(f.name, 1, problem, body, 150)
    finally:
        os.unlink(f.name)


def make_handler(trainer, bank, problems, review):
    busy = threading.Lock()  # the board's model has one slot: one prediction at a time

    class Handler(coach_handler(trainer, bank, review=review)):
        def static(self, path):
            if path in SHELL_ROUTES:
                path = "/index.html"
            full = os.path.realpath(os.path.join(PUBLIC, path.lstrip("/")))
            if not full.startswith(os.path.realpath(PUBLIC) + os.sep) or not os.path.isfile(full):
                return self.send(404, {"error": "not found"})
            kind = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind.endswith("javascript"):
                kind += "; charset=utf-8"
            with open(full, "rb") as f:
                return self.send(200, f.read(), kind)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            params = dict(urllib.parse.parse_qsl(url.query))
            if url.path.startswith("/api/coach/"):
                self.path = "/api/" + self.path[len("/api/coach/"):]
                return super().do_GET()
            if url.path in ("/review", "/api/hints"):  # the teacher's page, only with --review
                return super().do_GET()
            if url.path == "/api/info":
                name, items = model_name(), problems.all()
                return self.send(200, {
                    "count": len(items), "languages": sorted({p["language"] for p in items}),
                    "levels": sorted({p["level"] for p in items}),
                    "images": sum(1 for k in problems.by_key if problems.image(k)), "index": 0,
                    "llm": bool(name), "models": [name] if name else [], "model": name,
                    "embed": False, "vision": False, "time_limit": 60, "ocr": ocr_ready()})
            if url.path == "/api/problems":
                return self.send(200, [{"key": k, "id": p["id"], "language": p["language"], "level": p["level"],
                                        "options": bool(p.get("options"))} for k, (_, _, p) in problems.by_key.items()])
            if url.path == "/api/problem":
                if params.get("key") not in problems.by_key:
                    return self.send(404, {"error": "unknown problem"})
                return self.send(200, problems.public(params["key"]))
            if url.path == "/api/similar":
                return self.send(200, [])
            if url.path.startswith("/image/"):
                image = problems.image(urllib.parse.unquote(url.path[len("/image/"):]))
                if not image:
                    return self.send(404, {"error": "image not found"})
                with open(image, "rb") as f:
                    return self.send(200, f.read(), "image/png")
            if url.path.startswith("/api/"):
                return self.send(404, {"error": "not found"})
            return self.static(url.path)

        def do_POST(self):
            if self.path.startswith("/api/coach/"):
                self.path = "/api/" + self.path[len("/api/coach/"):]
                return super().do_POST()
            if self.path == "/api/review":
                return super().do_POST()
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size > MAX_BODY:
                    return self.send(413, {"error": "That's too big: 15 MB at most."})
                body = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self.send(400, {"error": "bad JSON"})
            try:
                return self.send(200, self.route(body))
            except Refused as refused:
                return self.send(refused.code, {"error": str(refused), **refused.extra})

        def with_model(self, function, *args):
            if not busy.acquire(blocking=False):
                raise Refused(429, "The board is already working on a problem. Wait for it to finish.")
            try:
                return function(*args)
            finally:
                busy.release()

        def route(self, body):
            entry = problems.by_key.get(body.get("key"))
            if self.path == "/api/check":
                if not entry or body.get("choice") not in tuple(LETTERS):
                    raise Refused(400, "bad request")
                return {"correct": body["choice"] == entry[2].get("label"), "label": entry[2].get("label", "")}
            if self.path == "/api/ask":
                if not entry:
                    raise Refused(404, "unknown problem")
                return self.with_model(predict, entry[0], entry[1], entry[2], body, 120)
            if self.path == "/api/structure-text":
                if not str(body.get("raw_text") or "").strip():
                    raise Refused(400, "Paste the problem's text first.")
                if body.get("use_ai"):
                    return self.with_model(structure_with_model, body["raw_text"], body)
                return {"problem": structure(body["raw_text"], body), "method": "parser"}
            if self.path == "/api/solve-json":
                given = body.get("problem")
                if not isinstance(given, dict) or not str(given.get("text") or "").strip():
                    raise Refused(400, "The JSON needs at least the field 'text'.")
                problem = normalize(given)
                return {"problem": problem, "prediction": self.with_model(predict_new, problem, body)}
            if self.path == "/api/upload-ocr":
                return ocr(body)
            if self.path == "/api/upload-solve":
                read = ocr(body)
                try:
                    prediction = self.with_model(predict_new, read["problem"], body)
                except Refused as refused:  # keep what OCR read, so the page can still show it
                    refused.extra.update(problem=read["problem"], raw_text=read["rawText"])
                    raise
                return {"problem": read["problem"], "raw_text": read["rawText"], "prediction": prediction}
            if self.path == "/api/save-problem":
                given = body.get("problem")
                if not isinstance(given, dict) or not given.get("id") or not str(given.get("text") or "").strip():
                    raise Refused(400, "The JSON needs 'id' and 'text'.")
                problem = normalize(given)
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", key_of(problem)):
                    raise Refused(400, "Use only letters, digits, '-', '_' and '.' in the id and the language.")
                entry = problems.by_key.get(key_of(problem))
                if entry and entry[0] != UPLOADED:
                    raise Refused(400, "That id is a problem of the dataset. Choose another id.")
                image = decode_image(body["image_base64"])[0] if body.get("image_base64") else b""
                problems.save(problem, image)
                return {"saved": True, "key": key_of(problem), "total": len(problems.by_key)}
            raise Refused(404, "not found")

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db", help="written by coach/build_bank.py")
    p.add_argument("--profile", default="data/teach_profile.db", help="the students' progress, kept on the board")
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open it to your network")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--led", default="http://127.0.0.1:7000", help="the LED app's address")
    p.add_argument("--no-coach", action="store_true", help="turn off 'ask the coach'")
    p.add_argument("--review", action="store_true", help="also serve /review (it shows the answers)")
    args = p.parse_args()
    os.chdir(ROOT)
    if not os.path.exists(args.bank):
        sys.exit(f"{args.bank} not found. Build it first: python3 coach/build_bank.py")

    bank = Bank(args.bank)
    trainer = Trainer(bank, args.profile, led=make_led(args.led), coach=None if args.no_coach else ask_model)
    problems = Problems()
    print(f"Coach: {len(bank.level)} problems, {bank.hint_count()} model hints. "
          f"Agent: {len(problems.by_key)} problems from {problems.path or 'nowhere'}. "
          f"Model {'up' if model_name() else 'DOWN'} on port {CONFIG['LLM_PORT']}. "
          f"OCR {'ready' if ocr_ready() else 'not installed'}.")
    print(f"Open http://{args.host}:{args.port} (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(trainer, bank, problems, args.review)).serve_forever()


if __name__ == "__main__":
    main()
