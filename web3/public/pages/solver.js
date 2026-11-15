/* Solver page: web2's Agent page with web1's model controls and result view.
   Exported as a mount() function so the router can inject the fragment and
   run it without reloading the shell. */
import { api, esc, renderRichText } from "/pages/rich.js";

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);

  let all = [];
  let shown = [];
  let current = null;
  let myChoice = null;
  let info = null;
  let alive = true;
  let openToken = 0;
  const results = {};

  function score() {
    const values = Object.values(results);
    const me = values.filter((r) => "me" in r);
    const model = values.filter((r) => "model" in r);
    $("score").textContent =
      `You ${me.filter((r) => r.me).length}/${me.length} · ` +
      `Model ${model.filter((r) => r.model).length}/${model.length}`;
  }

  function renderList() {
    const lang = $("f-lang").value;
    const level = $("f-level").value;
    const opts = $("f-options").checked;
    shown = all.filter((p) =>
      (!lang || p.language === lang) &&
      (level === "" || String(p.level) === level) &&
      (!opts || p.options));
    $("list").innerHTML = shown.map((p) => {
      const r = results[p.key] || {};
      const mark = ("me" in r ? (r.me ? "✓" : "✗") : "") +
        ("model" in r ? (r.model ? " ✓" : " ✗") : "");
      return `<div data-key="${esc(p.key)}" class="${current && p.key === current.key ? "on" : ""}">` +
        `<span>L${p.level} · ${esc(p.id)} · ${esc(p.language)}</span>` +
        `<span class="mark">${mark}</span></div>`;
    }).join("");
  }

  async function openProblem(key) {
    const token = ++openToken;
    try {
      const data = await api("/api/problem?key=" + encodeURIComponent(key));
      if (!alive || token !== openToken) return;

      current = data;
      myChoice = null;
      $("meta").textContent = `${current.id} · ${current.language} · level ${current.level}`;
      $("img").style.display = current.image ? "" : "none";
      if (current.image) $("img").src = "/image/" + encodeURIComponent(current.key);
      $("text").innerHTML = renderRichText(current.text);

      const options = current.options || {};
      $("ocr").innerHTML = Object.keys(options).length
        ? "Options: " + "ABCDE".split("").map((l) => `<b>${l})</b> ${renderRichText(options[l], true)}`).join(" &nbsp; ")
        : "No options available: they are in the picture.";

      $("mine").innerHTML = "ABCDE".split("").map((l) => `<button data-l="${l}">${l}</button>`).join("");
      $("my-verdict").textContent = "";
      $("my-verdict").className = "verdict";
      $("model-hint").textContent = "";
      $("model").innerHTML = "";
      renderList();
    } catch (error) {
      if (alive && token === openToken) $("text").textContent = error.message;
    }
  }

  async function answer(letter) {
    if (!current || myChoice) return;
    myChoice = letter;
    try {
      const r = await api("/api/check", { key: current.key, choice: letter });
      if (!alive) return;
      (results[current.key] ||= {}).me = r.correct;
      root.querySelectorAll("#mine button").forEach((button) => {
        button.disabled = true;
        if (button.dataset.l === r.label) button.classList.add("right");
        else if (button.dataset.l === letter) button.classList.add("wrong");
      });
      $("my-verdict").textContent = r.correct ? "Correct!" : `Not this time: the answer is ${r.label}.`;
      $("my-verdict").className = "verdict " + (r.correct ? "ok" : "bad");
      score();
      renderList();
    } catch (error) {
      myChoice = null;
      if (alive) $("my-verdict").textContent = error.message;
    }
  }

  async function ask() {
    if (!current || $("ask").disabled) return;
    $("ask").disabled = true;
    const asked = current.key;
    const started = Date.now();
    const timer = setInterval(() => {
      if (alive) $("model-hint").textContent = `Running on the board... ${((Date.now() - started) / 1000).toFixed(1)} s`;
    }, 250);

    try {
      const r = await api("/api/ask", {
        key: asked,
        model: $("f-model").value,
        variant: $("f-variant").value,
        max_tokens: Number($("f-max-tokens").value) || 120,
      });
      if (!alive) return;
      (results[asked] ||= {}).model = r.correct;
      score();
      renderList();
      if (!current || current.key !== asked) return;  // the reader moved on while the board was thinking

      root.querySelectorAll("#mine button").forEach((button) => {
        button.classList.toggle("model", button.dataset.l === r.answer);
      });
      $("model-hint").textContent = "";

      const thought = r.thought
        ? `<div class="thought-box"><div class="thought-title">Generated text</div>` +
          `<div class="thought-body rich-text">${renderRichText(r.thought)}</div></div>`
        : "";
      const rows = [
        ["Model", esc(r.model)],
        ["Variant", esc(r.variant)],
        ["Status", esc(r.status)],
        ["Time", `${r.seconds} s`],
        ["Tokens", `${r.prompt_tokens} read · ${r.written_tokens ?? 0} written`],
      ].map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
      const command = r.command
        ? `<details><summary>Command</summary><pre>${esc(r.command)}</pre></details>`
        : "";

      $("model").innerHTML =
        `<div class="verdict ${r.correct ? "ok" : "bad"}">The model says ${esc(r.answer)}: ` +
        `${r.correct ? "correct" : "wrong, the answer is " + esc(r.label)}.</div>` +
        thought + `<table>${rows}</table>` + command +
        `<details><summary>Prompt</summary><pre>${esc(r.prompt)}</pre></details>`;
    } catch (error) {
      if (!alive) return;
      $("model-hint").textContent = "Execution failed";
      const output = error.data && error.data.raw_output
        ? `<details><summary>Output</summary><pre>${esc(error.data.raw_output)}</pre></details>`
        : "";
      $("model").innerHTML = `<div class="verdict bad">${esc(error.message)}</div>${output}`;
    } finally {
      clearInterval(timer);
      if (alive) $("ask").disabled = false;
    }
  }

  function next(random) {
    if (!shown.length) return;
    const index = shown.findIndex((p) => current && p.key === current.key);
    const target = random
      ? Math.floor(Math.random() * shown.length)
      : (index + 1) % shown.length;
    openProblem(shown[target].key);
  }

  $("list").addEventListener("click", (event) => {
    const row = event.target.closest("[data-key]");
    if (row) openProblem(row.dataset.key);
  });

  $("mine").addEventListener("click", (event) => {
    if (event.target.dataset.l) answer(event.target.dataset.l);
  });

  ["f-lang", "f-level", "f-options"].forEach((id) => {
    $(id).addEventListener("change", renderList);
  });

  $("ask").addEventListener("click", ask);
  $("next").addEventListener("click", () => next(false));
  $("random").addEventListener("click", () => next(true));

  function onKeydown(event) {
    if (["SELECT", "INPUT", "TEXTAREA"].includes(event.target.tagName) ||
        event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toUpperCase();
    if (key.length !== 1) return;
    if ("ABCDE".includes(key)) answer(key);
    else if (key === "M") ask();
    else if (key === "N") next(false);
    else if (key === "R") next(true);
  }
  document.addEventListener("keydown", onKeydown);

  (async function init() {
    try {
      info = await api("/api/info");
      if (!alive) return;
      const models = info.models && info.models.length ? info.models : [info.model || "model"];
      $("f-model").innerHTML = models
        .map((m) => `<option value="${esc(m)}"${m === info.model ? " selected" : ""}>${esc(m.replace(/\.gguf$/i, ""))}</option>`)
        .join("");
      $("s-mode").textContent = info.llm ? `${(info.model || "model").replace(/\.gguf$/i, "")} · on the board` : "the model is not running";
      $("s-data").textContent = `${info.count} problems · ${info.images} images`;
      info.languages.forEach((language) =>
        $("f-lang").insertAdjacentHTML("beforeend", `<option>${esc(language)}</option>`));
      info.levels.forEach((level) =>
        $("f-level").insertAdjacentHTML("beforeend", `<option>${level}</option>`));

      all = await api("/api/problems");
      if (!alive) return;
      renderList();
      if (shown.length) openProblem(shown[0].key);
      else $("meta").textContent = "No problems found in data/.";
    } catch (error) {
      if (alive) $("text").textContent = error.message;
    }
  })();

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKeydown);
  };
}
