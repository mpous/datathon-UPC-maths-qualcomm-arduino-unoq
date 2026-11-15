/* The Coach page: the hint ladder and the adaptive trainer from coach/.
   The same logic as coach/public/index.html, as a mount() for the router.
   The server's routes are under /api/coach/. */
const T = {
  cat: { start_title:"Comencem", name:"El teu nom", level:"Per quin nivell vols començar?", go:"Comença", ladder_title:"Escala de pistes",
    next:"Següent problema", keys:"Tecles: A–E respon · P pista · N següent", progress_title:"El teu progrés", your_level:"El teu nivell ara",
    topics_title:"Per temes", how_title:"Com funciona", how_text:"Si t'equivoques, no et diem la resposta. Puges una escala de pistes: primer un problema semblant més fàcil, després el mètode, i només al final la solució. Si l'encertes a la primera, el següent problema és més difícil. Tot funciona dins la placa, sense internet.",
    grade:["5è de primària","6è de primària","1r d'ESO","2n d'ESO","3r d'ESO","4t d'ESO","1r de batxillerat","2n de batxillerat"],
    lvl:"Nivell", hint_btn:"Demana una pista", solution_btn:"Mostra la solució", no_more:"No hi ha més pistes",
    right:"Correcte! 🎉", right_hints:"Correcte! Ho has aconseguit amb l'ajuda de les pistes.", wrong:"Encara no. Torna-ho a provar o demana una pista.",
    r_similar:"Problema semblant", r_method:"Mètode", r_model:"Pista del model", r_solution:"Solució",
    h_similar:"Pista 1 · Prova primer aquest problema, que s'assembla i és més fàcil", h_method:"Pista · El mètode", h_model:"Pista · Una idea del model de la placa", h_solution:"La solució",
    warm_right:"Molt bé! Ara torna al problema de dalt amb la mateixa idea.", warm_wrong:"No és aquesta. Prova una altra opció.",
    solution_is:"La resposta correcta és", confirm:"Segur que vols veure la solució? El següent problema serà més fàcil.",
    ask_label:"O pregunta al coach amb les teves paraules (la placa triga uns 20 segons)", ask_btn:"Pregunta", ask_wait:"El coach està pensant… mira la matriu de LEDs.",
    h_ask:"El coach de la placa respon", ask_warning:"Ho ha escrit el model petit de la placa: es pot equivocar. Comprova-ho tu.",
    h_replaced:"El mètode", ask_replaced:"La resposta del model no ha passat les nostres comprovacions (calculava o donava el resultat), així que et donem el mètode.",
    tried:"Problemes fets", solved:"Resolts", first:"A la primera", hints:"Pistes usades", problems:"problemes", sim:"semblança", hello:"Hola",
    leave:"Canvia d'estudiant" },
  eng: { start_title:"Let's start", name:"Your name", level:"Which level do you want to start at?", go:"Start", ladder_title:"Hint ladder",
    next:"Next problem", keys:"Keys: A–E answer · P hint · N next", progress_title:"Your progress", your_level:"Your level now",
    topics_title:"By topic", how_title:"How it works", how_text:"If you get it wrong, we don't tell you the answer. You climb a ladder of hints: first a similar, easier problem, then the method, and only at the end the solution. If you get it right first time, the next problem is harder. Everything runs on the board, with no internet.",
    grade:["Grade 5","Grade 6","Grade 7","Grade 8","Grade 9","Grade 10","Grade 11","Grade 12"],
    lvl:"Level", hint_btn:"Ask for a hint", solution_btn:"Show the solution", no_more:"No more hints",
    right:"Correct! 🎉", right_hints:"Correct! You got there with the hints.", wrong:"Not yet. Try again, or ask for a hint.",
    r_similar:"Similar problem", r_method:"Method", r_model:"Model hint", r_solution:"Solution",
    h_similar:"Hint 1 · First try this problem: it's similar, and easier", h_method:"Hint · The method", h_model:"Hint · An idea from the board's model", h_solution:"The solution",
    warm_right:"Well done! Now go back to the problem above with the same idea.", warm_wrong:"Not this one. Try another option.",
    solution_is:"The correct answer is", confirm:"Are you sure you want to see the solution? The next problem will be easier.",
    ask_label:"Or ask the coach in your own words (the board takes about 20 seconds)", ask_btn:"Ask", ask_wait:"The coach is thinking… look at the LED matrix.",
    h_ask:"The board's coach answers", ask_warning:"The board's small model wrote this: it can be wrong. Check it yourself.",
    h_replaced:"The method", ask_replaced:"The model's reply didn't pass our checks (it calculated, or gave the result), so here is the method instead.",
    tried:"Problems done", solved:"Solved", first:"First try", hints:"Hints used", problems:"problems", sim:"similarity", hello:"Hi",
    leave:"Change student" },
};

const API = "/api/coach";
const SESSION = "coach-student";  // who is practising, so the page survives a visit to another section

function saved() {
  try { return JSON.parse(sessionStorage.getItem(SESSION) || "null"); } catch { return null; }
}
function remember(value) {
  try {
    if (value) sessionStorage.setItem(SESSION, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION);
  } catch { /* the page works without it */ }
}

export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);
  const esc = (v) => String(v).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let lang = "cat", name = "", current = null, warm = null, done = false, rungs = 0, info = null, asking = false;
  let alive = true;
  const t = (key) => T[lang][key];

  async function api(path, body) {
    const response = await fetch(API + path, body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  }

  function texts() {
    root.querySelectorAll("[data-t]").forEach((el) => { el.textContent = t(el.dataset.t); });
    const chosen = $("level").value || "4";
    $("level").innerHTML = t("grade").map((g, i) => `<option value="${i}">${t("lvl")} ${i} · ${esc(g)}</option>`).join("");
    $("level").value = chosen;
    $("bank").textContent = info ? `${info.problems} ${t("problems")} · M3Kang` : "";
    $("who").textContent = name ? `${t("hello")}, ${name}` : "";
    hintButton();
  }

  function optionButtons(box, problem, onPick) {
    box.innerHTML = "ABCDE".split("").map((l) => `<button data-l="${l}"><b>${l})</b><span>${esc(problem.options[l])}</span></button>`).join("");
    box.onclick = (e) => { const b = e.target.closest("button"); if (b && !b.disabled) onPick(b.dataset.l).catch(alertError); };
  }

  function mark(box, letter, correct) {
    box.querySelectorAll("button").forEach((b) => {
      if (b.dataset.l === letter) { b.classList.add(correct ? "right-one" : "wrong-one"); b.disabled = true; }
      if (correct) b.disabled = true;
    });
  }

  function show(problem) {
    current = problem; warm = null; done = false; rungs = 0;
    $("start").classList.add("hidden");
    ["problem", "ladder", "progress"].forEach((id) => $(id).classList.remove("hidden"));
    $("p-level").textContent = `${t("lvl")} ${problem.level} · ${t("grade")[problem.level]}`;
    $("p-topic").textContent = problem.topic_name;
    $("p-id").textContent = problem.id;
    $("p-text").textContent = problem.text;
    $("p-verdict").textContent = ""; $("p-verdict").className = "verdict";
    optionButtons($("p-options"), problem, answer);
    $("hints").innerHTML = ""; $("question").value = ""; $("ask-note").textContent = "";
    $("ask-box").classList.toggle("hidden", !(info && info.coach));
    steps(); hintButton(); progress();
    window.scrollTo({ top: 0 });
  }

  function steps() {
    $("steps").innerHTML = current.ladder.map((r, i) => `<span class="${i < rungs ? "done" : ""}">${i + 1}. ${esc(t("r_" + r))}</span>`).join("");
  }

  function hintButton() {
    if (!current) return;
    const left = current.ladder.length - rungs, button = $("hint");
    button.disabled = done || left <= 0;
    button.textContent = left <= 0 ? t("no_more") : left === 1 ? t("solution_btn") : t("hint_btn");
    $("ask").disabled = done || asking; $("question").disabled = done || asking;
  }

  async function ask() {
    const question = $("question").value.trim();
    if (!current || done || asking || question.length < 3) { $("question").focus(); return; }
    asking = true; hintButton(); $("ask-note").textContent = t("ask_wait");
    try {
      const r = await api("/ask", { name, id: current.id, question });
      if (!alive) return;
      const box = document.createElement("div"); box.className = "hint" + (r.replaced ? "" : " model");
      box.innerHTML = `<h3></h3><div class="hint-note"></div><div class="q"></div><div class="a"></div>`;
      box.querySelector("h3").textContent = r.replaced ? `${t("h_replaced")} · ${r.topic}` : `${t("h_ask")} (${r.seconds} s)`;
      box.querySelector(".hint-note").textContent = r.replaced ? t("ask_replaced") : t("ask_warning");
      box.querySelector(".q").textContent = "« " + question + " »";
      box.querySelector(".a").textContent = r.text;
      $("hints").append(box); $("question").value = ""; $("ask-note").textContent = "";
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) { if (alive) $("ask-note").textContent = error.message; }
    if (!alive) return;
    asking = false; hintButton(); progress();
  }

  async function answer(letter) {
    if (done) return;
    const r = await api("/answer", { name, id: current.id, choice: letter });
    if (!alive) return;
    mark($("p-options"), letter, r.correct);
    if (r.correct) {
      done = true;
      $("p-verdict").textContent = rungs || r.wrong.length ? t("right_hints") : t("right"); $("p-verdict").className = "verdict ok";
    } else { $("p-verdict").textContent = t("wrong"); $("p-verdict").className = "verdict bad"; }
    hintButton(); progress();
  }

  async function warmAnswer(letter) {
    if (!warm || warm.done) return;
    const r = await api("/answer", { name, id: warm.problem.id, choice: letter });
    if (!alive || !warm) return;
    mark(warm.box, letter, r.correct); warm.done = r.correct;
    warm.verdict.textContent = r.correct ? t("warm_right") : t("warm_wrong");
    warm.verdict.className = "verdict " + (r.correct ? "ok" : "bad");
  }

  async function hint() {
    if (!current || done || rungs >= current.ladder.length) return;
    if (current.ladder.length - rungs === 1 && !confirm(t("confirm"))) return;
    const h = await api("/hint", { name, id: current.id });
    if (!alive) return;
    rungs = current.ladder.indexOf(h.type) + 1;
    const box = document.createElement("div"); box.className = "hint" + (h.type === "solution" ? " solution" : h.type === "model" ? " model" : "");
    if (h.type === "similar") {
      box.innerHTML = `<h3>${esc(t("h_similar"))}</h3><div class="meta"><span class="pill">${esc(t("lvl"))} ${h.problem.level}</span><span class="pill">${esc(h.problem.topic_name)}</span><span class="pill">${esc(t("sim"))} ${Math.round(h.similarity * 100)}%</span></div><div class="text"></div><div class="options"></div><div class="verdict"></div>`;
      box.querySelector(".text").textContent = h.problem.text;
      warm = { problem: h.problem, box: box.querySelector(".options"), verdict: box.querySelector(".verdict"), done: false };
      optionButtons(warm.box, h.problem, warmAnswer);
    } else if (h.type === "solution") {
      done = true; warm = null;
      box.innerHTML = `<h3>${esc(t("h_solution"))}</h3><div>${esc(t("solution_is"))} <b>${esc(h.label)}) ${esc(h.value)}</b></div>`;
      $("p-options").querySelectorAll("button").forEach((b) => { b.disabled = true; if (b.dataset.l === h.label) b.classList.add("right-one"); });
    } else {
      box.innerHTML = `<h3>${esc(t("h_" + h.type))}${h.topic ? " · " + esc(h.topic) : ""}</h3><div></div>`;
      box.lastChild.textContent = h.text;
    }
    $("hints").append(box); steps(); hintButton(); progress();
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function next() {
    if (!current) return;
    const r = await api("/next", { name });
    if (alive) show(r.problem);
  }

  async function progress() {
    try {
      const p = await api("/progress?name=" + encodeURIComponent(name));
      if (!alive) return;
      $("track").innerHTML = [0, 1, 2, 3, 4, 5, 6, 7].map((l) => `<div class="${l === p.level ? "on" : ""}">${l}</div>`).join("");
      $("stats").innerHTML = [["tried", p.tried], ["solved", p.solved], ["first", p.first_try], ["hints", p.hints]]
        .map(([k, v]) => `<tr><td class="k">${esc(t(k))}</td><td>${v}</td></tr>`).join("");
      $("topics").innerHTML = p.topics.map((x) => `<tr><td class="k">${esc(x.topic)}</td><td>${x.solved}/${x.tried}</td></tr>`).join("");
    } catch { /* the panel keeps its last numbers */ }
  }

  async function begin(level) {
    const r = await api("/start", { name, language: lang, level });
    if (!alive) return;
    remember({ name, lang });
    $("ui-lang").disabled = true;
    texts();
    show(r.problem);
  }

  async function start() {
    name = $("name").value.trim(); $("start-error").textContent = "";
    if (!name) { $("name").focus(); return; }
    try { await begin(Number($("level").value)); }
    catch (error) { name = ""; $("start-error").textContent = error.message; }
  }

  function leave() {
    remember(null);
    name = ""; current = null; warm = null; done = false; rungs = 0;
    ["problem", "ladder", "progress"].forEach((id) => $(id).classList.add("hidden"));
    $("start").classList.remove("hidden");
    $("ui-lang").disabled = false; $("name").value = "";
    texts(); $("name").focus();
  }

  function alertError(error) {
    if (!alive) return;
    $("p-verdict").textContent = error.message; $("p-verdict").className = "verdict bad";
  }

  $("go").onclick = start;
  $("hint").onclick = () => hint().catch(alertError);
  $("next").onclick = () => next().catch(alertError);
  $("leave").onclick = leave;
  $("name").addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
  $("ask").onclick = ask;
  $("question").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
  $("ui-lang").onchange = (e) => { lang = e.target.value; texts(); };

  function onKeydown(e) {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey || !current) return;
    const k = e.key.toUpperCase();
    if ("ABCDE".includes(k) && k.length === 1) (warm && !warm.done ? warmAnswer(k) : answer(k)).catch(alertError);
    else if (k === "P" || k === "H") hint().catch(alertError);
    else if (k === "N") next().catch(alertError);
  }
  document.addEventListener("keydown", onKeydown);

  (async function init() {
    texts();
    try { info = await api("/info"); } catch { info = null; }
    if (!alive) return;
    texts();
    // Coming back from another section: carry on at the level the student had reached
    const student = saved();
    if (student && student.name && T[student.lang]) {
      try {
        const p = await api("/progress?name=" + encodeURIComponent(student.name));
        if (!alive) return;
        name = student.name; lang = student.lang; $("ui-lang").value = lang;
        await begin(p.level);
      } catch { name = ""; remember(null); texts(); }
    }
  })();

  return () => {
    alive = false;
    document.removeEventListener("keydown", onKeydown);
  };
}
