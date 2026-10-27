#!/usr/bin/env bash
# Bookshelf Seance demo: build the sample EPUB (three tales by Edgar Allan Poe), ingest it into a throwaway index and
# ask Poe's ghost three questions. Two are answered from his tales; the third must meet silence.
# Needs Ollama on localhost with the model in $OLLAMA_MODEL (default: docs/demo-model.txt). Run from anywhere:
#   bash docs/demo.sh
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
MODEL="${OLLAMA_MODEL:-$(head -n 1 docs/demo-model.txt)}"
PYTHON="$(command -v python3 || command -v python)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Bookshelf Seance demo, model $MODEL, Ollama at ${OLLAMA_HOST:-http://localhost:11434}"
echo
"$PYTHON" samples/make_sample_epub.py "$WORK/poe-tales.epub"
"$PYTHON" -m seance ingest "$WORK/poe-tales.epub" --index "$WORK/index"

for question in "What drives a man to madness?" "Can anyone escape death?" "What do you think of smartphones?"; do
  echo
  echo "> $question"
  start=$SECONDS
  "$PYTHON" -m seance summon "Edgar Allan Poe" --ask "$question" --index "$WORK/index" --model "$MODEL" \
    --top-k 3 --num-predict 200 --no-color 2>&1
  echo "  ($((SECONDS - start)) s)"
done
