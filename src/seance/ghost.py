"""The seance itself: find the author's passages, ask the model, and keep its reply only if every citation checks out.

The rule that makes it honest: the ghost may speak only through passages it was shown. Every ``[n]`` in the reply must
be one of the passages ``[1]..[k]`` sent to the model, and the reply must cite at least one. Anything else is thrown
away and the spirits stay silent, because honoring the dead means not putting words in their mouths.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import SILENCE
from .bm25 import BM25, tokenize
from .index import SENTENCE_END
from .ollama import chat

DEFAULT_TOP_K = 4
DEFAULT_MIN_SCORE = 2.0
# "[2]", "[1, 3]", "[1-3]", "[passage 2]": square brackets holding passage numbers
_BRACKETS = re.compile(r"\[\s*(?:passages?\s*)?(\d[\d\s,;\-–]*)\]", re.IGNORECASE)
_NUMBER_OR_RANGE = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?")
_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_SILENT = re.compile(re.escape(SILENCE.rstrip(".")), re.IGNORECASE)


@dataclass
class Answer:
    text: str  # the accepted reply, or SILENCE
    cited: list[dict] = field(default_factory=list)  # cited passages, with their number "n" and a "quote"
    reason: str = ""  # why the spirits are silent

    @property
    def silent(self) -> bool:
        return self.text == SILENCE


def cited_numbers(reply: str) -> list[int]:
    """Every passage number cited in the reply, in order of appearance (ranges like [1-3] are expanded)."""
    numbers: list[int] = []
    for group in _BRACKETS.findall(reply):
        for match in _NUMBER_OR_RANGE.finditer(group):
            low, high = int(match[1]), int(match[2] or match[1])
            numbers += range(low, high + 1) if 0 <= high - low <= 20 else [low, high]
    return numbers


def check_citations(reply: str, shown: int) -> tuple[list[int], str]:
    """(cited numbers, "") when the reply cites only passages 1..shown, else ([], the reason to discard it)."""
    numbers = cited_numbers(reply)
    if not numbers:
        return [], "the reply cited no passage"
    invented = sorted({n for n in numbers if not 1 <= n <= shown})
    if invented:
        listed = ", ".join(f"[{n}]" for n in invented)
        return [], f"the reply cited {listed}, but only [1] to [{shown}] were shown to the model"
    return sorted(set(numbers)), ""


def system_prompt(author: str) -> str:
    return (f"You are the ghost of {author}, speaking at a seance. Speak as {author}, in the first person (\"I\", "
            "\"my\"). Use ONLY the numbered passages from your own books that the user gives you, and add nothing "
            "they do not say. End every sentence with the number of the passage it comes from, in square brackets, "
            "like this: [2]. Never cite a number that is not in the list. Answer in two to four short sentences. "
            f"If the passages do not answer the question, reply exactly: {SILENCE}")


def build_messages(author: str, question: str, shown: list[dict]) -> list[dict]:
    numbered = "\n\n".join(f"[{n}] ({p['book']}, {p['chapter']}) {p['text']}" for n, p in enumerate(shown, 1))
    return [{"role": "system", "content": system_prompt(author)},
            {"role": "user", "content": f"Passages:\n\n{numbered}\n\nQuestion: {question}\n\n"
                                        f"Answer as {author}, in the first person, citing the passages."}]


def quote(passage: str, reply: str, n: int, words: int = 30) -> str:
    """The sentence of the passage that shares most words with what the reply says citing [n], shortened."""
    claims = set(tokenize(" ".join(s for s in SENTENCE_END.split(reply) if n in cited_numbers(s))))
    sentences = SENTENCE_END.split(" ".join(passage.split()))
    best = max(range(len(sentences)), key=lambda i: len(claims & set(tokenize(sentences[i]))))
    parts = sentences[best].split()
    return ("... " if best else "") + " ".join(parts[:words]) + (" ..." if len(parts) > words else "")


def summon(passages: list[dict], author: str, question: str, *, host: str, model: str,
           top_k: int = DEFAULT_TOP_K, min_score: float = DEFAULT_MIN_SCORE, num_predict: int = 200,
           ask: Callable[..., str] = chat) -> Answer:
    """Ask ``author``'s ghost; ``passages`` are that author's passages from the index."""
    hits = BM25([p["text"] for p in passages]).search(question, top_k)
    best = hits[0][1] if hits else 0.0
    if best < min_score:
        return Answer(SILENCE, reason=f"no passage scored {min_score:g} or more (the best scored {best:.2f}), "
                                      "so the model was not called")
    shown = [passages[i] for i, _ in hits]
    reply = _THINKING.sub("", ask(host, model, build_messages(author, question, shown), num_predict=num_predict))
    reply = reply.strip()
    if not reply:
        return Answer(SILENCE, reason="the model returned an empty reply")
    if _SILENT.search(reply):
        return Answer(SILENCE, reason="the ghost found no answer in the passages it was shown")
    numbers, problem = check_citations(reply, len(shown))
    if problem:
        return Answer(SILENCE, reason=f"{problem}, so the reply was discarded")
    return Answer(reply, [dict(shown[n - 1], n=n, quote=quote(shown[n - 1]["text"], reply, n)) for n in numbers])
