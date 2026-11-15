/* Analytics page logic. Mounted by the router inside the shared shell. */
export function mount(root) {
  const $ = (id) => root.querySelector(`#${id}`);

  const sample = `id,language,level,has_options,label,answer,correct,seconds,status,prompt_tokens
lvl-0_2016_8,eng,0,False,C,D,0,2.12,error: connection,0
lvl-0_2015_17,eng,0,True,D,D,1,2.03,ok,0
lvl-0_2016_20,eng,0,True,C,D,0,2.04,error: connection,0`;

  function parse(text) {
    const lines = text.trim().split(/\r?\n/);
    const headers = lines.shift().split(",");
    return lines.map((line) => {
      const values = line.split(",");
      return Object.fromEntries(headers.map((h, i) => [h, values[i] || ""]));
    });
  }

  function render(data) {
    const valid = data.filter((r) =>
      "ABCDE".includes((r.answer || "").toUpperCase()) &&
      "ABCDE".includes((r.label || "").toUpperCase()));
    const correct = valid.filter((r) => r.label.toUpperCase() === r.answer.toUpperCase());
    const errors = data.filter((r) => (r.status || "").toLowerCase().includes("error"));
    const latency = data.map((r) => Number(r.seconds)).filter(Number.isFinite);

    $("metrics").innerHTML = [
      ["Evaluated samples", data.length],
      ["Valid answers (A-E)", valid.length],
      ["Accuracy", valid.length ? (correct.length / valid.length * 100).toFixed(1) + "%" : "-"],
      ["Mean latency", latency.length
        ? (latency.reduce((a, b) => a + b, 0) / latency.length).toFixed(2) + " s"
        : "-"],
      ["Execution errors", errors.length],
    ].map(([label, value]) =>
      `<div class="metric"><span>${label}</span><b>${value}</b></div>`).join("");

    $("rows").innerHTML = data.map((r) =>
      `<tr><td>${r.id}</td><td>${r.language}</td><td>${r.level}</td>` +
      `<td>${r.label}</td><td>${r.answer}</td><td>${r.status}</td></tr>`).join("");
  }

  render(parse(sample));

  $("csv").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      render(parse(await file.text()));
      $("status").textContent = file.name;
      $("status").className = "";
    } catch (error) {
      $("status").textContent = error.message;
      $("status").className = "error";
    }
  });
}
