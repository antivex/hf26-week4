import tempfile
import unittest

from tests import helpers  # noqa: F401  (puts src/ on the import path)

from seance.epub import Book, Chapter
from seance.index import add_book, find_author, load_index, save_index, split_passages


def sentences(count: int, words: int = 10) -> str:
    return " ".join(" ".join(f"w{i}x{j}" for j in range(words - 1)) + f" end{i}." for i in range(count))


class SplitPassagesTest(unittest.TestCase):
    def test_keeps_every_word_in_order(self):
        text = sentences(40)
        self.assertEqual(" ".join(split_passages(text)).split(), text.split())

    def test_passages_are_whole_sentences_of_about_120_words(self):
        passages = split_passages(sentences(37))  # 370 words in 10-word sentences
        self.assertEqual([len(p.split()) for p in passages], [120, 120, 130])  # the 10-word tail joins the last
        self.assertTrue(all(p.endswith(".") for p in passages))

    def test_a_short_chapter_is_one_passage(self):
        self.assertEqual(split_passages("Once upon a midnight dreary.\n\nWhile I pondered."),
                         ["Once upon a midnight dreary. While I pondered."])
        self.assertEqual(split_passages("   "), [])

    def test_a_runaway_sentence_is_cut_by_words(self):
        passages = split_passages(" ".join(["nevermore"] * 500) + ".")
        self.assertTrue(all(len(p.split()) <= 240 for p in passages))
        self.assertEqual(sum(len(p.split()) for p in passages), 500)

    def test_sentences_end_after_closing_quotes(self):
        text = sentences(11) + ' "Is it you?" he asked. ' + sentences(5)
        self.assertTrue(split_passages(text, target=113)[0].endswith('"Is it you?"'))


class IndexTest(unittest.TestCase):
    def book(self, title="Tales", author="Edgar Allan Poe", text="The raven spoke."):
        return Book(title, author, [Chapter("One", text)])

    def test_add_save_and_load(self):
        index = load_index("/nonexistent/seance-index")
        self.assertEqual(index["passages"], [])
        self.assertEqual(add_book(index, self.book(), "tales.epub"), 1)
        with tempfile.TemporaryDirectory() as tmp:
            save_index(tmp, index)
            loaded = load_index(tmp)
        self.assertEqual(loaded["passages"], [{"author": "Edgar Allan Poe", "book": "Tales", "chapter": "One",
                                               "text": "The raven spoke."}])
        self.assertEqual(loaded["books"][0]["passages"], 1)

    def test_ingesting_a_book_again_replaces_it(self):
        index = load_index("/nonexistent/seance-index")
        add_book(index, self.book(text="Old text."), "a.epub")
        add_book(index, self.book(title="Poems"), "b.epub")
        add_book(index, self.book(text="New text."), "a.epub")
        self.assertEqual(sorted(p["text"] for p in index["passages"]), ["New text.", "The raven spoke."])
        self.assertEqual(len(index["books"]), 2)

    def test_find_author(self):
        index = load_index("/nonexistent/seance-index")
        for author in ("Edgar Allan Poe", "Mary Shelley", "Percy Bysshe Shelley"):
            add_book(index, self.book(author=author), "x.epub")
        self.assertEqual(find_author(index, "  edgar   ALLAN poe "), "Edgar Allan Poe")
        self.assertEqual(find_author(index, "poe"), "Edgar Allan Poe")
        with self.assertRaisesRegex(LookupError, "be more specific"):
            find_author(index, "shelley")
        with self.assertRaisesRegex(LookupError, "Authors you can summon: Edgar Allan Poe, Mary Shelley"):
            find_author(index, "Lovecraft")
        with self.assertRaisesRegex(LookupError, "index is empty"):
            find_author(load_index("/nonexistent/seance-index"), "Poe")


if __name__ == "__main__":
    unittest.main()
