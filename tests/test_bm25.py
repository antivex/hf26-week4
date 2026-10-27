import unittest

from tests import helpers  # noqa: F401  (puts src/ on the import path)

from seance.bm25 import BM25, stem, tokenize

DOCS = [
    "The old man's eye, the pale blue eye of a vulture, drove me mad with dread.",
    "The prince shut the gates of the abbey so that no one could escape the Red Death.",
    "We drank the wine in the damp catacombs, and the man laughed at the bells.",
    "The man, the man, the man walked by the man and the man and then another man.",
]


class TokenizeTest(unittest.TestCase):
    def test_stem_groups_word_forms(self):
        for words, expected in ((("madness", "mad"), "mad"), (("drives", "drive", "driving"), "driv"),
                                (("escape", "escaped", "escaping"), "escap"), (("death", "deaths"), "death"),
                                (("eye", "eyes"), "eye"), (("glass",), "glass")):
            self.assertEqual({stem(w) for w in words}, {expected}, words)

    def test_tokenize_drops_stopwords_and_question_framing(self):
        self.assertEqual(tokenize("What do you think of smartphones?"), ["smartphon"])
        self.assertEqual(tokenize("What drives a man to MADNESS?"), ["driv", "man", "mad"])
        self.assertEqual(tokenize("The man's eye_lid"), ["man", "eye", "lid"])


class BM25Test(unittest.TestCase):
    def setUp(self):
        self.bm25 = BM25(DOCS)

    def test_best_match_first(self):
        self.assertEqual(self.bm25.search("Can anyone escape death?", 4)[0][0], 1)
        self.assertEqual(self.bm25.search("What drives a man to madness?", 4)[0][0], 0)

    def test_a_rare_word_outweighs_a_common_one(self):
        rare, common = self.bm25.search("wine", 4)[0][1], self.bm25.search("man", 4)[0][1]
        self.assertGreater(rare, common)

    def test_term_frequency_saturates_and_long_documents_are_penalized(self):
        scores = dict(self.bm25.search("man", 4))
        self.assertGreater(scores[3], scores[2])  # six "man" beat one ...
        self.assertLess(scores[3], 3 * scores[2])  # ... but not six times over

    def test_no_match_returns_nothing(self):
        self.assertEqual(self.bm25.search("What do you think of smartphones?", 4), [])
        self.assertEqual(BM25([]).search("raven", 4), [])

    def test_k_limits_the_results(self):
        self.assertEqual(len(self.bm25.search("man eye death", 2)), 2)


if __name__ == "__main__":
    unittest.main()
