/* Agent page logic. Exported as a mount() function so the router can inject
   the fragment and run it without reloading the shell. */
export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const esc = (value) => String(value).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const api = async (url, body) => {
    const response = await fetch(url, body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  };

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
      $("text").textContent = current.text;

      const options = current.options || {};
      $("ocr").innerHTML = Object.keys(options).length
        ? "Options: " + "ABCDE".split("").map((l) => `<b>${l})</b> ${esc(options[l])}`).join(" &nbsp; ")
        : "No options available.";

      $("mine").innerHTML = "ABCDE".split("").map((l) => `<button data-l="${l}">${l}</button>`).join("");
      $("my-verdict").textContent = "";
      $("my-verdict").className = "verdict";
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
    if (!current) return;
    $("ask").disabled = true;
    try {
      const r = await api("/api/ask", { key: current.key });
      if (!alive) return;
      (results[current.key] ||= {}).model = r.correct;
      root.querySelectorAll("#mine button").forEach((button) => {
        button.classList.toggle("model", button.dataset.l === r.answer);
      });
      $("model").innerHTML =
        `<div class="verdict ${r.correct ? "ok" : "bad"}">The model says ${esc(r.answer)}: ` +
        `${r.correct ? "correct" : "wrong, the answer is " + esc(r.label)}.</div>` +
        `<table><tr><td>Status</td><td>${esc(r.status)}</td></tr>` +
        `<tr><td>Time</td><td>${r.seconds} s</td></tr></table>` +
        `<details><summary>Prompt</summary><pre>${esc(r.prompt)}</pre></details>`;
      score();
      renderList();
    } catch (error) {
      if (alive) $("model").innerHTML = `<div class="verdict bad">${esc(error.message)}</div>`;
    } finally {
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
    if (["SELECT", "INPUT"].includes(event.target.tagName) ||
        event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toUpperCase();
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
      $("s-data").textContent = `${info.count} problems · ${info.images} images`;
      info.languages.forEach((language) =>
        $("f-lang").insertAdjacentHTML("beforeend", `<option>${esc(language)}</option>`));
      info.levels.forEach((level) =>
        $("f-level").insertAdjacentHTML("beforeend", `<option>${level}</option>`));

      all = await api("/api/problems");
      if (!alive) return;
      renderList();
      if (shown.length) openProblem(shown[0].key);
    } catch (error) {
      if (alive) $("text").textContent = error.message;
    }
  })();

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKeydown);
  };
}
