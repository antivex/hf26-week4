"""Command line: ``seance ingest`` reads EPUB files, ``seance summon`` holds the seance."""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

from . import SILENCE, __version__
from .epub import EpubError, read_epub
from .ghost import DEFAULT_MIN_SCORE, DEFAULT_TOP_K, Answer, summon
from .index import add_book, default_index_dir, find_author, load_index, save_index
from .ollama import DEFAULT_HOST, DEFAULT_MODEL, OllamaError

EXAMPLES = """examples:
  seance ingest ~/Books                       # every .epub in the folder, into ~/.seance
  seance summon "Edgar Allan Poe" --ask "What drives a man to madness?"
  seance summon poe                           # an interactive seance; an empty line ends it

From a clone of the repository, run it as:  PYTHONPATH=src python3 -m seance --help
Needs Ollama running locally (https://ollama.com) and a model: ollama pull gemma4:e2b
"""
# (color, candle, color, text) for each line of the banner of an interactive seance
BANNER = [("33", "       )", "1", "B O O K S H E L F   S E A N C E"),
          ("33", "      (_)", "2", "The candle is lit. {author} is listening."),
          ("", "      |=|", "2", "Ask a question; an empty line ends the seance."),
          ("", "      | |", "", ""),
          ("", "    __|_|__", "", "")]


class Style:
    """ANSI colors, only when wanted and printing to a terminal."""

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled and code else text


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seance", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EXAMPLES,
        description="Bookshelf Seance: summon the dead authors of your EPUB library. A ghost answers only with "
                    "passages from its own books, cites them, and stays silent when its books say nothing. "
                    "Everything runs on your computer, with an open model served locally by Ollama.")
    parser.add_argument("--version", action="version", version=f"seance {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    index_help = "index folder (default: ~/.seance)"

    ingest = commands.add_parser("ingest", help="read EPUB files (or folders of them) into the local index")
    ingest.add_argument("paths", nargs="+", metavar="EPUB_OR_FOLDER")
    ingest.add_argument("--index", default=str(default_index_dir()), help=index_help)
    ingest.set_defaults(run=run_ingest)

    summon_cmd = commands.add_parser("summon", help="ask an author's ghost; without --ask, an interactive seance")
    summon_cmd.add_argument("author", help='author name as in the books, e.g. "Edgar Allan Poe" (case does not matter)')
    summon_cmd.add_argument("--ask", metavar="QUESTION", help="ask one question and leave")
    summon_cmd.add_argument("--index", default=str(default_index_dir()), help=index_help)
    summon_cmd.add_argument("--host", default=os.environ.get("OLLAMA_HOST") or DEFAULT_HOST,
                            help=f"Ollama address (default: $OLLAMA_HOST or {DEFAULT_HOST})")
    summon_cmd.add_argument("--model", default=os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL,
                            help=f"Ollama model (default: $OLLAMA_MODEL or {DEFAULT_MODEL})")
    summon_cmd.add_argument("--top-k", type=_positive_int, default=DEFAULT_TOP_K,
                            help=f"passages shown to the model (default: {DEFAULT_TOP_K})")
    summon_cmd.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE,
                            help=f"BM25 score below which the spirits stay silent (default: {DEFAULT_MIN_SCORE:g})")
    summon_cmd.add_argument("--num-predict", type=_positive_int, default=200,
                            help="maximum tokens in the reply (default: 200)")
    summon_cmd.add_argument("--no-color", action="store_true", help="plain text, no colors")
    summon_cmd.set_defaults(run=run_summon)
    return parser


def run_ingest(args) -> int:
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.suffix.lower() == ".epub")
        elif path.is_file():
            files.append(path)
        else:
            print(f"seance: {raw}: no such file or folder", file=sys.stderr)
    if not files:
        print("seance: no .epub files to ingest", file=sys.stderr)
        return 1
    index, ingested = load_index(args.index), 0
    for path in files:
        try:
            book = read_epub(path)
        except EpubError as e:
            print(f"seance: skipped {path}: {e}", file=sys.stderr)
            continue
        count = add_book(index, book, path)
        ingested += 1
        print(f'Ingested "{book.title}" by {book.author}: {len(book.chapters)} chapters, {count} passages')
    if not ingested:
        return 1
    saved = save_index(args.index, index)
    books = len(index["books"])
    print(f"Index: {saved} ({len(index['passages'])} passages from {books} book{'' if books == 1 else 's'})")
    return 0


def show(answer: Answer, author: str, style: Style) -> None:
    if answer.silent:
        print(style("2;3", SILENCE), flush=True)
        print(style("2", f"  why: {answer.reason}."), file=sys.stderr, flush=True)
        return
    print(style("1;36", f"{author}:"))
    for paragraph in answer.text.split("\n"):
        if paragraph.strip():
            print(textwrap.fill(paragraph.strip(), width=78, initial_indent="  ", subsequent_indent="  "))
    print()
    print(style("2", "Cited passages:"))
    for p in answer.cited:
        print(style("2", f"  [{p['n']}] {p['book']}, \"{p['chapter']}\""))
        print(style("2", textwrap.fill(f"\"{p['quote']}\"", width=78, initial_indent="      ",
                                       subsequent_indent="       ")))


def run_summon(args) -> int:
    index = load_index(args.index)
    try:
        author = find_author(index, args.author)
    except LookupError as e:
        print(f"seance: {e}", file=sys.stderr)
        return 2
    passages = [p for p in index["passages"] if p["author"] == author]
    style = Style(not args.no_color and "NO_COLOR" not in os.environ and sys.stdout.isatty())

    def ask(question: str) -> None:
        show(summon(passages, author, question, host=args.host, model=args.model, top_k=args.top_k,
                    min_score=args.min_score, num_predict=args.num_predict), author, style)

    try:
        if args.ask is not None:
            ask(args.ask)
            return 0
        for art_code, art, text_code, text in BANNER:
            print((style(art_code, art.ljust(14)) + style(text_code, text.replace("{author}", author))).rstrip())
        while True:
            try:
                question = input(style("1", "\nYou: ")).strip()
            except EOFError:
                print()
                break
            if question.casefold() in {"", "quit", "exit", "bye"}:
                break
            ask(question)
        print(style("2", f"The candle gutters out. {author} returns to the dark."))
        return 0
    except OllamaError as e:
        print(f"seance: {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print()
        return 130


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # books are UTF-8: so are pipes and files, and odd characters never crash
            stream.reconfigure(errors="replace", **({} if stream.isatty() else {"encoding": "utf-8"}))
    args = build_parser().parse_args(argv)
    return args.run(args)
