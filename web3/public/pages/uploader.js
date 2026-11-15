/* Uploader page: web1's uploader as a mount() for the router. A picture or
   pasted text becomes a problem in the M3Kang format, and the board's model
   answers it. */
import { api, esc, renderRichText } from "/pages/rich.js";

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  let picture = "";       // the uploaded picture, as a data URL
  let pictureName = "";
  let info = null;
  let alive = true;

  const say = (id, text) => { if (alive) $(id).textContent = text; };

  /* A status line that counts the seconds while the board works. Returns stop(). */
  function clock(id, label) {
    const started = Date.now();
    const timer = setInterval(() => say(id, `${label} ${((Date.now() - started) / 1000).toFixed(1)} s`), 250);
    return () => clearInterval(timer);
  }

  function modelSettings() {
    return {
      model: $("f-model").value,
      variant: $("f-variant").value,
      max_tokens: Number($("f-max-tokens").value) || 150,
    };
  }

  function chosenMeta() {
    return { id: $("m-id").value.trim(), level: $("m-level").value, label: $("m-label").value };
  }

  function selectedFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (!alive) return;
      picture = reader.result;
      pictureName = file.name || "pasted_image.png";
      $("preview-img").src = picture;
      $("preview-wrap").hidden = false;
      $("preview-meta").textContent = `${pictureName} (${Math.round(file.size / 1024)} KB)`;
      $("btn-solve-img").disabled = false;
      $("btn-ocr-only").disabled = false;
      $("img-status").textContent = info && !info.ocr
        ? "This device can't read pictures (no OCR). Paste the text in step 2."
        : "The picture is ready.";
    };
    reader.readAsDataURL(file);
  }

  function fillEditor(problem, rawText) {
    $("json-out").value = JSON.stringify(problem, null, 2);
    if (rawText && !$("raw-text").value.trim()) $("raw-text").value = rawText;
    if (problem.id) $("m-id").value = problem.id;
    if (problem.language && [...$("m-lang").options].some((o) => o.value === problem.language)) $("m-lang").value = problem.language;
    if (problem.level !== undefined) $("m-level").value = problem.level;
    if (problem.label) $("m-label").value = problem.label;
  }

  function showAnswer(r, problem) {
    $("resolution-card").hidden = false;
    const letters = "ABCDE".split("").map((l) => {
      let cls = "letter-badge";
      if (r.has_label && l === r.label) cls += " right";
      else if (r.has_label && l === r.answer && !r.correct) cls += " wrong";
      else if (l === r.answer) cls += " pred";
      return `<span class="${cls}">${l}</span>`;
    }).join("");
    const value = problem && problem.options && problem.options[r.answer] ? ` (${esc(problem.options[r.answer])})` : "";
    const verdict = r.has_label
      ? `<div class="verdict ${r.correct ? "ok" : "bad"}">The model says ${esc(r.answer)}${value}: ${r.correct ? "correct" : "wrong, the answer is " + esc(r.label)}.</div>`
      : `<div class="verdict neutral">The model says ${esc(r.answer)}${value}</div>`;
    const thought = r.thought
      ? `<div class="thought-box"><div class="thought-title">Generated text</div><div class="thought-body rich-text">${renderRichText(r.thought)}</div></div>`
      : "";
    const rows = [
      ["Model", esc(r.model)],
      ["Variant", esc(r.variant)],
      ["Status", esc(r.status)],
      ["Time", `${r.seconds} s`],
      ["Tokens", `${r.prompt_tokens} read · ${r.written_tokens ?? 0} written`],
    ].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
    const logprobs = r.lp
      ? `<details><summary>Log-probabilities (A–E)</summary><pre>${esc("ABCDE".split("").map((l) => `${l}: ${r.lp[l]}`).join("\n"))}</pre></details>`
      : "";
    const prompt = r.prompt ? `<details><summary>Prompt</summary><pre>${esc(r.prompt)}</pre></details>` : "";
    $("resolution-body").innerHTML = verdict + `<div class="letters-bar">${letters}</div>` + thought +
      `<table>${rows}</table>` + logprobs + prompt;
    $("resolution-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function solvePicture() {
    if (!picture) return;
    $("btn-solve-img").disabled = true; $("btn-ocr-only").disabled = true;
    const stop = clock("img-status", "Reading the picture and asking the model...");
    try {
      const r = await api("/api/upload-solve", {
        image_base64: picture, filename: pictureName, language: $("f-lang").value, ...modelSettings(), ...chosenMeta(),
      });
      stop();
      if (!alive) return;
      fillEditor(r.problem, r.raw_text);
      showAnswer(r.prediction, r.problem);
      say("img-status", "Done.");
    } catch (error) {
      stop();
      say("img-status", `Error: ${error.message}`);
      if (alive && error.data && error.data.problem) fillEditor(error.data.problem, error.data.raw_text);
    } finally {
      if (alive) { $("btn-solve-img").disabled = false; $("btn-ocr-only").disabled = false; }
    }
  }

  async function readPicture() {
    if (!picture) return;
    $("btn-solve-img").disabled = true; $("btn-ocr-only").disabled = true;
    const stop = clock("img-status", "Reading the picture...");
    try {
      const r = await api("/api/upload-ocr", {
        image_base64: picture, filename: pictureName, language: $("f-lang").value, ...chosenMeta(),
      });
      stop();
      if (!alive) return;
      fillEditor(r.problem, r.rawText);
      say("img-status", `Read: ${Object.keys(r.problem.options || {}).length} of 5 options.`);
    } catch (error) {
      stop();
      say("img-status", `Error: ${error.message}`);
    } finally {
      if (alive) { $("btn-solve-img").disabled = false; $("btn-ocr-only").disabled = false; }
    }
  }

  async function structureText(withModel) {
    const raw = $("raw-text").value;
    if (!raw.trim()) { say("struct-status", "Paste the text first."); $("raw-text").focus(); return; }
    $("btn-struct-fast").disabled = true; $("btn-struct-ai").disabled = true;
    const stop = withModel ? clock("struct-status", "The model is cleaning the text...") : () => {};
    try {
      const r = await api("/api/structure-text", {
        raw_text: raw, use_ai: withModel, model: $("f-model").value, language: $("m-lang").value, ...chosenMeta(),
      });
      stop();
      if (!alive) return;
      fillEditor(r.problem, "");
      say("struct-status", `Structured by the ${r.method}: ${Object.keys(r.problem.options || {}).length} of 5 options.`);
    } catch (error) {
      stop();
      say("struct-status", `Error: ${error.message}`);
    } finally {
      if (alive) { $("btn-struct-fast").disabled = false; $("btn-struct-ai").disabled = false; }
    }
  }

  function editorProblem() {
    try { return JSON.parse($("json-out").value); }
    catch (error) { say("json-status", `The JSON isn't valid: ${error.message}`); return null; }
  }

  async function solveJson() {
    const problem = editorProblem();
    if (!problem) return;
    $("btn-solve-json").disabled = true;
    const stop = clock("json-status", "Asking the model...");
    try {
      const r = await api("/api/solve-json", { problem, ...modelSettings() });
      stop();
      if (!alive) return;
      fillEditor(r.problem, "");
      showAnswer(r.prediction, r.problem);
      say("json-status", "Solved.");
    } catch (error) {
      stop();
      say("json-status", `Error: ${error.message}`);
    } finally {
      if (alive) $("btn-solve-json").disabled = false;
    }
  }

  async function copy(text, done) {
    try { await navigator.clipboard.writeText(text); say("json-status", done); }
    catch { say("json-status", "The browser didn't allow copying. Select the text and copy it."); }
  }

  $("dropzone").addEventListener("click", () => $("file-input").click());
  $("dropzone").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file-input").click(); }
  });
  $("file-input").addEventListener("change", (e) => selectedFile(e.target.files[0]));
  $("dropzone").addEventListener("dragover", (e) => { e.preventDefault(); $("dropzone").classList.add("drag"); });
  $("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("drag"));
  $("dropzone").addEventListener("drop", (e) => {
    e.preventDefault();
    $("dropzone").classList.remove("drag");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) selectedFile(e.dataTransfer.files[0]);
  });

  function onPaste(e) {
    for (const item of (e.clipboardData || {}).items || []) {
      if (item.type.startsWith("image/")) { selectedFile(item.getAsFile()); break; }
    }
  }
  document.addEventListener("paste", onPaste);

  $("btn-solve-img").addEventListener("click", solvePicture);
  $("btn-ocr-only").addEventListener("click", readPicture);
  $("btn-struct-fast").addEventListener("click", () => structureText(false));
  $("btn-struct-ai").addEventListener("click", () => structureText(true));
  $("btn-solve-json").addEventListener("click", solveJson);
  $("btn-copy-json").addEventListener("click", () => copy($("json-out").value, "Copied the JSON."));
  $("btn-copy-jsonl").addEventListener("click", () => {
    const problem = editorProblem();
    if (problem) copy(JSON.stringify(problem), "Copied one line of JSONL.");
  });
  $("btn-download-json").addEventListener("click", () => {
    const problem = editorProblem();
    if (!problem) return;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(problem, null, 2) + "\n"], { type: "application/json" }));
    link.download = `${problem.id || "problem"}_${problem.language || "eng"}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  });
  $("btn-save").addEventListener("click", async () => {
    const problem = editorProblem();
    if (!problem) return;
    try {
      const r = await api("/api/save-problem", { problem, image_base64: picture || "" });
      say("json-status", `Saved as ${r.key}. The Agent now lists ${r.total} problems.`);
    } catch (error) { say("json-status", `Not saved: ${error.message}`); }
  });

  (async function init() {
    try {
      info = await api("/api/info");
      if (!alive) return;
      const models = info.models && info.models.length ? info.models : [info.model || "model"];
      $("f-model").innerHTML = models
        .map((m) => `<option value="${esc(m)}">${esc(m.replace(/\.gguf$/i, ""))}</option>`).join("");
      $("s-model").textContent = info.llm ? `${info.model.replace(/\.gguf$/i, "")} · on the board` : "the model is not running";
      $("s-data").textContent = `${info.count} problems in the Agent`;
      $("s-ocr").textContent = info.ocr ? "OCR ready" : "no OCR on this device: paste the text";
      $("s-ocr").classList.toggle("warn", !info.ocr);
    } catch (error) { say("img-status", error.message); }
  })();

  return () => {
    alive = false;
    document.removeEventListener("paste", onPaste);
  };
}
