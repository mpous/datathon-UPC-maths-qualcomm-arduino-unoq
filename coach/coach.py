"""Ask the board's language model one question for a student, live.

This is the only place where the Teach copilot waits for the model: about 20
seconds on the board. The system prompt tells the model to coach and not to
solve. That isn't enough on its own with a small model, so core.check_model_text
checks every reply before the student sees it.
"""
from copilot.client import post
from copilot.config import CONFIG
from copilot.llm import URL

from .core import MAX_CHARS

LANGUAGE = {"eng": "English", "cat": "Catalan"}

# Keep the system prompt stable: llama-server caches the start of the prompt
SYSTEM = ("You are a maths coach for school students. A student is working on a problem and asks you a question. "
          "Reply in {language}, in at most two short sentences. Guide the student: name the next step, "
          "or ask a question that helps them think. Do not calculate anything. "
          "Never give a result, the answer, or the letter of an option.")
GRAMMAR = f'root ::= [^\\n]{{15,{MAX_CHARS}}}'


def ask_model(problem, question, timeout=55):
    """Return the model's one-line reply. Raises OSError if the server doesn't answer in time."""
    response = post(URL, {
        "messages": [
            {"role": "system", "content": SYSTEM.format(language=LANGUAGE[problem["language"]])},
            {"role": "user", "content": f"Problem: {problem['text'].strip()}\n\nStudent's question: {question}"}],
        "grammar": GRAMMAR,
        "max_tokens": 90,
        "temperature": 0,
        "seed": int(CONFIG["SEED"]),
        "cache_prompt": True,
    }, timeout=timeout)
    return response["choices"][0]["message"]["content"].strip()
