import unittest

from tests import helpers  # noqa: F401  (puts src/ on the import path)

from seance import SILENCE
from seance.ghost import build_messages, check_citations, cited_numbers, summon

PASSAGES = [{"author": "Edgar Allan Poe", "book": "Tales", "chapter": chapter, "text": text} for chapter, text in [
    ("The Tell-Tale Heart", "True! nervous, very dreadfully nervous I had been, but why will you say that I am mad?"),
    ("The Tell-Tale Heart", "Madmen know nothing. You should have seen how wisely I proceeded, with what caution."),
    ("The Masque of the Red Death", "No pestilence had ever been so fatal. The Red Death held dominion over all."),
    ("The Cask of Amontillado", "The thousand injuries of Fortunato I had borne as I best could; I vowed revenge."),
]]


class FakeModel:
    """Records each call made in place of the Ollama client and returns a canned reply."""

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def __call__(self, host, model, messages, num_predict):
        self.calls.append({"host": host, "model": model, "messages": messages, "num_predict": num_predict})
        return self.reply


def ask(question, reply, min_score=0.5, **options):
    """Hold the seance over PASSAGES (four short passages score lower than a real book, hence the lower threshold)."""
    model = FakeModel(reply)
    answer = summon(PASSAGES, "Edgar Allan Poe", question, host="http://ghost", model="gemma4:e2b", ask=model,
                    min_score=min_score, **options)
    return answer, model.calls


class CitationParsingTest(unittest.TestCase):
    def test_cited_numbers(self):
        self.assertEqual(cited_numbers("I was not mad [2]. The eye [1][3]."), [2, 1, 3])
        self.assertEqual(cited_numbers("Death came [1, 3] [2-4] [ passage 5 ]."), [1, 3, 2, 3, 4, 5])
        self.assertEqual(cited_numbers("No citations here, [sic], [a] or [12a]."), [])

    def test_valid_citations(self):
        self.assertEqual(check_citations("Mad? Never [2]. Hearken [1][2].", 3), ([1, 2], ""))

    def test_invented_citation(self):
        numbers, reason = check_citations("I was calm [1]. I wrote the Raven [7].", 3)
        self.assertEqual(numbers, [])
        self.assertEqual(reason, "the reply cited [7], but only [1] to [3] were shown to the model")
        self.assertIn("[0]", check_citations("Zero [0].", 3)[1])

    def test_missing_citation(self):
        self.assertEqual(check_citations("I was never mad, I promise you.", 3), ([], "the reply cited no passage"))


class SummonTest(unittest.TestCase):
    def test_below_the_threshold_the_model_is_never_called(self):
        answer, calls = ask("What do you think of smartphones?", "I adore my phone [1].")
        self.assertTrue(answer.silent)
        self.assertEqual(answer.text, SILENCE)
        self.assertIn("model was not called", answer.reason)
        self.assertEqual(calls, [])

    def test_threshold_is_configurable(self):
        self.assertEqual(ask("Why are you mad?", "Mad [1].", min_score=99)[1], [])
        self.assertEqual(len(ask("Why are you mad?", "Mad [1].", min_score=0.1)[1]), 1)

    def test_accepted_reply_carries_its_cited_passages(self):
        answer, calls = ask("Was it madness or caution?", "Madmen know nothing [2]. Why call me mad [1]?")
        self.assertFalse(answer.silent)
        self.assertEqual(answer.text, "Madmen know nothing [2]. Why call me mad [1]?")
        self.assertEqual([(p["n"], p["chapter"]) for p in answer.cited],
                         [(1, "The Tell-Tale Heart"), (2, "The Tell-Tale Heart")])
        self.assertEqual(calls[0]["model"], "gemma4:e2b")
        self.assertEqual(calls[0]["num_predict"], 200)

    def test_each_citation_quotes_the_sentence_it_draws_on(self):
        answer, _ = ask("Was it madness or caution?", "Why call me mad [1]? I proceeded with caution [2].")
        self.assertEqual([p["quote"] for p in answer.cited],
                         ["... nervous, very dreadfully nervous I had been, but why will you say that I am mad?",
                          "... You should have seen how wisely I proceeded, with what caution."])

    def test_invented_citation_is_discarded(self):
        answer, calls = ask("Was it madness or caution?", "I am not mad [1]. Quoth the raven [9].")
        self.assertEqual(len(calls), 1)
        self.assertEqual(answer.text, SILENCE)
        self.assertIn("cited [9]", answer.reason)

    def test_reply_without_citations_is_discarded(self):
        answer, _ = ask("Was it madness or caution?", "I am perfectly sane, dear reader.")
        self.assertEqual(answer.text, SILENCE)
        self.assertIn("cited no passage", answer.reason)

    def test_the_ghost_may_choose_silence(self):
        for reply in (SILENCE, "the spirits are silent on this", "  ", "<think>hmm</think>"):
            answer, _ = ask("Was it madness or caution?", reply)
            self.assertEqual(answer.text, SILENCE, reply)

    def test_thinking_is_stripped(self):
        answer, _ = ask("Was it madness or caution?", "<think>[9] maybe</think>Madmen know nothing [2].")
        self.assertEqual(answer.text, "Madmen know nothing [2].")

    def test_only_the_top_k_passages_are_shown_and_numbered(self):
        answer, calls = ask("Was it madness or caution?", "Mad [2].", top_k=2)
        prompt = calls[0]["messages"][1]["content"]
        self.assertIn("[1] (Tales, The Tell-Tale Heart) True!", prompt)
        self.assertIn("[2] (Tales, The Tell-Tale Heart) Madmen", prompt)
        self.assertNotIn("[3]", prompt)
        self.assertEqual(answer.cited[0]["n"], 2)
        self.assertEqual(ask("Was it madness or caution?", "Mad [2].", top_k=1)[0].text, SILENCE)

    def test_prompt(self):
        system, user = build_messages("Edgar Allan Poe", "Is death the end?", PASSAGES[2:3])
        self.assertEqual(system["role"], "system")
        self.assertIn("Speak as Edgar Allan Poe, in the first person", system["content"])
        self.assertIn("ONLY", system["content"])
        self.assertIn(f"reply exactly: {SILENCE}", system["content"])
        self.assertTrue(user["content"].startswith("Passages:\n\n[1] (Tales, The Masque of the Red Death) No pest"))
        self.assertIn("\n\nQuestion: Is death the end?\n\nAnswer as Edgar Allan Poe", user["content"])


if __name__ == "__main__":
    unittest.main()
