"""Teach mode: help a student reach the answer instead of giving it.

The hint ladder has three levels: 1 = a nudge (a guiding question), 2 = the method, 3 = the first step.
Everything runs on the board, from the most reliable source to the least:

1. Grounded hints. When the student opens a problem, the board starts solving it in the background (Reason mode's
   Python route, ~30-40 s on the board; the owl closes its eyes while it thinks). If the program's result matches
   an option (and, when we have the answer key, it is the right one), levels 2 and 3 explain that program's
   method in words. Explaining a working program is much easier for the 0.8B model than solving the problem.
2. Strategy hints, always correct by construction: classic problem-solving strategies (smaller cases, patterns,
   systematic counting, drawing, equations, testing the options), chosen from the problem's wording, in English
   and Catalan. Level 1 always comes from here, and levels 2-3 when there is no grounded hint.
3. A guard drops any generated sentence that gives an answer away: 'the answer is', a result equal to any option
   (a wrong one misleads, a right one spoils), or the correct letter.

Measured on the laptop with the same model: free hints without grounding were often wrong ('it lands on 11');
grounded method hints were right on the problems where the program was right.
"""
import json
import re
import threading
import time
import urllib.request

from . import reason
from .config import CONFIG
from .llm import format_problem

URL = f"http://127.0.0.1:{CONFIG['LLM_PORT']}"
NAMES = {"eng": "English", "cat": "Catalan"}

# --- 2. Strategy hints -----------------------------------------------------------------------------------------
# (pattern on the lower-case text, {lang: (nudge, method, first step)})
STRATEGIES = [
    (r"last digit|última xifra|darrera xifra|units digit",
     {"eng": ("What are the last digits of the first few powers? Do they repeat?",
              "Only the last digit matters: write the last digit of the first few powers, find how often the pattern repeats, then use the remainder of the exponent.",
              "Start the list: write the last digit of the 1st, 2nd, 3rd and 4th power. When does it start again?"),
      "cat": ("Quines són les últimes xifres de les primeres potències? Es repeteixen?",
              "Només importa l'última xifra: escriu l'última xifra de les primeres potències, troba cada quant es repeteix el patró i fes servir el residu de l'exponent.",
              "Comença la llista: escriu l'última xifra de la 1a, 2a, 3a i 4a potència. Quan torna a començar?")}),
    (r"\.\.\.|…|after \d+|després de \d+|alternate|alternativament|repeat|repeteix|sequence|seqüència|pattern|patró",
     {"eng": ("What happens after the first two or three steps? Can you see something that repeats?",
              "Work out a few small cases by hand, find the block that repeats, then count how many full blocks fit and what is left over.",
              "Write the position (or value) after step 1, step 2, step 3 and step 4. What changes after each pair of steps?"),
      "cat": ("Què passa després dels dos o tres primers passos? Veus alguna cosa que es repeteix?",
              "Fes uns quants casos petits a mà, troba el bloc que es repeteix, i compta quants blocs complets hi caben i què sobra.",
              "Escriu la posició (o el valor) després del pas 1, del 2, del 3 i del 4. Què canvia després de cada parella de passos?")}),
    (r"how many|quants|quantes|count|compta",
     {"eng": ("How could you list all the possibilities without missing any or counting one twice?",
              "Count systematically: split the cases into groups (for example by the first digit or by size) and count each group.",
              "Start with the smallest case and write the first few that work. Is there a rule for how many there are in each group?"),
      "cat": ("Com podries fer la llista de totes les possibilitats sense deixar-te'n cap ni comptar-ne cap dues vegades?",
              "Compta de manera ordenada: separa els casos en grups (per exemple per la primera xifra o per mida) i compta cada grup.",
              "Comença pel cas més petit i escriu els primers que funcionen. Hi ha una regla de quants n'hi ha a cada grup?")}),
    (r"area|àrea|perimeter|perímetre|angle|triangle|square|quadrat|rectangle|circle|cercle|side|costat",
     {"eng": ("Can you draw the figure and mark every length or angle you know?",
              "Draw it and split the shape into simpler pieces (squares, rectangles, triangles) whose area or length you can compute.",
              "Write down the formula for the simplest piece and put in the numbers you know."),
      "cat": ("Pots dibuixar la figura i marcar-hi totes les longituds o angles que coneixes?",
              "Dibuixa-la i divideix la figura en peces més senzilles (quadrats, rectangles, triangles) de les quals sàpigues calcular l'àrea o la longitud.",
              "Escriu la fórmula de la peça més senzilla i posa-hi els nombres que coneixes.")}),
    (r"years old|age|anys|edat|older|younger|gran que|petit que",
     {"eng": ("What do you not know yet? Could you call it x?",
              "Call the unknown age x, write each sentence of the problem as an equation, and solve it.",
              "Write the first sentence of the problem as an equation with x."),
      "cat": ("Què és el que encara no saps? Ho podries anomenar x?",
              "Anomena x l'edat que no saps, escriu cada frase del problema com una equació i resol-la.",
              "Escriu la primera frase del problema com una equació amb x.")}),
    (r"average|mean|mitjana|sum|suma|total",
     {"eng": ("If you know the average and how many there are, what do you know about the total?",
              "Use total = average × number of items, before and after the change, and compare.",
              "Compute the total before the change."),
      "cat": ("Si saps la mitjana i quants n'hi ha, què saps del total?",
              "Fes servir total = mitjana × nombre d'elements, abans i després del canvi, i compara.",
              "Calcula el total abans del canvi.")}),
    (r"divisible|multiple|múltiple|prime|primer|divisor|remainder|residu",
     {"eng": ("Can you break the numbers into prime factors?",
              "Write each number as a product of primes, then check which condition each option meets.",
              "Factorise the first number in the problem into primes."),
      "cat": ("Pots descompondre els nombres en factors primers?",
              "Escriu cada nombre com un producte de primers i comprova quina condició compleix cada opció.",
              "Descompon en factors primers el primer nombre del problema.")}),
    (r"least|smallest|largest|greatest|minimum|maximum|mínim|màxim|més petit|més gran|almenys",
     {"eng": ("What is the worst (or most extreme) case that could happen?",
              "Think about the extreme case: try the smallest or largest choice that still follows all the rules, and check it really works.",
              "Try the most extreme value you can think of. Does it follow every rule in the problem?"),
      "cat": ("Quin és el pitjor cas (o el més extrem) que podria passar?",
              "Pensa en el cas extrem: prova l'opció més petita o més gran que encara compleix totes les regles, i comprova que funciona.",
              "Prova el valor més extrem que se t'acudeixi. Compleix totes les regles del problema?")}),
]
DEFAULT = {"eng": ("What exactly is the question asking you to find? Underline it.",
                   "Try a smaller or simpler version of the problem first, or test each option against the conditions and cross out the ones that fail.",
                   "Take option A and check it against the first condition of the problem. Does it work?"),
           "cat": ("Què et demana exactament la pregunta? Subratlla-ho.",
                   "Prova primer una versió més petita o més senzilla del problema, o comprova cada opció amb les condicions i ratlla les que no funcionen.",
                   "Agafa l'opció A i comprova-la amb la primera condició del problema. Funciona?")}
FIGURE = {"eng": "Look carefully at the figure: what does it show that the text doesn't say?",
          "cat": "Mira bé la figura: què hi veus que el text no diu?"}


def lang_of(problem):
    return problem.get("language") if problem.get("language") in NAMES else "eng"


def strategy(problem):
    text = problem.get("text", "").lower()
    for pattern, hints in STRATEGIES:
        if re.search(pattern, text):
            return hints[lang_of(problem)]
    return DEFAULT[lang_of(problem)]


# --- 3. The guard ----------------------------------------------------------------------------------------------
GIVEAWAY = re.compile(r"\b(the answer|answer is|correct (option|answer)|la resposta|resposta correcta|"
                      r"l'opció correcta|la solució és|the solution is)\b", re.I)


def states_an_option(sentence, problem):
    """True if the sentence announces any option's value as a result ('lands on 11', '= 9', 'és 10')."""
    s = sentence.lower()
    for value in (problem.get("options") or {}).values():
        v = str(value).strip().lower()
        if re.fullmatch(r"[-−]?\d+(?:[.,]\d+)?", v) and re.search(
                rf"(=|\bis|\bare|\bés|\bson|\bon|\ba|\bget|\bgets|\bequals)\s*{re.escape(v)}\b(?![.,]\d)", s):
            return True
    return False


def leaks(sentence, problem, extra_values=()):
    """True if a sentence gives an answer away."""
    if GIVEAWAY.search(sentence) or states_an_option(sentence, problem):
        return True
    s = sentence.lower()
    for v in extra_values:  # the program's own result, however it's written
        if v and re.search(rf"(?<![\d.]){re.escape(v)}(?![\d])", s):
            return True
    label = problem.get("label")
    if label and (re.search(rf"(answer|option|opció|resposta|correct)\W{{0,12}}\(?{label.lower()}\b", s)
                  or re.search(rf"(^|\s)\(?{label.lower()}\)", s)):
        return True
    return False


# --- 1. Grounded hints -----------------------------------------------------------------------------------------
class Lesson:
    """One problem being taught. Starts solving in the background as soon as it's created."""

    def __init__(self, problem, url=URL, budget_s=40.0):
        self.problem, self.url = problem, url
        self.program, self.value, self.letter, self.reason = "", None, None, "solving"
        self.done = threading.Event()
        threading.Thread(target=self._solve, args=(budget_s,), daemon=True).start()

    def _solve(self, budget_s):
        try:
            if not self.problem.get("options"):
                self.reason = "no text options"
                return
            r = reason.post(self.url + "/completion", {
                "prompt": reason.chat_prompt(self.problem, reason.CODE_INSTRUCTION),
                "n_predict": int(budget_s * reason.WRITE_TPS), "temperature": 0, "seed": int(CONFIG["SEED"]),
                "cache_prompt": True, "t_max_predict_ms": int(budget_s * 1000)}, timeout=budget_s + 30)
            reply = r.get("content", "")
            self.value, self.reason = reason.run_program(reply)
            m = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|$)", reply, flags=re.S)
            self.program = (m.group(1) if m else reply).strip()
            if self.value is not None:
                self.letter = reason.matching_option(self.value, self.problem.get("options"))
                if not self.letter:
                    self.reason = "no option matches"
        except Exception as error:  # noqa: BLE001 - no grounded hints, strategy hints still work
            self.reason = f"error: {type(error).__name__}"
        finally:
            self.done.set()

    @property
    def grounded(self):
        """A program we trust: its result matches an option, and the answer key agrees when we have one."""
        label = self.problem.get("label")
        return bool(self.letter) and (not label or self.letter == label)

    def result_strings(self):
        if self.value is None:
            return ()
        v = self.value
        return tuple({f"{v:g}", str(int(v)) if float(v).is_integer() else f"{v:g}"})


GROUNDED = {
    2: ("Explain in two short sentences the method this program uses, in words a 12-year-old understands. "
        "Don't mention the program, Python or code. Don't give its final result.",
        {"eng": "You can", "cat": "Pots"}, 70),
    3: ("Show the first step of that method with real numbers from the problem, in one or two sentences, then ask "
        "the student to continue. Don't mention the program, Python or code. Don't give the final result.",
        {"eng": "First,", "cat": "Primer,"}, 70),
}
CODE_WORDS = re.compile(r"\b(program|programa|python|code|codi|function|funció|variable|loop|bucle)\b", re.I)


def grounded_prompt(lesson, level):
    instruction, starts, _ = GROUNDED[level]
    lang = lang_of(lesson.problem)
    user = (f"Problem:\n{format_problem(lesson.problem)}\n\nA program that solves it:\n{lesson.program}\n\n"
            f"{instruction} Reply in {NAMES[lang]}.")
    return (f"<|im_start|>system\nYou are a kind math tutor for school students. You never give the final "
            f"answer.<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
            + starts[lang])


def _stream(url, prompt, max_tokens, start_text, timeout):
    """Yield complete sentences from llama-server's streamed completion."""
    request = urllib.request.Request(url + "/completion", data=json.dumps({
        "prompt": prompt, "n_predict": max_tokens, "temperature": 0, "seed": int(CONFIG["SEED"]),
        "cache_prompt": True, "stream": True, "stop": ["<|im_end|>", "\n\n"],
    }).encode(), headers={"Content-Type": "application/json"})
    buffer, first = start_text, True
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = json.loads(line[5:])
            piece = chunk.get("content", "")
            if first:  # the start words already end in a space
                piece, first = piece.lstrip(), False
            buffer += piece
            while True:
                m = re.search(r"[.!?](\s)", buffer)
                if not m:
                    break
                sentence, buffer = buffer[:m.end()].strip(), buffer[m.end():]
                yield sentence
            if chunk.get("stop"):
                break
    if re.search(r"[.!?]$", buffer.strip()):  # a cut-off half sentence is dropped
        yield buffer.strip()


def stream_hint(problem, level, lesson=None, wait_s=45.0, timeout=60):
    """Yield (source, sentence) pairs for hint level 1-3. source is 'strategy' or 'board'."""
    level = min(max(int(level), 1), 3)
    plan = strategy(problem)
    if level == 1:
        if problem.get("text_only") is False:
            yield "strategy", FIGURE[lang_of(problem)]
        yield "strategy", plan[0]
        return
    if lesson is not None:
        lesson.done.wait(timeout=wait_s)
    if lesson is not None and lesson.done.is_set() and lesson.grounded:
        _, starts, max_tokens = GROUNDED[level]
        sent, keep = 0, {2: 1, 3: 2}[level]  # the first sentences are the reliable ones
        try:
            for sentence in _stream(lesson.url, grounded_prompt(lesson, level), max_tokens,
                                    starts[lang_of(problem)] + " ", timeout):
                if sentence and not CODE_WORDS.search(sentence) and \
                        not leaks(sentence, problem, lesson.result_strings()):
                    sent += 1
                    yield "board", sentence
                    if sent >= keep:
                        break
        except OSError:
            pass
        if sent:
            return
    yield "strategy", plan[level - 1]


def hint(problem, level, lesson=None):
    return " ".join(s for _src, s in stream_hint(problem, level, lesson))


# --- Practice and checking -------------------------------------------------------------------------------------
def similar(problem, index, k=3, max_level_gap=1):
    """Up to k related solved problems, same or nearby level, never the same problem in another language."""
    hits = index.search(problem, k=60, exclude_id=problem.get("id"))  # scoring is the slow part; 60 is free
    level = problem.get("level")
    near = [(s, p) for s, p in hits if level is None or abs((p.get("level") or 0) - level) <= max_level_gap]
    return (near or hits)[:k]


def check(problem, letter):
    label = problem.get("label")
    return {"correct": letter == label, "label": label} if label else {"correct": None, "label": None}
