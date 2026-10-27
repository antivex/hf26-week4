# Bookshelf Séance

Hold a séance with the dead authors on your own bookshelf, on your own computer, with the Wi-Fi off.

You summon an author from your EPUB library ("Edgar Allan Poe"), ask a question, and the ghost answers in the first
person. The catch: it may speak **only through passages from its own books**, and it has to cite them. If the books
hold nothing on the subject, it does not improvise. It says:

```text
The spirits are silent on this.
```

Honoring the dead means not putting words in their mouths.

**For whom:** readers with a library of EPUBs (public-domain classics, family letters, out-of-print books) who want
to talk with what an author actually wrote, privately, without uploading their books anywhere.

## How it works

1. `seance ingest` opens each EPUB with `zipfile` (`META-INF/container.xml` -> OPF -> manifest and spine), reads
   title and author from `dc:title` / `dc:creator`, chapter titles from the nav/NCX table of contents (or the first
   heading), strips the XHTML with `html.parser` and cuts every chapter into passages of about 120 words (whole
   sentences). Everything goes into a JSON index in `~/.seance`.
2. `seance summon` ranks that author's passages against your question with **BM25**, written with the standard library.
   If no passage scores above a threshold, the model is **not even called**: the spirits are silent.
3. Otherwise the best passages go to a local open model (Gemma, through Ollama) numbered `[1]..[k]`, with the rule:
   answer in the first person, use only these passages, cite them as `[n]`.
4. **The citation check runs in code, not in the prompt.** Every `[n]` in the reply must be one of the passages that
   were actually shown, and the reply must cite at least one. A reply that cites a passage that does not exist, or
   cites nothing, is thrown away, and the spirits are silent. Under an accepted reply you get the book, the chapter
   and the sentence of each cited passage, so you can check the ghost yourself.

## Install

You need Python 3.10 or newer (standard library only: nothing to `pip install`) and [Ollama](https://ollama.com).

```bash
ollama pull gemma4:e2b          # the smallest Gemma 4: runs on a laptop CPU
git clone https://github.com/antivex/hf26-week4.git && cd hf26-week4
```

A larger model answers better if your computer can run it (for example `ollama pull gemma4:12b`, then
`--model gemma4:12b`). Any chat model in Ollama works.

## Use

From the repository folder (on Windows PowerShell: `$env:PYTHONPATH="src"; python -m seance ...`, or simply
`python src/seance ...`):

```bash
export PYTHONPATH=src
python3 -m seance ingest ~/Books                 # an .epub file or a whole folder
python3 -m seance summon "Edgar Allan Poe" --ask "Can anyone escape death?"
python3 -m seance summon poe                     # an interactive séance; an empty line ends it
python3 -m seance --help
```

Options: `--model` / `OLLAMA_MODEL` (default `gemma4:e2b`), `--host` / `OLLAMA_HOST` (default
`http://localhost:11434`), `--index DIR` (default `~/.seance`), `--top-k` passages shown to the model (default 4),
`--min-score` silence threshold (default 2), `--num-predict` reply length (default 200 tokens), `--no-color`.

Try it on the sample: `python3 samples/make_sample_epub.py` builds `samples/poe-tales.epub` (three public-domain
tales by Poe), and `bash docs/demo.sh` ingests it and asks Poe three questions. With `gemma4:12b` it went like this:

```text
> What drives a man to madness?
Edgar Allan Poe:
  What you mistake for madness is but over-acuteness of the sense [3]. The
  disease had sharpened my senses—not destroyed—not dulled them [2].

Cited passages:
  [2] Three Tales of Terror, "The Tell-Tale Heart"
      "... The disease had sharpened my senses—not destroyed—not dulled them."
  [3] Three Tales of Terror, "The Tell-Tale Heart"
      "... And have I not told you that what you mistake for madness is but
       over-acuteness of the sense?—now, I say, there came to my ears a low,
       dull, quick sound, ..."

> What do you think of smartphones?
The spirits are silent on this.
  why: no passage scored 2 or more (the best scored 0.00), so the model was not called.
```

## Privacy

Your books and your questions stay on your computer. The index is a JSON file in `~/.seance`. The only network
request the program makes is `POST /api/chat` to your Ollama (on `localhost` unless you say otherwise), and it ignores
proxy settings, so nothing is routed elsewhere. No accounts, no telemetry, and it works offline.

## Honest limits

- **Small models are small.** `gemma4:e2b` sometimes paraphrases loosely, slips out of the first person or prefers
  silence. The citation check guarantees that every cited passage exists and was shown; it cannot prove that each
  sentence says exactly what the passage says. That is why the cited sentences are printed: read them.
- **BM25 is lexical.** It matches words (with a tiny suffix stripper), not meanings: "Can anyone escape death?"
  finds the Red Death, while "What is mortality?" finds nothing, although the tales speak of death on every page.
  Silence then means "no matching words", not "the author never touched the idea". The threshold is a plain number
  you can tune with `--min-score`.
- **English-centric:** the stopword list and suffix stripper are English. Other languages work, less well.
- EPUBs with DRM cannot be read, and scanned books without a text layer have nothing to search.

## Sample data

`samples/texts/` holds "The Tell-Tale Heart", "The Masque of the Red Death" and "The Cask of Amontillado" by Edgar
Allan Poe (public domain), cut from the plain-text Raven Edition, volume 2, with every Project Gutenberg header,
footer and license text removed. No personal data anywhere.

## Development

```bash
python3 -m unittest discover -s tests -t .       # offline: a fake Ollama server runs in a thread
```

Ground rules of the project: an open-weight model running locally is the core; Python standard library only; tests
run offline with a fake model server and sample files that contain no real personal data.

## License

MIT, see [LICENSE](LICENSE).

Built during the DEV Hacktoberfest 2026 Open-Source AI Challenge, week 4.

Made by antivex. If it helps you, there's a tip jar: https://ko-fi.com/antivex
