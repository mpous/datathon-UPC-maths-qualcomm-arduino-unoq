/* Text helpers shared by the Solver and the Uploader (from web1): escaping, a
   little Markdown, and LaTeX shown with plain characters. No CDN: the pages
   must work with no internet. */
export const esc = (value) => String(value).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function latexHtml(tex, display) {
  const s = esc(tex.trim())
    .replace(/\\left|\\right/g, "")
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/\\div/g, "÷")
    .replace(/\\pm/g, "±")
    .replace(/\\mp/g, "∓")
    .replace(/\\leq?/g, "≤")
    .replace(/\\geq?/g, "≥")
    .replace(/\\neq?/g, "≠")
    .replace(/\\approx/g, "≈")
    .replace(/\\equiv/g, "≡")
    .replace(/\\pi/g, "π")
    .replace(/\\alpha/g, "α")
    .replace(/\\beta/g, "β")
    .replace(/\\gamma/g, "γ")
    .replace(/\\theta/g, "θ")
    .replace(/\\Delta/g, "Δ")
    .replace(/\\infty/g, "∞")
    .replace(/\\angle/g, "∠")
    .replace(/\\triangle/g, "△")
    .replace(/\^\\circ|\\circ|\\degree/g, "°")
    .replace(/\\sqrt\{([^{}]+)\}/g, "√($1)")
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1)/($2)")
    .replace(/\\(?:text|mathrm|mathbf|mathit)\{([^{}]+)\}/g, "$1")
    .replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>")
    .replace(/\^([A-Za-z0-9])/g, "<sup>$1</sup>")
    .replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>")
    .replace(/_([A-Za-z0-9])/g, "<sub>$1</sub>")
    .replace(/\\[,;! ]/g, " ");
  return `<span class="math-fallback${display ? " math-display" : ""}">${s}</span>`;
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}

export function renderRichText(raw, inlineOnly = false) {
  if (raw === null || raw === undefined) return "";
  const math = [];
  const withPlaceholders = String(raw).replace(
    /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$(?!\s)([^$\n]+?)(?<!\s)\$)/g,
    (match) => {
      const display = match.startsWith("$$") || match.startsWith("\\[");
      const inner = match.replace(/^\$\$|\$\$$|^\\\[|\\\]$|^\\\(|\\\)$|^\$|\$$/g, "");
      return `\u0000MATH${math.push({ inner, display }) - 1}\u0000`;
    });

  let html = esc(withPlaceholders);
  if (inlineOnly) {
    html = inlineMarkdown(html).replace(/\r?\n/g, " ");
  } else {
    html = html.trim().split(/\n{2,}/).map((block) => {
      const lines = block.split(/\r?\n/);
      if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
        return `<ul>${lines.map((l) => `<li>${inlineMarkdown(l.replace(/^\s*[-*]\s+/, ""))}</li>`).join("")}</ul>`;
      }
      if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) {
        return `<ol>${lines.map((l) => `<li>${inlineMarkdown(l.replace(/^\s*\d+\.\s+/, ""))}</li>`).join("")}</ol>`;
      }
      return `<p>${lines.map(inlineMarkdown).join("<br>")}</p>`;
    }).join("");
  }
  return html.replace(/\u0000MATH(\d+)\u0000/g, (_, i) => latexHtml(math[Number(i)].inner, math[Number(i)].display));
}

export async function api(url, body) {
  const response = await fetch(url, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || response.statusText);
    error.data = data;
    throw error;
  }
  return data;
}
