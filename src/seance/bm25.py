"""Okapi BM25 ranking, standard library only. Purely lexical: it matches words, not meanings."""
from __future__ import annotations

import math
import re
from collections import Counter

# Common English words, plus verbs that frame a question ("what do you think of...") rather than name its topic.
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other
our ours ourselves out over own same she should so some such than that the their theirs them themselves then there
these they this those through to too under until up very was we were what when where which while who whom why will
with would you your yours yourself yourselves think tell say said says
""".split())
_WORD = re.compile(r"[^\W_]+")
_SUFFIXES = ("ness", "ing", "ed", "ly", "s")


def stem(word: str) -> str:
    """A deliberately tiny suffix stripper: madness -> mad, drives/drive -> driv, escaped/escape -> escap."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not (suffix == "s" and word.endswith("ss")):
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    """Lower-cased, stemmed words of two letters or more, without stopwords."""
    return [stem(w) for w in _WORD.findall(text.casefold()) if len(w) > 1 and w not in STOPWORDS]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in documents]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avgdl = sum(self.lengths) / len(self.docs) if self.docs else 0.0
        n = len(self.docs)
        df = Counter(term for doc in self.docs for term in doc)
        self.idf = {term: math.log(1 + (n - f + 0.5) / (f + 0.5)) for term, f in df.items()}

    def score(self, terms: set[str], i: int) -> float:
        doc, norm = self.docs[i], self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avgdl or 1))
        return sum(self.idf[t] * doc[t] * (self.k1 + 1) / (doc[t] + norm) for t in terms if doc[t])

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        """The ``k`` best (document number, score) pairs with a score above zero, best first."""
        terms = set(tokenize(query))
        scored = [(i, self.score(terms, i)) for i in range(len(self.docs))]
        return sorted((s for s in scored if s[1] > 0), key=lambda s: (-s[1], s[0]))[:k]
