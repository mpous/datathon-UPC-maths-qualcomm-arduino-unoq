"""The Teach copilot: a hint ladder and an adaptive trainer over M3Kang.

No language model runs while the student waits. Everything here is a lookup
in data/teach.db (built by build_bank.py) or a rule, so each step takes
milliseconds. The model's one-sentence hints are written ahead of time by
make_hints.py and checked in code before a student ever sees them.
"""
import json
import random
import re
import sqlite3
import threading
import time

LETTERS = "ABCDE"
LEVELS = range(8)
TWIN = 0.95  # above this similarity it's the same problem at another level, not a hint

# --- Topics -----------------------------------------------------------------
# M3Kang has no topic field. These keyword rules read the English text, and
# the same topic then applies to every translation of the problem (same id).

TOPICS = {
    "geometry": r"triang|square|rectang|circle|angle|perimeter|\barea\b|cube|polygon|hexagon|radius|diagonal|parallel|side length|vertex|vertices|cm\b",
    "counting": r"how many (different |distinct )?(ways|numbers|words|paths|arrangements)|in how many|combination|arrange|permut|choose|different ways",
    "logic": r"\bliar|truth|lies\b|lying|statement|exactly one of|true\b|false\b|who is|which of them",
    "fractions": r"percent|%|fraction|half of|third of|quarter|ratio|proportion|\\frac",
    "numbers": r"digit|divisib|divisor|multiple|prime|remainder|odd\b|even\b|integer|consecutive|factor",
    "sequences": r"sequence|pattern|term\b|terms\b|next number|series|rule",
    "measures": r"\bkm\b|speed|hour|minute|second|clock|euro|cent|price|cost|\bage\b|years old|kg\b|litre|liter|weigh",
}

TIPS = {
    "geometry": {
        "eng": "Draw the figure and write on it every length or angle you know. Which ones are missing?",
        "cat": "Dibuixa la figura i escriu-hi totes les longituds o angles que coneixes. Quins falten?"},
    "counting": {
        "eng": "List the cases in an organised way, for example from smallest to largest, so you don't miss or repeat any.",
        "cat": "Fes una llista ordenada dels casos, per exemple de més petit a més gran, per no deixar-te'n cap ni repetir-ne."},
    "logic": {
        "eng": "Suppose one statement is true and see if it leads to a contradiction. Then try the other case.",
        "cat": "Suposa que una afirmació és certa i mira si porta a una contradicció. Després prova l'altre cas."},
    "fractions": {
        "eng": "Choose a convenient total, like 100 or a common multiple, and work out each part from it.",
        "cat": "Tria un total còmode, com 100 o un múltiple comú, i calcula cada part a partir d'aquest."},
    "numbers": {
        "eng": "Try small examples first and look at the digits or the divisors: what must the number fulfil?",
        "cat": "Prova primer amb exemples petits i fixa't en les xifres o els divisors: què ha de complir el nombre?"},
    "sequences": {
        "eng": "Write the first terms and look for what changes from one to the next.",
        "cat": "Escriu els primers termes i mira què canvia d'un al següent."},
    "measures": {
        "eng": "Write what you know in a small table with its units, then find how the quantities are related.",
        "cat": "Escriu el que saps en una taula petita amb les unitats i busca com es relacionen les quantitats."},
    "arithmetic": {
        "eng": "Give the unknown a name, write the relation the problem gives you, and test your result against the options.",
        "cat": "Posa nom a la incògnita, escriu la relació que et dona el problema i comprova el resultat amb les opcions."},
}

TOPIC_NAMES = {
    "geometry": {"eng": "Geometry", "cat": "Geometria"},
    "counting": {"eng": "Counting", "cat": "Comptar casos"},
    "logic": {"eng": "Logic", "cat": "Lògica"},
    "fractions": {"eng": "Fractions and percentages", "cat": "Fraccions i percentatges"},
    "numbers": {"eng": "Numbers and digits", "cat": "Nombres i xifres"},
    "sequences": {"eng": "Sequences and patterns", "cat": "Successions i patrons"},
    "measures": {"eng": "Measures, time and money", "cat": "Mesures, temps i diners"},
    "arithmetic": {"eng": "Arithmetic and equations", "cat": "Aritmètica i equacions"},
}


def topic_of(english_text):
    """The topic whose keywords appear most often. Arithmetic when none does."""
    text = english_text.lower()
    counts = {topic: len(re.findall(pattern, text)) for topic, pattern in TOPICS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] else "arithmetic"


# --- Checking a hint before a student sees it ---------------------------------

def leaks(hint, problem):
    """True if a hint gives the answer away: the correct value, or its letter."""
    value = str(problem["options"][problem["label"]]).strip().lower()
    text = hint.lower()
    if re.search(r"answer\s*(is|:)|\b(option|opció|resposta)\s*[a-e]\b|\b[a-e]\)", text):
        return True
    if not value:
        return False
    # A number must match as a whole number: "13" leaks, "130" doesn't
    if re.fullmatch(r"[\d.,]+", value):
        return re.search(rf"(?<![\d.,]){re.escape(value)}(?![\d])", text) is not None
    return value in text


MAX_CHARS = 260  # the longest line the model may write for a student


def numbers(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def check_model_text(text, problem, also_allowed=""):
    """Return '' if a line from the model is safe to show, or the reason it isn't.

    The model is told not to calculate and not to give the answer. A small model
    doesn't always obey, so the code decides:
    - it must not contain the correct value or a letter (leaks),
    - it must not contain a number that isn't in the problem or in the
      student's own question (also_allowed): then the model calculated,
    - it must not be cut off at the length limit.
    """
    if leaks(text, problem):
        return "gives the answer"
    extra = numbers(text) - numbers(problem["text"]) - numbers(also_allowed)
    if extra:
        return "new number: " + ", ".join(sorted(extra))
    if len(text) >= MAX_CHARS:
        return "cut off"
    return ""


# --- The bank -----------------------------------------------------------------

class Bank:
    """Every problem, its neighbours and its topic, in memory."""

    def __init__(self, path):
        db = sqlite3.connect(path)
        self.problems = {}  # (id, language) -> problem
        for pid, language, text in db.execute("SELECT id, language, problem FROM problems"):
            self.problems[(pid, language)] = json.loads(text)
        self.neighbours = {}  # id -> [(score, other id)], most similar first
        for pid, other, score in db.execute("SELECT id, other, score FROM neighbours ORDER BY id, score DESC"):
            self.neighbours.setdefault(pid, []).append((score, other))
        db.close()
        self.path = path
        self.level = {pid: p["level"] for (pid, lang), p in self.problems.items() if lang == "eng"}
        self.topic = {pid: topic_of(p["text"]) for (pid, lang), p in self.problems.items() if lang == "eng"}
        self.languages = sorted({lang for _pid, lang in self.problems})

    def model_hint(self, pid, language):
        """The model's one-sentence hint, if make_hints.py wrote one and it passed the checks.

        Read from the file each time, so hints appear while make_hints.py is still running.
        """
        db = sqlite3.connect(self.path)
        try:
            row = db.execute("SELECT hint FROM hints WHERE id = ? AND language = ? AND ok = 1",
                             (pid, language)).fetchone()
        except sqlite3.OperationalError:  # no hints table yet
            row = None
        db.close()
        return row[0] if row else None

    def all_hints(self):
        """Every hint the model wrote, passed or not, with its problem: for the teacher's review page."""
        db = sqlite3.connect(self.path)
        try:
            rows = db.execute("SELECT id, language, hint, ok, reason FROM hints ORDER BY id, language").fetchall()
        except sqlite3.OperationalError:
            rows = []
        db.close()
        return [{"id": pid, "language": language, "hint": hint, "ok": bool(ok), "reason": reason,
                 "level": self.level[pid], "text": self.problems[(pid, language)]["text"],
                 "options": self.problems[(pid, language)]["options"],
                 "label": self.problems[(pid, language)]["label"]}
                for pid, language, hint, ok, reason in rows if self.has(pid, language)]

    def review_hint(self, pid, language, keep):
        """A person keeps or rejects a hint. The code checks can't judge whether the method is right."""
        db = sqlite3.connect(self.path)
        db.execute("UPDATE hints SET ok = ?, reason = ? WHERE id = ? AND language = ?",
                   (int(keep), "human: kept" if keep else "human: rejected", pid, language))
        db.commit()
        db.close()
        return {"ok": True}

    def hint_count(self):
        db = sqlite3.connect(self.path)
        try:
            count = db.execute("SELECT COUNT(*) FROM hints WHERE ok = 1").fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        db.close()
        return count

    def has(self, pid, language):
        return (pid, language) in self.problems

    def public(self, pid, language):
        """A problem without its label, so the page can't give the answer away."""
        problem = self.problems[(pid, language)]
        return {"id": pid, "language": language, "level": problem["level"], "text": problem["text"],
                "options": problem["options"], "topic": self.topic[pid],
                "topic_name": TOPIC_NAMES[self.topic[pid]][language]}

    def easier(self, pid, language, seen=()):
        """The most similar problem at a lower level: the first rung of the ladder.

        At level 0 there's nothing lower, so it's the most similar at the same level.
        Returns (score, other id), or None.
        """
        level = self.level[pid]
        fallback = None
        for score, other in self.neighbours.get(pid, []):
            if score > TWIN or other in seen or not self.has(other, language):
                continue
            if self.level[other] < level:
                return score, other
            if fallback is None and self.level[other] == level:
                fallback = (score, other)
        return fallback

    def pick(self, language, level, seen, near=None, topic=None, rng=random):
        """The next problem at a level: close to the last one if we can, else any unseen one."""
        if near:
            for _score, other in self.neighbours.get(near, []):
                if (self.level[other] == level and other not in seen and self.has(other, language)
                        and (topic is None or self.topic[other] == topic)):
                    return other
        pool = [pid for pid, lvl in self.level.items()
                if lvl == level and pid not in seen and self.has(pid, language)]
        same_topic = [pid for pid in pool if self.topic[pid] == topic]
        pool = same_topic or pool
        return rng.choice(sorted(pool)) if pool else None


# --- The student's profile, kept on the board ----------------------------------

PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    name TEXT PRIMARY KEY, language TEXT NOT NULL, level INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    name TEXT NOT NULL, id TEXT NOT NULL, level INTEGER NOT NULL, topic TEXT NOT NULL,
    solved INTEGER NOT NULL,   -- 1 if the student found the answer
    wrong INTEGER NOT NULL,    -- wrong letters tried
    hints INTEGER NOT NULL,    -- rungs of the ladder used
    warmup INTEGER NOT NULL,   -- 1 for the easier problem of rung 1
    time REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS asks (
    name TEXT NOT NULL, id TEXT NOT NULL, language TEXT NOT NULL,
    question TEXT NOT NULL,
    reply TEXT NOT NULL,       -- what the model wrote
    ok INTEGER NOT NULL,       -- 1 if it passed the checks and the student saw it
    reason TEXT NOT NULL,      -- why it was replaced, if it was
    seconds REAL NOT NULL, time REAL NOT NULL
);
"""

RUNGS = ("similar", "method", "model", "solution")


class Trainer:
    """Turns answers into the next step. One instance serves every student."""

    def __init__(self, bank, profile_path, led=None, coach=None, seed=42):
        self.bank = bank
        self.led = led or (lambda *_args: None)
        self.coach = coach  # coach(problem, question) -> text, from coach/coach.py; None turns it off
        self.coach_busy = threading.Lock()  # the board's model answers one request at a time
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(profile_path, check_same_thread=False)
        self.db.executescript(PROFILE_SCHEMA)
        self.open = {}  # student name -> the problem on screen

    # -- helpers --

    def _student(self, name):
        row = self.db.execute("SELECT language, level FROM students WHERE name = ?", (name,)).fetchone()
        if not row:
            raise KeyError("unknown student")
        return {"name": name, "language": row[0], "level": row[1]}

    def _seen(self, name):
        return {row[0] for row in self.db.execute("SELECT id FROM attempts WHERE name = ?", (name,))}

    def _present(self, name, pid, language, warmup_for=None):
        state = {"id": pid, "wrong": [], "rung": 0, "asks": 0, "solved": False, "warmup_for": warmup_for,
                 "warmup": None, "start": time.time()}
        shown = self.bank.public(pid, language)
        if warmup_for is None:
            self.open[name] = state
            # The rungs this problem has, so the page can warn before the last one
            shown["ladder"] = [rung for rung in RUNGS if rung in ("method", "solution")
                               or (rung == "similar" and self.bank.easier(pid, language, seen=self._seen(name) | {pid}))
                               or (rung == "model" and self.bank.model_hint(pid, language))]
        else:
            self.open[name]["warmup"] = state
        return shown

    def _state(self, name, pid):
        state = self.open.get(name)
        if state and state["warmup"] and state["warmup"]["id"] == pid:
            return state["warmup"]
        if state and state["id"] == pid:
            return state
        raise KeyError("this problem isn't open")

    def _record(self, name, state):
        pid = state["id"]
        self.db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            name, pid, self.bank.level[pid], self.bank.topic[pid], int(state["solved"]),
            len(state["wrong"]), state["rung"] + state["asks"], int(state["warmup_for"] is not None), time.time()))
        self.db.commit()

    # -- the API --

    def start(self, name, language, level):
        """Register or resume a student, and give the first problem."""
        with self.lock:
            if language not in self.bank.languages or level not in LEVELS:
                raise ValueError("bad language or level")
            self.db.execute("INSERT INTO students VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                            "language = excluded.language, level = excluded.level", (name, language, level))
            self.db.commit()
            pid = self.bank.pick(language, level, self._seen(name), rng=self.rng)
            if pid is None:
                raise ValueError("no problems left at this level")
            self.led("level", level)
            return {"problem": self._present(name, pid, language), "level": level}

    def answer(self, name, pid, choice):
        """Check one letter. A wrong answer never reveals the right one."""
        with self.lock:
            student = self._student(name)
            state = self._state(name, pid)
            if state["solved"] or choice in state["wrong"] or choice not in LETTERS:
                raise ValueError("already answered")
            correct = choice == self.bank.problems[(pid, student["language"])]["label"]
            if correct:
                state["solved"] = True
                self._record(name, state)
            else:
                state["wrong"].append(choice)
            self.led("tick" if correct else "cross")
            return {"correct": correct, "warmup": state["warmup_for"] is not None,
                    "wrong": state["wrong"], "rungs_used": state["rung"]}

    def hint(self, name, pid):
        """Climb one rung of the ladder. Only the last rung gives the answer."""
        with self.lock:
            student = self._student(name)
            state = self._state(name, pid)
            if state["warmup_for"] is not None:
                raise ValueError("the warm-up problem has no ladder")
            if state["solved"]:
                raise ValueError("this problem is finished")
            language = student["language"]
            problem = self.bank.problems[(pid, language)]
            while state["rung"] < len(RUNGS):
                rung = RUNGS[state["rung"]]
                state["rung"] += 1
                if rung == "similar":
                    found = self.bank.easier(pid, language, seen=self._seen(name) | {pid})
                    if found:
                        score, other = found
                        self.led("hint", state["rung"])
                        return {"rung": state["rung"], "type": rung, "similarity": round(score, 2),
                                "problem": self._present(name, other, language, warmup_for=pid)}
                elif rung == "method":
                    topic = self.bank.topic[pid]
                    self.led("hint", state["rung"])
                    return {"rung": state["rung"], "type": rung, "topic": TOPIC_NAMES[topic][language],
                            "text": TIPS[topic][language]}
                elif rung == "model":
                    text = self.bank.model_hint(pid, language)
                    if text:
                        self.led("hint", state["rung"])
                        return {"rung": state["rung"], "type": rung, "text": text}
                else:
                    if not state["solved"]:
                        self._record(name, state)
                        state["solved"] = True  # closed: no more answers count
                    self.led("letter", problem["label"])
                    return {"rung": state["rung"], "type": rung, "label": problem["label"],
                            "value": problem["options"][problem["label"]]}
            raise ValueError("no more hints")

    def ask(self, name, pid, question):
        """The student asks the board's model a question, live. About 20 seconds.

        The model gets a coach's system prompt, but the code has the last word:
        a reply that fails check_model_text is never shown. The student gets the
        method tip for the topic instead, and the page says so.
        """
        question = " ".join(str(question).split())[:200]
        if not self.coach:
            raise ValueError("the coach's model isn't available")
        if len(question) < 3:
            raise ValueError("write your question first")
        with self.lock:
            student = self._student(name)
            state = self._state(name, pid)
            if state["warmup_for"] is not None or state["solved"]:
                raise ValueError("this problem is finished")
            language = student["language"]
            problem = self.bank.problems[(pid, language)]
        if not self.coach_busy.acquire(blocking=False):
            raise ValueError("the coach is answering someone else, try again in a moment")
        try:
            self.led("think")
            start = time.perf_counter()
            try:
                reply = self.coach(problem, question)
                reason = check_model_text(reply, problem, also_allowed=question)
            except OSError as error:
                reply, reason = "", f"model error: {error}"
            seconds = round(time.perf_counter() - start, 1)
        finally:
            self.coach_busy.release()
        with self.lock:
            state["asks"] += 1
            self.db.execute("INSERT INTO asks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (name, pid, language, question, reply, int(not reason), reason, seconds, time.time()))
            self.db.commit()
            self.led("level", student["level"])
            if reason:
                topic = self.bank.topic[pid]
                return {"shown": "method", "replaced": True, "text": TIPS[topic][language],
                        "topic": TOPIC_NAMES[topic][language], "seconds": seconds}
            return {"shown": "model", "replaced": False, "text": reply, "seconds": seconds}

    def next(self, name):
        """Choose the next problem from how the last one went."""
        with self.lock:
            student = self._student(name)
            last = self.open.get(name)
            level, near, topic = student["level"], None, None
            if last:
                near, topic = last["id"], self.bank.topic[last["id"]]
                revealed = last["rung"] >= len(RUNGS)
                if (last["solved"] and not revealed and last["rung"] == 0 and not last["wrong"]
                        and not last["asks"]):
                    level = min(level + 1, max(LEVELS))  # right at the first try: harder
                elif revealed or not last["solved"]:
                    if not last["solved"]:
                        self._record(name, last)  # skipped
                    level = max(level - 1, min(LEVELS))  # needed the answer: easier, same topic
                # solved with hints or after a wrong try: stay at this level
            seen = self._seen(name)
            pid = None
            for candidate in sorted(LEVELS, key=lambda l: (abs(l - level), l)):
                pid = (self.bank.pick(student["language"], candidate, seen, near=near, topic=topic, rng=self.rng)
                       or self.bank.pick(student["language"], candidate, seen, near=near, rng=self.rng))
                if pid:
                    level = candidate
                    break
            if pid is None:
                raise ValueError("you have solved every problem")
            self.db.execute("UPDATE students SET level = ? WHERE name = ?", (level, name))
            self.db.commit()
            self.led("level", level)
            return {"problem": self._present(name, pid, student["language"]), "level": level}

    def progress(self, name):
        """What the student has done so far, for the page's summary."""
        with self.lock:
            student = self._student(name)
            rows = self.db.execute("SELECT level, topic, solved, wrong, hints FROM attempts "
                                   "WHERE name = ? AND warmup = 0 ORDER BY time", (name,)).fetchall()
            by_topic = {}
            for _level, topic, solved, _wrong, _hints in rows:
                entry = by_topic.setdefault(topic, {"topic": TOPIC_NAMES[topic][student["language"]],
                                                    "tried": 0, "solved": 0})
                entry["tried"] += 1
                entry["solved"] += solved
            return {"level": student["level"], "tried": len(rows), "solved": sum(r[2] for r in rows),
                    "first_try": sum(1 for r in rows if r[2] and not r[3] and not r[4]),
                    "hints": sum(r[4] for r in rows), "path": [r[0] for r in rows],
                    "topics": sorted(by_topic.values(), key=lambda e: -e["tried"])}
