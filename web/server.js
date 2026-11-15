const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const VALIDATION_DATA = "val.jsonl";
const TRAIN_DATA = "val.jsonl";
const TEST_DATA = "";
const SAMPLE_PROBLEMS = "sample_problems.jsonl";

const PORT = Number(process.env.PORT || 3000);
const PUBLIC_DIR = path.join(__dirname, "public");
const PROJECT_DIR = path.resolve(__dirname, "..");
const DATA_FILE = process.env.M3KANG_INPUT
  ? path.resolve(process.env.M3KANG_INPUT)
  : [
      path.join(PROJECT_DIR, "data", VALIDATION_DATA),
      path.join(PROJECT_DIR, "data", TRAIN_DATA),
      path.join(PROJECT_DIR, "data", SAMPLE_PROBLEMS),
    ].find((file) => fs.existsSync(file));
const IMAGE_DIR = process.env.M3KANG_IMAGES
  ? path.resolve(process.env.M3KANG_IMAGES)
  : path.join(PROJECT_DIR, "data", "images");

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

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

function loadProblems() {
  try {
    return fs.readFileSync(DATA_FILE, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch (error) {
    console.error(`Could not load ${DATA_FILE}: ${error.message}`);
    return [];
  }
}

const problems = loadProblems();
const byKey = new Map(problems.map((problem) => [problemKey(problem), problem]));

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

function handleApi(request, response) {
  const url = new URL(request.url, "http://localhost");
  const params = parseQuery(request.url);

  if (request.method === "GET" && url.pathname === "/api/info") {
    return sendJson(response, 200, {
      count: problems.length,
      languages: [...new Set(problems.map((problem) => problem.language))].sort(),
      levels: [...new Set(problems.map((problem) => problem.level))].sort((a, b) => a - b),
      images: problems.filter((problem) => publicProblem(problem).image).length,
      index: 0,
      llm: false,
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
    const problem = byKey.get(params.key);
    return problem
      ? sendJson(response, 200, publicProblem(problem))
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
      const problem = byKey.get(body.key);
      if (!problem || !/^[ABCDE]$/.test(body.choice)) {
        return sendJson(response, 400, { error: "bad request" });
      }
      return sendJson(response, 200, {
        correct: body.choice === problem.label,
        label: problem.label,
      });
    }).catch((error) => sendJson(response, 400, { error: error.message }));
  }
  if (request.method === "POST" && url.pathname === "/api/ask") {
    return readJson(request).then((body) => {
      const problem = byKey.get(body.key);
      if (!problem) return sendJson(response, 404, { error: "unknown problem" });
      const answer = "D";
      return sendJson(response, 200, {
        answer,
        status: "local fallback",
        seconds: 0,
        prompt_tokens: 0,
        correct: answer === problem.label,
        label: problem.label,
        prompt: `${problem.text}\n\nLocal mode: no language model configured.`,
        examples: [],
      });
    }).catch((error) => sendJson(response, 400, { error: error.message }));
  }
  return false;
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    let data = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { data += chunk; });
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
    "/uploader": "/uploader.html",
  };
  const requestedPath = routePages[request.url] || request.url;
  const filePath = path.resolve(PUBLIC_DIR, `.${requestedPath.split("?")[0]}`);
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
  console.log(`Kangaroo web app: http://127.0.0.1:${PORT}`);
  console.log(`Loaded ${problems.length} problems from ${DATA_FILE}`);
});
