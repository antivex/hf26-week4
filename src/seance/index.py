"""Split chapters into ~120-word passages and keep them in a JSON index on your disk."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .epub import Book

TARGET_WORDS = 120
INDEX_FILE = "index.json"
# whitespace after ., ! or ? (optionally followed by a closing quote or bracket) ends a sentence
SENTENCE_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)\]]))\s+")


def default_index_dir() -> Path:
    return Path.home() / ".seance"


def split_passages(text: str, target: int = TARGET_WORDS) -> list[str]:
    """Group whole sentences into passages of about ``target`` words; a runaway sentence is cut by words."""
    sentences: list[list[str]] = []
    for sentence in SENTENCE_END.split(" ".join(text.split())):
        words = sentence.split()
        while len(words) > 2 * target:
            sentences.append(words[:target])
            words = words[target:]
        if words:
            sentences.append(words)
    passages: list[list[str]] = []
    current: list[str] = []
    for words in sentences:
        current += words
        if len(current) >= target:
            passages.append(current)
            current = []
    if current:
        if passages and len(current) < target // 3:
            passages[-1] += current  # a short tail joins the passage before it
        else:
            passages.append(current)
    return [" ".join(p) for p in passages]


def load_index(index_dir: str | Path) -> dict:
    path = Path(index_dir) / INDEX_FILE
    if not path.exists():
        return {"version": 1, "books": [], "passages": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_index(index_dir: str | Path, index: dict) -> Path:
    folder = Path(index_dir)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (INDEX_FILE + ".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, folder / INDEX_FILE)
    return folder / INDEX_FILE


def add_book(index: dict, book: Book, source: str | Path) -> int:
    """Add a book's passages to the index, replacing an earlier copy of the same book; returns the passage count."""
    key = (book.author, book.title)
    index["books"] = [b for b in index["books"] if (b["author"], b["title"]) != key]
    index["passages"] = [p for p in index["passages"] if (p["author"], p["book"]) != key]
    new = [{"author": book.author, "book": book.title, "chapter": chapter.title, "text": text}
           for chapter in book.chapters for text in split_passages(chapter.text)]
    index["books"].append({"author": book.author, "title": book.title, "source": str(source),
                           "chapters": len(book.chapters), "passages": len(new)})
    index["passages"] += new
    return len(new)


def find_author(index: dict, name: str) -> str:
    """The author's name as stored in the index: case-insensitive, and a unique part of the name ("poe") works too."""
    authors = sorted({b["author"] for b in index["books"]})
    if not authors:
        raise LookupError("the index is empty: run `seance ingest <book.epub>` first")
    wanted = " ".join(name.split()).casefold()
    exact = [a for a in authors if a.casefold() == wanted]
    if exact:
        return exact[0]
    partial = [a for a in authors if wanted and wanted in a.casefold()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise LookupError(f"'{name}' could be {', '.join(partial)}: be more specific")
    raise LookupError(f"no books by '{name}' in the index. Authors you can summon: {', '.join(authors)}")
