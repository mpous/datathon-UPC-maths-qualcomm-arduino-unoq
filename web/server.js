const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const { spawn } = require("node:child_process");

const VALIDATION_DATA = "val.jsonl";
const TRAIN_DATA = "val.jsonl";
const TEST_DATA = "";
const SAMPLE_PROBLEMS = "sample_problems.jsonl";

const DEFAULT_MODEL_GGUF = process.env.M3KANG_MODEL || "Qwen_Qwen3.5-0.8B-Q8_0.gguf";
const PREDICT_PORT = Number(process.env.M3KANG_PREDICT_PORT || 18111);

const PORT = Number(process.env.PORT || 3000);
const PUBLIC_DIR = path.join(__dirname, "public");
const PROJECT_DIR = path.resolve(__dirname, "..");

const VENV_PYTHON = [
  path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe"),
  path.join(PROJECT_DIR, ".venv", "bin", "python"),
  path.join(__dirname, ".venv", "Scripts", "python.exe"),
  path.join(__dirname, ".venv", "bin", "python"),
].find((p) => fs.existsSync(p));

const PYTHON_BIN =
  process.env.PYTHON_BIN ||
  VENV_PYTHON ||
  (process.platform === "win32" ? "python" : "python3");

const DATA_FILE = process.env.M3KANG_INPUT
  ? path.resolve(process.env.M3KANG_INPUT)
  : [
      path.join(PROJECT_DIR, "data", VALIDATION_DATA),
      path.join(PROJECT_DIR, "data", TRAIN_DATA),
      path.join(PROJECT_DIR, "data", SAMPLE_PROBLEMS),
    ].find((file) => fs.existsSync(file)) || path.join(PROJECT_DIR, "data", VALIDATION_DATA);

const IMAGE_DIR = process.env.M3KANG_IMAGES
  ? path.resolve(process.env.M3KANG_IMAGES)
  : path.join(PROJECT_DIR, "data", "images");

const MODELS_DIR = process.env.M3KANG_MODELS
  ? path.resolve(process.env.M3KANG_MODELS)
  : [
      path.join(PROJECT_DIR, "models"),
      path.join(__dirname, "models"),
    ].find((dir) => fs.existsSync(dir)) || path.join(PROJECT_DIR, "models");

const MACHINE_DIR = [
  path.join(PROJECT_DIR, "machine"),
  PROJECT_DIR,
  __dirname,
].find((dir) => fs.existsSync(path.join(dir, "predict_one.py"))) || path.join(PROJECT_DIR, "machine");

const PREDICT_SCRIPT = path.join(MACHINE_DIR, "predict_one.py");
const RUN_PREDICT_BAT = path.join(MACHINE_DIR, "run_predict.bat");

const IMAGE_TO_JSON_SCRIPT = [
  path.join(PROJECT_DIR, "laptop", "image_to_json.py"),
  path.join(PROJECT_DIR, "image_to_json.py"),
  path.join(MACHINE_DIR, "image_to_json.py"),
  path.join(__dirname, "image_to_json.py"),
].find((file) => fs.existsSync(file));

const TMP_WORK_DIR = path.join(MACHINE_DIR, ".tmp_web");

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

let activePrediction = false;

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(payload));
}

function problemKey(problem) {
  return `${problem.id}_${problem.language}`;
}

function listGgufModels() {
  try {
    if (!fs.existsSync(MODELS_DIR)) return [];
    return fs.readdirSync(MODELS_DIR)
      .filter((file) => file.toLowerCase().endsWith(".gguf"))
      .sort((a, b) => a.localeCompare(b));
  } catch (error) {
    console.error(`Could not list models in ${MODELS_DIR}: ${error.message}`);
    return [];
  }
}

function resolveSelectedModel(requestedModel) {
  const availableModels = listGgufModels();
  const safeName = requestedModel ? path.basename(String(requestedModel)) : "";
  if (
    safeName.toLowerCase().endsWith(".gguf") &&
    (availableModels.length === 0 || availableModels.includes(safeName))
  ) {
    return safeName;
  }
  if (availableModels.includes(DEFAULT_MODEL_GGUF)) return DEFAULT_MODEL_GGUF;
  return availableModels[0] || DEFAULT_MODEL_GGUF;
}

function loadProblems() {
  try {
    if (!fs.existsSync(DATA_FILE)) return [];
    return fs.readFileSync(DATA_FILE, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch (error) {
    console.error(`Could not load ${DATA_FILE}: ${error.message}`);
    return [];
  }
}

function argmaxLp(lp) {
  if (!lp || typeof lp !== "object") return null;
  let bestLetter = null;
  let bestScore = -Infinity;
  for (const letter of ["A", "B", "C", "D", "E"]) {
    const score = lp[letter];
    if (typeof score === "number" && Number.isFinite(score) && score > bestScore) {
      bestScore = score;
      bestLetter = letter;
    }
  }
  return bestLetter;
}

function formatPrompt(problem) {
  const options = problem.options || {};
  const optionLines = ["A", "B", "C", "D", "E"]
    .filter((letter) => options[letter] !== undefined && options[letter] !== "")
    .map((letter) => `${letter}) ${options[letter]}`);
  return optionLines.length
    ? `${problem.text}\n\n${optionLines.join("\n")}`
    : problem.text;
}

function isPortOpen(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const socket = net.createConnection({ port, host });
    socket.setTimeout(500);
    socket.on("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("error", () => {
      resolve(false);
    });
  });
}

function spawnAsync(cmd, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      ...options,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (err) => {
      resolve({ code: -1, stdout, stderr: `${stderr}\n${err.message}`.trim() });
    });
    child.on("close", (code) => {
      resolve({ code: code ?? 0, stdout, stderr });
    });
  });
}

// --- OCR on uploaded image (uses image_to_json.py or inline RapidOCR fallback) ---

const INLINE_OCR_SCRIPT = `
import json, os, re, sys
from rapidocr_onnxruntime import RapidOCR

LETTERS = "ABCDE"
MARKER = re.compile(r"^\\s*([A-E])\\s*([\\)）\\]:.]?)\\s*(.*)$")

def group_rows(boxes):
    items = []
    for box, text, _score in boxes:
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        items.append({"x": min(xs), "y": (min(ys) + max(ys)) / 2, "h": max(ys) - min(ys), "text": text})
    items.sort(key=lambda it: it["y"])
    rows, current = [], []
    for it in items:
        if current and abs(it["y"] - current[-1]["y"]) > 0.6 * max(it["h"], current[-1]["h"]):
            rows.append(current)
            current = []
        current.append(it)
    if current:
        rows.append(current)
    return [sorted(row, key=lambda it: it["x"]) for row in rows]

def is_marker(text, letter, strict):
    m = MARKER.match(text)
    if not m or m.group(1) != letter:
        return None
    paren, rest = m.group(2), m.group(3)
    if paren:
        return rest
    if strict:
        return None
    if rest == "" or re.match(r"^[-+−\\d]", rest):
        return rest
    return None

def parse_options_with_start(boxes):
    items = [it for row in group_rows(boxes) for it in row]
    starts = [i for i, it in enumerate(items) if is_marker(it["text"], "A", strict=True) is not None]
    for start in reversed(starts):
        options, current, i = {}, None, start
        expected = iter(LETTERS)
        letter = next(expected)
        while i < len(items):
            text = items[i]["text"]
            rest = is_marker(text, letter, strict=(letter == "A")) if letter else None
            if rest is not None:
                current = letter
                options[current] = rest
                letter = next(expected, None)
            elif current:
                options[current] = (options[current] + " " + text).strip()
            i += 1
        if len(options) == 5:
            cleaned = {k: v.lstrip(")）] ").strip() for k, v in options.items()}
            if all(cleaned.values()):
                return cleaned, start
            return {}, start
    return {}, len(items)

def extract(img_path):
    ocr = RapidOCR()
    with open(img_path, "rb") as f:
        boxes, _ = ocr(f.read())
    boxes = boxes or []
    rows = group_rows(boxes)
    items = [it for row in rows for it in row]
    options, start_idx = parse_options_with_start(boxes)
    item_to_row = {}
    flat = 0
    for r_i, row in enumerate(rows):
        for _ in row:
            item_to_row[flat] = r_i
            flat += 1
    st_rows = {}
    for idx in range(start_idx):
        st_rows.setdefault(item_to_row[idx], []).append(items[idx]["text"].strip())
    text = "\\n".join(" ".join(t for t in st_rows[r] if t) for r in sorted(st_rows)).strip()
    raw_full = "\\n".join(" ".join(it["text"].strip() for it in row if it["text"].strip()) for row in rows).strip()
    return {"text": text, "options": options, "raw_text": raw_full}

print(json.dumps(extract(sys.argv[1]), ensure_ascii=False))
`;

function detectLanguage(text) {
  const lower = ` ${String(text || "").toLowerCase()} `;
  if (/\b(què|quants|quantes|quin|quina|quins|quines|dels|pels|amb|això|és|són)\b/.test(lower)) return "cat";
  if (/\b(qué|cuántos|cuántas|cuál|cuáles|los|las|del|con|una|está|son)\b/.test(lower)) return "esp";
  if (/\b(quel|quelle|quels|quelles|combien|les|des|avec|dans|est|sont)\b/.test(lower)) return "fra";
  if (/\b(welche|welcher|welches|wie viele|der|die|das|und|mit|ist|sind)\b/.test(lower)) return "deu";
  return "eng";
}

function parseMetaFromFilename(filename, overrides = {}) {
  const stem = path.parse(filename || "uploaded.png").name;
  const m = stem.match(/^(lvl-(\d+)_(\d{4})_([^_]+))_([a-z]{2,3})$/i);
  const year = overrides.year
    ? Number(overrides.year)
    : (m ? Number(m[3]) : new Date().getFullYear());
  const level = overrides.level !== undefined && overrides.level !== ""
    ? Number(overrides.level)
    : (m ? Number(m[2]) : 0);
  const id = (overrides.id && String(overrides.id).trim())
    || (m ? m[1] : `lvl-${level}_${year}_${stem.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 20) || "custom"}`);
  const lang = (overrides.language && overrides.language !== "auto")
    ? String(overrides.language).toLowerCase()
    : (m ? m[5].toLowerCase() : "");
  return { id, language: lang, level, year };
}

async function runOcrOnUploadedImage(imgPath, originalFilename, overrides = {}) {
  ensureDir(TMP_WORK_DIR);
  const meta = parseMetaFromFilename(originalFilename, overrides);
  let extractedText = "";
  let options = {};
  let rawText = "";

  if (IMAGE_TO_JSON_SCRIPT) {
    const tmpOut = path.join(TMP_WORK_DIR, `ocr_${Date.now()}_${Math.random().toString(36).slice(2)}.jsonl`);
    const res = await spawnAsync(PYTHON_BIN, [
      IMAGE_TO_JSON_SCRIPT,
      "--image", imgPath,
      "--out", tmpOut,
      "--no-cache",
      "--default-language", meta.language || "eng",
    ]);
    try {
      if (res.code === 0 && fs.existsSync(tmpOut)) {
        const content = fs.readFileSync(tmpOut, "utf8").trim();
        if (content) {
          const parsed = JSON.parse(content.split(/\r?\n/)[0]);
          extractedText = parsed.text || "";
          options = parsed.options || {};
        }
      } else {
        throw new Error(res.stderr || res.stdout || "Error executant image_to_json.py");
      }
    } finally {
      try { fs.unlinkSync(tmpOut); } catch {}
    }
  } else {
    const res = await spawnAsync(PYTHON_BIN, ["-c", INLINE_OCR_SCRIPT, imgPath]);
    if (res.code !== 0) {
      throw new Error(`Error d'OCR (RapidOCR): ${res.stderr || res.stdout}`);
    }
    const parsed = JSON.parse(res.stdout.trim());
    extractedText = parsed.text || "";
    options = parsed.options || {};
    rawText = parsed.raw_text || "";
  }

  const resolvedLang = meta.language || detectLanguage(extractedText || rawText);
  const validLabel = /^[ABCDE]$/i.test(overrides.label || "") ? String(overrides.label).toUpperCase() : "";

  const problemJson = {
    id: meta.id,
    language: resolvedLang,
    level: Number.isFinite(meta.level) ? meta.level : 0,
    year: Number.isFinite(meta.year) ? meta.year : new Date().getFullYear(),
    text_only: Object.keys(options).length === 5,
    text: extractedText,
    options,
    label: validLabel,
  };

  if (!rawText) {
    const optStr = ["A", "B", "C", "D", "E"]
      .filter((k) => options[k])
      .map((k) => `${k}) ${options[k]}`)
      .join("   ");
    rawText = [extractedText, optStr].filter(Boolean).join("\n");
  }

  return { problem: problemJson, rawText };
}

// --- Raw text -> Structured M3Kang JSON ---

function structureRawTextDeterministic(rawText, overrides = {}) {
  const cleanedRaw = String(rawText || "").replace(/\r\n/g, "\n").trim();
  const letters = ["A", "B", "C", "D", "E"];

  // Find last sequence of markers A..E (supports "A) ...", "(A) ...", "A. ...", "A: ...", "A] ...")
  const markerRegex = /(?:^|[\s\n])[\(\[]?([A-E])[\)\]\.:]\s*/g;
  const matches = [];
  let m;
  while ((m = markerRegex.exec(cleanedRaw)) !== null) {
    matches.push({
      letter: m[1],
      matchStart: m.index,
      contentStart: m.index + m[0].length,
    });
  }

  let bestSequence = null;
  for (let i = matches.length - 1; i >= 0; i--) {
    if (matches[i].letter !== "A") continue;
    const seq = [matches[i]];
    let expectedIdx = 1;
    for (let j = i + 1; j < matches.length && expectedIdx < 5; j++) {
      if (matches[j].letter === letters[expectedIdx]) {
        seq.push(matches[j]);
        expectedIdx++;
      }
    }
    if (seq.length === 5) {
      bestSequence = seq;
      break;
    }
  }

  let statement = cleanedRaw;
  let options = {};

  if (bestSequence) {
    statement = cleanedRaw.slice(0, bestSequence[0].matchStart).trim();
    for (let k = 0; k < 5; k++) {
      const start = bestSequence[k].contentStart;
      const end = k < 4 ? bestSequence[k + 1].matchStart : cleanedRaw.length;
      const val = cleanedRaw.slice(start, end).replace(/\s+/g, " ").trim();
      options[letters[k]] = val;
    }
    if (!letters.every((l) => options[l])) {
      options = {};
    }
  }

  const numMatch = statement.match(/^(\d{1,2})\s*[\.\)]\s+/);
  const qNum = numMatch ? numMatch[1] : "1";
  const level = overrides.level !== undefined && overrides.level !== ""
    ? Number(overrides.level)
    : 0;
  const year = overrides.year !== undefined && overrides.year !== ""
    ? Number(overrides.year)
    : new Date().getFullYear();
  const language = (overrides.language && overrides.language !== "auto")
    ? String(overrides.language).toLowerCase()
    : detectLanguage(statement);
  const id = (overrides.id && String(overrides.id).trim())
    || `lvl-${level}_${year}_${qNum}`;
  const label = /^[ABCDE]$/i.test(overrides.label || "")
    ? String(overrides.label).toUpperCase()
    : "";

  return {
    id,
    language,
    level: Number.isFinite(level) ? level : 0,
    year: Number.isFinite(year) ? year : new Date().getFullYear(),
    text_only: Object.keys(options).length === 5,
    text: statement,
    options,
    label,
  };
}

const INLINE_AI_STRUCTURER = `
import json, os, socket, subprocess, sys, time, urllib.error, urllib.request

model_path = sys.argv[1]
port = int(sys.argv[2])
raw_text = sys.argv[3]
server_exe = sys.argv[4]
url = f"http://127.0.0.1:{port}"

def healthy():
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

proc = None
try:
    if not healthy():
        if not os.path.exists(server_exe) or not os.path.exists(model_path):
            sys.exit(2)
        proc = subprocess.Popen(
            [server_exe, "-m", model_path, "--host", "127.0.0.1", "--port", str(port),
             "--threads", "4", "--ctx-size", "2048", "--parallel", "1", "--cache-ram", "0",
             "--jinja", "--reasoning", "off", "--reasoning-budget", "0"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(120):
            if proc.poll() is not None:
                sys.exit(3)
            if healthy():
                break
            time.sleep(1)

    prompt = (
        "Extract the math problem statement and the five options A, B, C, D, E from the raw text below. "
        "Fix obvious OCR spacing issues without changing the language or numbers. "
        "Reply ONLY with valid JSON matching: "
        '{"text": "...", "options": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}.\n\n'
        "Raw text:\n" + raw_text
    )
    payload = json.dumps({
        "messages": [
            {"role": "system", "content": "You convert raw math exam text into clean JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
        "max_tokens": 512
    }).encode("utf-8")
    req = urllib.request.Request(url + "/v1/chat/completions", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith("\`\`\`"):
        content = content.strip("\`").lstrip("json").strip()
    print(content)
finally:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
`;

async function structureRawTextWithAi(rawText, overrides = {}) {
  const base = structureRawTextDeterministic(rawText, overrides);
  const selectedModel = resolveSelectedModel(overrides.model);
  const modelPath = path.join(MODELS_DIR, selectedModel);
  const serverExe = process.platform === "win32"
    ? path.join(PROJECT_DIR, "llama.cpp", "build", "bin", "Release", "llama-server.exe")
    : path.join(PROJECT_DIR, "llama.cpp", "build", "bin", "llama-server");

  const res = await spawnAsync(PYTHON_BIN, [
    "-c", INLINE_AI_STRUCTURER,
    modelPath,
    String(PREDICT_PORT),
    rawText,
    serverExe,
  ]);

  if (res.code === 0 && res.stdout.trim()) {
    try {
      const m = res.stdout.match(/\{[\s\S]*\}/);
      if (m) {
        const aiObj = JSON.parse(m[0]);
        if (typeof aiObj.text === "string" && aiObj.text.trim()) {
          base.text = aiObj.text.trim();
        }
        if (aiObj.options && typeof aiObj.options === "object") {
          const cleanOpts = {};
          for (const l of ["A", "B", "C", "D", "E"]) {
            if (aiObj.options[l] !== undefined && String(aiObj.options[l]).trim() !== "") {
              cleanOpts[l] = String(aiObj.options[l]).trim();
            }
          }
          if (Object.keys(cleanOpts).length === 5) {
            base.options = cleanOpts;
            base.text_only = true;
          }
        }
        return { problem: base, method: `ai (${selectedModel})` };
      }
    } catch {}
  }

  return { problem: base, method: "parser" };
}

// --- Run predict_one.py / run_predict.bat ---

async function runPredictOne({ inputFile = DATA_FILE, index = 1, model, variant, maxTokens, ctxSize }) {
  if (!fs.existsSync(PREDICT_SCRIPT)) {
    throw new Error(`No s'ha trobat predict_one.py a ${PREDICT_SCRIPT}`);
  }
  const resolvedInputFile = inputFile
    ? (path.isAbsolute(inputFile) ? inputFile : path.resolve(MACHINE_DIR, inputFile))
    : "";
  if (!resolvedInputFile || !fs.existsSync(resolvedInputFile)) {
    throw new Error(`No s'ha trobat el fitxer d'entrada ${resolvedInputFile || inputFile}`);
  }

  ensureDir(TMP_WORK_DIR);
  const selectedModel = resolveSelectedModel(model);

  // Relative path inside MACHINE_DIR avoids spaces in Windows paths when passed to run_predict.bat
  const relOutFile = path.join(
    ".tmp_web",
    `pred_${Date.now()}_${Math.random().toString(36).slice(2)}.jsonl`
  );
  const absOutFile = path.join(MACHINE_DIR, relOutFile);

  const serverAlreadyUp = await isPortOpen(PREDICT_PORT);
  const commonArgs = [
    "--input", inputFile,
    "--index", String(index),
    "--variant", variant,
    "--max-tokens", String(maxTokens),
    "--ctx-size", String(ctxSize),
    "--port", String(PREDICT_PORT),
    "--out", relOutFile,
  ];

  const useBat = process.platform === "win32" && fs.existsSync(RUN_PREDICT_BAT) && !serverAlreadyUp;

  const cmd = useBat ? "cmd.exe" : PYTHON_BIN;
  const args = useBat
    ? ["/c", RUN_PREDICT_BAT, selectedModel, ...commonArgs]
    : [PREDICT_SCRIPT, ...(serverAlreadyUp ? [] : ["--serve", selectedModel]), ...commonArgs];

  const displayCommand = useBat
    ? `run_predict.bat ${selectedModel} ${commonArgs.join(" ")}`
    : `${PYTHON_BIN} ${args.join(" ")}`;

  const startedAt = Date.now();
  const execResult = await spawnAsync(cmd, args, { cwd: MACHINE_DIR });
  const elapsedSeconds = Number(((Date.now() - startedAt) / 1000).toFixed(2));

  const cleanStdout = execResult.stdout
    .replace(/\r?\n.*(?:any key|cualquier tecla|qualsevol tecla).*\.{3}\s*$/i, "")
    .trim();
  const cleanStderr = execResult.stderr.trim();
  const rawOutput = [cleanStdout, cleanStderr ? `[stderr]\n${cleanStderr}` : ""]
    .filter(Boolean)
    .join("\n\n");

  let record = null;
  if (fs.existsSync(absOutFile)) {
    try {
      const content = fs.readFileSync(absOutFile, "utf8").trim();
      if (content) {
        const lines = content.split(/\r?\n/).filter(Boolean);
        record = JSON.parse(lines[lines.length - 1]);
      }
    } finally {
      try { fs.unlinkSync(absOutFile); } catch {}
    }
  }

  return {
    exitCode: execResult.code,
    record,
    rawOutput,
    command: displayCommand,
    elapsedSeconds,
    selectedModel,
  };
}

function buildPredictionResponse(result, problem, variant) {
  const rec = result.record;
  const answer = rec.lp ? argmaxLp(rec.lp) : rec.answer;
  const generatedText = [
    rec.thought,
    rec.expr ? `Expression: ${rec.expr}` : "",
    rec.value !== undefined && rec.value !== null ? `Value: ${rec.value}` : "",
    rec.match ? `Match: ${rec.match}` : "",
    !rec.thought && rec.content ? rec.content : "",
  ].filter(Boolean).join("\n");

  const seconds = typeof rec.laptop_s === "number"
    ? rec.laptop_s
    : (typeof rec.seconds === "number" ? rec.seconds : result.elapsedSeconds);

  const hasLabel = Boolean(problem.label && /^[ABCDE]$/.test(problem.label));

  return {
    answer,
    thought: generatedText,
    model: result.selectedModel.replace(/\.gguf$/i, ""),
    variant,
    status: rec.status || "ok",
    seconds,
    board_s: rec.board_s ?? null,
    laptop_s: rec.laptop_s ?? null,
    prompt_tokens: rec.read_tokens ?? rec.prompt_tokens ?? 0,
    written_tokens: rec.written_tokens ?? 0,
    lp: rec.lp ?? null,
    has_label: hasLabel,
    correct: hasLabel ? answer === problem.label : null,
    label: problem.label || "",
    prompt: formatPrompt(problem),
    command: result.command,
    examples: [],
  };
}

let problems = loadProblems();
let byKey = new Map(
  problems.map((problem, index) => [problemKey(problem), { problem, index }])
);

function reloadProblemsCache() {
  problems = loadProblems();
  byKey = new Map(
    problems.map((problem, index) => [problemKey(problem), { problem, index }])
  );
}

function publicProblem(problem) {
  const { label, ...shown } = problem;
  const key = problemKey(problem);
  return {
    ...shown,
    key,
    image: fs.existsSync(path.join(IMAGE_DIR, `${key}.png`)),
  };
}

function parseQuery(url) {
  return Object.fromEntries(new URL(url, "http://localhost").searchParams);
}

function parseDataUrlImage(dataUrl, fallbackName = "upload.png") {
  const m = String(dataUrl || "").match(/^data:image\/([a-zA-Z0-9+.-]+);base64,(.+)$/);
  if (!m) {
    throw new Error("Format d'imatge invàlid. Puja un fitxer PNG, JPG o WEBP.");
  }
  const extMap = { png: ".png", jpeg: ".jpg", jpg: ".jpg", webp: ".webp", bmp: ".bmp" };
  const ext = extMap[m[1].toLowerCase()] || path.extname(fallbackName) || ".png";
  const buffer = Buffer.from(m[2], "base64");
  return { buffer, ext };
}

function handleApi(request, response) {
  const url = new URL(request.url, "http://localhost");
  const params = parseQuery(request.url);

  if (request.method === "GET" && url.pathname === "/api/info") {
    const hasScript = fs.existsSync(PREDICT_SCRIPT);
    const models = listGgufModels();
    const defaultModel = models.includes(DEFAULT_MODEL_GGUF)
      ? DEFAULT_MODEL_GGUF
      : (models[0] || DEFAULT_MODEL_GGUF);

    return sendJson(response, 200, {
      count: problems.length,
      languages: [...new Set(problems.map((problem) => problem.language))].sort(),
      levels: [...new Set(problems.map((problem) => problem.level))].sort((a, b) => a - b),
      images: problems.filter((problem) => publicProblem(problem).image).length,
      index: 0,
      llm: hasScript,
      models,
      model: defaultModel,
      embed: false,
      vision: false,
      time_limit: 60,
    });
  }

  if (request.method === "GET" && url.pathname === "/api/problems") {
    return sendJson(response, 200, problems.map((problem) => ({
      key: problemKey(problem),
      id: problem.id,
      language: problem.language,
      level: problem.level,
      options: Boolean(problem.options),
    })));
  }

  if (request.method === "GET" && url.pathname === "/api/problem") {
    const entry = byKey.get(params.key);
    return entry
      ? sendJson(response, 200, publicProblem(entry.problem))
      : sendJson(response, 404, { error: "unknown problem" });
  }

  if (request.method === "GET" && url.pathname === "/api/similar") {
    return sendJson(response, 200, []);
  }

  if (request.method === "GET" && url.pathname.startsWith("/image/")) {
    const key = decodeURIComponent(url.pathname.slice("/image/".length));
    const file = path.resolve(IMAGE_DIR, `${key}.png`);
    if (byKey.has(key) && file.startsWith(`${IMAGE_DIR}${path.sep}`)) {
      return fs.readFile(file, (error, content) => {
        if (error) return sendJson(response, 404, { error: "image not found" });
        response.writeHead(200, { "Content-Type": "image/png" });
        response.end(content);
      });
    }
    return sendJson(response, 404, { error: "image not found" });
  }

  if (request.method === "POST" && url.pathname === "/api/check") {
    return readJson(request).then((body) => {
      const entry = byKey.get(body.key);
      if (!entry || !/^[ABCDE]$/.test(body.choice)) {
        return sendJson(response, 400, { error: "bad request" });
      }
      return sendJson(response, 200, {
        correct: body.choice === entry.problem.label,
        label: entry.problem.label,
      });
    }).catch((error) => sendJson(response, 400, { error: error.message }));
  }

  // Solver endpoint: solve an existing problem from VALIDATION_DATA
  if (request.method === "POST" && url.pathname === "/api/ask") {
    return readJson(request).then(async (body) => {
      const entry = byKey.get(body.key);
      if (!entry) return sendJson(response, 404, { error: "unknown problem" });

      if (activePrediction) {
        return sendJson(response, 429, {
          error: "Ja hi ha una predicció en execució. Espera que acabi.",
        });
      }

      const allowedVariants = new Set(["letter", "cot", "pot", "official"]);
      const variant = allowedVariants.has(body.variant) ? body.variant : "cot";
      const maxTokens = Number.isFinite(Number(body.max_tokens)) && Number(body.max_tokens) > 0
        ? Math.floor(Number(body.max_tokens))
        : 120;
      const ctxSize = Number.isFinite(Number(body.ctx_size)) && Number(body.ctx_size) >= 0
        ? Math.floor(Number(body.ctx_size))
        : 4096;

      const { problem, index } = entry;
      const oneBasedIndex = index + 1;

      activePrediction = true;
      try {
        const result = await runPredictOne({
          inputFile: DATA_FILE,
          index: oneBasedIndex,
          model: body.model,
          variant,
          maxTokens,
          ctxSize,
        });

        if (result.exitCode !== 0 || !result.record) {
          return sendJson(response, 500, {
            error: `predict_one.py ha acabat amb codi ${result.exitCode}`,
            raw_output: result.rawOutput,
            command: result.command,
          });
        }

        return sendJson(response, 200, buildPredictionResponse(result, problem, variant));
      } finally {
        activePrediction = false;
      }
    }).catch((error) => sendJson(response, 500, { error: error.message }));
  }

  // Uploader endpoint 1: OCR only on uploaded image -> structured JSON
  if (request.method === "POST" && url.pathname === "/api/upload-ocr") {
    return readJson(request).then(async (body) => {
      const { buffer, ext } = parseDataUrlImage(body.image_base64, body.filename);
      ensureDir(TMP_WORK_DIR);
      const tmpImg = path.join(TMP_WORK_DIR, `img_${Date.now()}_${Math.random().toString(36).slice(2)}${ext}`);
      fs.writeFileSync(tmpImg, buffer);
      try {
        const ocrRes = await runOcrOnUploadedImage(tmpImg, body.filename, {
          id: body.id,
          language: body.language,
          level: body.level,
          year: body.year,
          label: body.label,
        });
        return sendJson(response, 200, ocrRes);
      } finally {
        try { fs.unlinkSync(tmpImg); } catch {}
      }
    }).catch((error) => sendJson(response, 400, { error: error.message }));
  }

  // Uploader endpoint 2: Upload image -> OCR + full AI resolution
  if (request.method === "POST" && url.pathname === "/api/upload-solve") {
    return readJson(request).then(async (body) => {
      if (activePrediction) {
        return sendJson(response, 429, {
          error: "Ja hi ha una predicció en execució. Espera que acabi.",
        });
      }

      const { buffer, ext } = parseDataUrlImage(body.image_base64, body.filename);
      ensureDir(TMP_WORK_DIR);
      const stamp = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
      const tmpImg = path.join(TMP_WORK_DIR, `img_${stamp}${ext}`);
      const relInputJsonl = path.join(".tmp_web", `in_${stamp}.jsonl`);
      const absInputJsonl = path.join(MACHINE_DIR, relInputJsonl);

      fs.writeFileSync(tmpImg, buffer);

      const allowedVariants = new Set(["letter", "cot", "pot", "official"]);
      const variant = allowedVariants.has(body.variant) ? body.variant : "cot";
      const maxTokens = Number.isFinite(Number(body.max_tokens)) && Number(body.max_tokens) > 0
        ? Math.floor(Number(body.max_tokens))
        : 150;
      const ctxSize = Number.isFinite(Number(body.ctx_size)) && Number(body.ctx_size) >= 0
        ? Math.floor(Number(body.ctx_size))
        : 4096;

      activePrediction = true;
      try {
        const ocrRes = await runOcrOnUploadedImage(tmpImg, body.filename, {
          id: body.id,
          language: body.language,
          level: body.level,
          year: body.year,
          label: body.label,
        });

        fs.writeFileSync(absInputJsonl, JSON.stringify(ocrRes.problem) + "\n", "utf8");

        const result = await runPredictOne({
          inputFile: relInputJsonl,
          index: 1,
          model: body.model,
          variant,
          maxTokens,
          ctxSize,
        });

        if (result.exitCode !== 0 || !result.record) {
          return sendJson(response, 500, {
            error: `predict_one.py ha acabat amb codi ${result.exitCode}`,
            problem: ocrRes.problem,
            raw_text: ocrRes.rawText,
            command: result.command,
          });
        }

        return sendJson(response, 200, {
          problem: ocrRes.problem,
          raw_text: ocrRes.rawText,
          prediction: buildPredictionResponse(result, ocrRes.problem, variant),
        });
      } finally {
        activePrediction = false;
        try { fs.unlinkSync(tmpImg); } catch {}
        try { fs.unlinkSync(absInputJsonl); } catch {}
      }
    }).catch((error) => sendJson(response, 500, { error: error.message }));
  }

  // Uploader endpoint 3: Structure raw text into M3Kang JSON
  if (request.method === "POST" && url.pathname === "/api/structure-text") {
    return readJson(request).then(async (body) => {
      if (!body.raw_text || !String(body.raw_text).trim()) {
        return sendJson(response, 400, { error: "Enganxa primer el text en brut." });
      }
      if (body.use_ai) {
        if (activePrediction) {
          return sendJson(response, 429, { error: "Espera que acabi l'execució actual." });
        }
        activePrediction = true;
        try {
          const out = await structureRawTextWithAi(body.raw_text, body);
          return sendJson(response, 200, out);
        } finally {
          activePrediction = false;
        }
      }
      const problem = structureRawTextDeterministic(body.raw_text, body);
      return sendJson(response, 200, { problem, method: "parser" });
    }).catch((error) => sendJson(response, 500, { error: error.message }));
  }

  // Uploader endpoint 4: Solve an arbitrary structured JSON problem with the AI
  if (request.method === "POST" && url.pathname === "/api/solve-json") {
    return readJson(request).then(async (body) => {
      if (activePrediction) {
        return sendJson(response, 429, {
          error: "Ja hi ha una predicció en execució. Espera que acabi.",
        });
      }
      const problem = body.problem;
      if (!problem || typeof problem !== "object" || !String(problem.text || "").trim()) {
        return sendJson(response, 400, { error: "El JSON ha de contenir com a mínim el camp 'text'." });
      }

      const normalized = {
        id: String(problem.id || `lvl-0_${new Date().getFullYear()}_custom`),
        language: String(problem.language || detectLanguage(problem.text)),
        level: Number.isFinite(Number(problem.level)) ? Number(problem.level) : 0,
        year: Number.isFinite(Number(problem.year)) ? Number(problem.year) : new Date().getFullYear(),
        text_only: Boolean(problem.options && Object.keys(problem.options).length === 5),
        text: String(problem.text).trim(),
        options: problem.options && typeof problem.options === "object" ? problem.options : {},
        label: /^[ABCDE]$/i.test(problem.label || "") ? String(problem.label).toUpperCase() : "",
      };

      ensureDir(TMP_WORK_DIR);
      const relInputJsonl = path.join(
        ".tmp_web",
        `json_${Date.now()}_${Math.random().toString(36).slice(2)}.jsonl`
      );
      const absInputJsonl = path.join(MACHINE_DIR, relInputJsonl);
      fs.writeFileSync(absInputJsonl, JSON.stringify(normalized) + "\n", "utf8");

      const allowedVariants = new Set(["letter", "cot", "pot", "official"]);
      const variant = allowedVariants.has(body.variant) ? body.variant : "cot";
      const maxTokens = Number.isFinite(Number(body.max_tokens)) && Number(body.max_tokens) > 0
        ? Math.floor(Number(body.max_tokens))
        : 150;
      const ctxSize = Number.isFinite(Number(body.ctx_size)) && Number(body.ctx_size) >= 0
        ? Math.floor(Number(body.ctx_size))
        : 4096;

      activePrediction = true;
      try {
        const result = await runPredictOne({
          inputFile: relInputJsonl,
          index: 1,
          model: body.model,
          variant,
          maxTokens,
          ctxSize,
        });

        if (result.exitCode !== 0 || !result.record) {
          return sendJson(response, 500, {
            error: `predict_one.py ha acabat amb codi ${result.exitCode}`,
            command: result.command,
          });
        }

        return sendJson(response, 200, {
          problem: normalized,
          prediction: buildPredictionResponse(result, normalized, variant),
        });
      } finally {
        activePrediction = false;
        try { fs.unlinkSync(absInputJsonl); } catch {}
      }
    }).catch((error) => sendJson(response, 500, { error: error.message }));
  }

  // Optional: Save structured problem (and image if present) into DATA_FILE (val.jsonl)
  if (request.method === "POST" && url.pathname === "/api/save-problem") {
    return readJson(request).then((body) => {
      const problem = body.problem;
      if (!problem || !problem.id || !problem.text) {
        return sendJson(response, 400, { error: "JSON incomplet (cal 'id' i 'text')." });
      }
      const record = {
        id: String(problem.id),
        language: String(problem.language || "eng"),
        level: Number(problem.level || 0),
        year: Number(problem.year || new Date().getFullYear()),
        text_only: Boolean(problem.options && Object.keys(problem.options).length === 5),
        text: String(problem.text).trim(),
        options: problem.options || {},
        label: /^[ABCDE]$/i.test(problem.label || "") ? String(problem.label).toUpperCase() : "",
      };

      ensureDir(path.dirname(DATA_FILE));
      fs.appendFileSync(DATA_FILE, JSON.stringify(record) + "\n", "utf8");

      if (body.image_base64) {
        try {
          const { buffer } = parseDataUrlImage(body.image_base64);
          ensureDir(IMAGE_DIR);
          fs.writeFileSync(path.join(IMAGE_DIR, `${record.id}_${record.language}.png`), buffer);
        } catch {}
      }

      reloadProblemsCache();
      return sendJson(response, 200, {
        saved: true,
        key: problemKey(record),
        total: problems.length,
      });
    }).catch((error) => sendJson(response, 500, { error: error.message }));
  }

  return false;
}

function readJson(request, maxBytes = 15 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let data = "";
    let size = 0;
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      size += Buffer.byteLength(chunk, "utf8");
      if (size > maxBytes) {
        reject(new Error("El fitxer supera el límit de 15 MB."));
        request.destroy();
        return;
      }
      data += chunk;
    });
    request.on("end", () => {
      try { resolve(JSON.parse(data || "{}")); } catch { reject(new Error("Invalid JSON")); }
    });
    request.on("error", reject);
  });
}

function serveStatic(request, response) {
  const routePages = {
    "/": "/index.html",
    "/analytics": "/analytics.html",
    "/analytics.html": "/analytics.html",
    "/solver": "/solver.html",
    "/solver.html": "/solver.html",
    "/solver.py": "/solver.html",
    "/uploader": "/uploader.html",
    "/uploader.html": "/uploader.html",
    "/uploader.py": "/uploader.html",
  };
  const cleanUrl = request.url.split("?")[0];
  const requestedPath = routePages[cleanUrl] || cleanUrl;
  const filePath = path.resolve(PUBLIC_DIR, `.${requestedPath}`);
  if (!filePath.startsWith(`${PUBLIC_DIR}${path.sep}`)) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }

  fs.readFile(filePath, (error, content) => {
    if (error) {
      sendJson(response, 404, { error: "Not found" });
      return;
    }
    response.writeHead(200, {
      "Content-Type": MIME_TYPES[path.extname(filePath)] || "application/octet-stream",
    });
    response.end(content);
  });
}

const server = http.createServer((request, response) => {
  if (request.url.startsWith("/api/") || request.url.startsWith("/image/")) {
    const handled = handleApi(request, response);
    if (handled !== false) return;
  }
  if (request.method === "GET") {
    serveStatic(request, response);
    return;
  }
  sendJson(response, 405, { error: "Method not allowed" });
});

server.listen(PORT, () => {
  const models = listGgufModels();
  console.log(`Kangaroo web app: http://127.0.0.1:${PORT}`);
  console.log(`Using Python: ${PYTHON_BIN}`);
  console.log(`Loaded ${problems.length} problems from ${DATA_FILE}`);
  console.log(`Found ${models.length} GGUF model(s) in ${MODELS_DIR}: ${models.join(", ") || "(none)"}`);
});