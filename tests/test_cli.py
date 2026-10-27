import contextlib
import io
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT, FakeOllama, load_sample_builder

from seance import SILENCE
from seance.cli import main

MADNESS = "What drives a man to madness?"


def run(*argv, env=None, stdin=None):
    """Run the CLI in-process; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    clean = {k: v for k, v in os.environ.items() if k not in ("OLLAMA_HOST", "OLLAMA_MODEL", "NO_COLOR")}
    with mock.patch.dict(os.environ, {**clean, **(env or {})}, clear=True), \
            mock.patch("sys.stdin", io.StringIO(stdin or "")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.epub = cls.dir / "library" / "poe-tales.epub"
        cls.epub.parent.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            load_sample_builder().main([str(cls.epub)])
        cls.index = cls.dir / "index"
        cls.ingest = run("ingest", cls.epub, "--index", cls.index)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def summon(self, question, fake, *extra, env=None):
        return run("summon", "Edgar Allan Poe", "--ask", question, "--index", self.index, "--host", fake.url,
                   "--no-color", *extra, env=env)

    def test_ingest(self):
        code, out, _ = self.ingest
        self.assertEqual(code, 0)
        self.assertRegex(out, r'Ingested "Three Tales of Terror" by Edgar Allan Poe: 3 chapters, \d+ passages')
        self.assertTrue((self.index / "index.json").exists())

    def test_ingest_a_folder_skips_broken_files(self):
        (self.dir / "library" / "broken.epub").write_text("not a zip", encoding="utf-8")
        code, out, err = run("ingest", self.dir / "library", "--index", self.dir / "other-index")
        self.assertEqual(code, 0)
        self.assertIn("Ingested", out)
        self.assertIn("skipped", err)
        self.assertEqual(run("ingest", self.dir / "nothing-here", "--index", self.dir / "x")[0], 1)

    def test_answer_with_checked_citations(self):
        with FakeOllama("It was the eye of a vulture [1]. Madmen know nothing [2].") as fake:
            code, out, _ = self.summon(MADNESS, fake, env={"OLLAMA_MODEL": "gemma-test"})
        self.assertEqual(code, 0)
        self.assertIn("Edgar Allan Poe:\n  It was the eye of a vulture [1]. Madmen know nothing [2].", out)
        self.assertIn('Cited passages:\n  [1] Three Tales of Terror, "The Tell-Tale Heart"\n      "', out)
        self.assertIn("  [2] Three Tales of Terror", out)
        request = fake.requests[0]
        self.assertEqual(request["model"], "gemma-test")
        self.assertEqual((request["stream"], request["think"]), (False, False))
        self.assertEqual(request["options"]["num_predict"], 200)
        self.assertIn("ghost of Edgar Allan Poe", request["messages"][0]["content"])
        self.assertIn("[4] (Three Tales of Terror, ", request["messages"][1]["content"])
        self.assertNotIn("[5]", request["messages"][1]["content"])

    def test_invented_citation_means_silence(self):
        with FakeOllama("I wrote of telephones too [7].") as fake:
            code, out, err = self.summon(MADNESS, fake)
        self.assertEqual((code, out), (0, SILENCE + "\n"))
        self.assertIn("cited [7], but only [1] to [4] were shown", err)

    def test_missing_citation_means_silence(self):
        with FakeOllama("Madness is a matter of nerves.") as fake:
            self.assertEqual(self.summon(MADNESS, fake)[1], SILENCE + "\n")

    def test_nothing_in_the_books_means_silence_without_calling_the_model(self):
        with FakeOllama("Smartphones are marvellous [1].") as fake:
            code, out, err = self.summon("What do you think of smartphones?", fake)
        self.assertEqual((code, out), (0, SILENCE + "\n"))
        self.assertIn("the model was not called", err)
        self.assertEqual(fake.requests, [])

    def test_options_and_environment(self):
        with FakeOllama("Death held dominion over all [1].") as fake:
            code, out, _ = run("summon", "POE", "--ask", "Can anyone escape death?", "--index", self.index,
                               "--top-k", "2", "--num-predict", "50", "--model", "m",
                               env={"OLLAMA_HOST": fake.url, "NO_COLOR": "1"})
        self.assertEqual(code, 0)
        self.assertIn('"The Masque of the Red Death"', out)
        self.assertEqual((fake.requests[0]["model"], fake.requests[0]["options"]["num_predict"]), ("m", 50))
        self.assertNotIn("[3]", fake.requests[0]["messages"][1]["content"])

    def test_ollama_errors(self):
        with FakeOllama(status=404) as fake:
            code, _, err = self.summon(MADNESS, fake)
        self.assertEqual(code, 3)
        self.assertIn("HTTP 404: model 'gemma4:e2b' not found", err)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            closed = f"http://127.0.0.1:{s.getsockname()[1]}"
        code, _, err = run("summon", "Poe", "--ask", MADNESS, "--index", self.index, "--host", closed)
        self.assertEqual(code, 3)
        self.assertIn("cannot reach Ollama", err)

    def test_unknown_author(self):
        code, _, err = run("summon", "H. P. Lovecraft", "--ask", "Who?", "--index", self.index)
        self.assertEqual(code, 2)
        self.assertIn("Authors you can summon: Edgar Allan Poe", err)

    def test_interactive_seance(self):
        with FakeOllama("Madmen know nothing [1].") as fake:
            code, out, _ = run("summon", "poe", "--index", self.index, "--host", fake.url,
                               stdin=f"{MADNESS}\nWhat do you think of smartphones?\n\n")
        self.assertEqual(code, 0)
        self.assertIn("B O O K S H E L F   S E A N C E", out)
        self.assertIn("(_)", out)
        self.assertIn("Madmen know nothing [1].", out)
        self.assertIn(SILENCE, out)
        self.assertTrue(out.rstrip().endswith("The candle gutters out. Edgar Allan Poe returns to the dark."))
        self.assertEqual(len(fake.requests), 1)
        self.assertNotIn("\033[", out)  # never colors when not printing to a terminal

    def test_python_dash_m_seance(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        help_text = subprocess.run([sys.executable, "-m", "seance", "--help"], capture_output=True, text=True,
                                   env=env, cwd=ROOT, check=True).stdout
        self.assertIn("summon", help_text)
        self.assertIn("ingest", help_text)
        with FakeOllama("Darkness and Decay held dominion [1].") as fake:
            done = subprocess.run([sys.executable, str(ROOT / "src" / "seance"), "summon", "Edgar Allan Poe", "--ask",
                                   "Can anyone escape death?", "--index", str(self.index), "--host", fake.url],
                                  capture_output=True, env=os.environ, cwd=self.dir)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Darkness and Decay held dominion [1].", done.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
