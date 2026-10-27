import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, load_sample_builder, write_zip

from seance.epub import EpubError, read_epub

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
# An EPUB 2 package: NCX table of contents, a non-linear cover, a %-escaped href and a chapter missing from the NCX.
OPF2 = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>  Letters   from the Attic </dc:title><dc:creator>Ada Quill</dc:creator><dc:identifier id="id">x</dc:identifier>
</metadata>
<manifest>
  <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
  <item id="one" href="text/chapter%201.xhtml" media-type="application/xhtml+xml"/>
  <item id="two" href="text/two.xhtml" media-type="application/xhtml+xml"/>
  <item id="img" href="pic.png" media-type="image/png"/>
</manifest>
<spine toc="ncx"><itemref idref="cover" linear="no"/><itemref idref="one"/><itemref idref="img"/><itemref idref="two"/>
</spine></package>"""
NCX = """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><navMap>
<navPoint id="p1"><navLabel><text>The First Letter</text></navLabel><content src="text/chapter%201.xhtml#top"/></navPoint>
</navMap></ncx>"""
CHAPTER_ONE = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>ignored</title><style>p {color: red}</style></head>
<body><h2>Letter I</h2><p>Dear reader, the attic is cold &amp; the candle is low.</p>
<script>var hidden = 1;</script><p>Yours,<br/>Ada</p></body></html>"""
CHAPTER_TWO = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1>A Second Letter</h1><p>The floorboards creak at night.</p></body></html>"""


class ReadEpubTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def epub2(self, **overrides):
        files = {"mimetype": "application/epub+zip", "META-INF/container.xml": CONTAINER, "OPS/book.opf": OPF2,
                 "OPS/toc.ncx": NCX, "OPS/cover.xhtml": "<html><body><p>COVER</p></body></html>",
                 "OPS/text/chapter 1.xhtml": CHAPTER_ONE, "OPS/text/two.xhtml": CHAPTER_TWO}
        files.update(overrides)
        return write_zip(self.dir / "letters.epub", {k: v for k, v in files.items() if v is not None})

    def test_epub2_metadata_spine_and_ncx_titles(self):
        book = read_epub(self.epub2())
        self.assertEqual(book.title, "Letters from the Attic")
        self.assertEqual(book.author, "Ada Quill")
        self.assertEqual([c.title for c in book.chapters], ["The First Letter", "A Second Letter"])

    def test_chapter_text_keeps_paragraphs_and_drops_markup(self):
        text = read_epub(self.epub2()).chapters[0].text
        self.assertEqual(text, "Dear reader, the attic is cold & the candle is low.\n\nYours, Ada")
        self.assertNotIn("COVER", text)

    def test_falls_back_to_first_heading_then_section_number(self):
        ncx_empty = NCX.replace("The First Letter", "")
        book = read_epub(self.epub2(**{"OPS/toc.ncx": ncx_empty}))
        self.assertEqual(book.chapters[0].title, "Letter I")
        no_heading = CHAPTER_TWO.replace("<h1>A Second Letter</h1>", "")
        book = read_epub(self.epub2(**{"OPS/toc.ncx": ncx_empty, "OPS/text/two.xhtml": no_heading}))
        self.assertEqual(book.chapters[1].title, "Section 2")

    def test_missing_container_falls_back_to_the_opf(self):
        book = read_epub(self.epub2(**{"META-INF/container.xml": None}))
        self.assertEqual(len(book.chapters), 2)

    def test_not_an_epub(self):
        bad = self.dir / "bad.epub"
        bad.write_text("just text", encoding="utf-8")
        with self.assertRaises(EpubError):
            read_epub(bad)
        with self.assertRaises(EpubError):
            read_epub(write_zip(self.dir / "empty.epub", {"mimetype": "application/epub+zip"}))

    def test_epub3_written_by_the_sample_builder(self):
        builder = load_sample_builder()
        path = builder.build_epub(self.dir / "b.epub", "Ghost <Stories>", "Jane Doe",
                                  [("One", ["First & foremost.", "Second paragraph."]), ("Two", ["Boo."])])
        book = read_epub(path)
        self.assertEqual((book.title, book.author), ("Ghost <Stories>", "Jane Doe"))
        self.assertEqual([(c.title, c.text) for c in book.chapters],
                         [("One", "First & foremost.\n\nSecond paragraph."), ("Two", "Boo.")])

    def test_the_committed_sample_texts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(load_sample_builder().main([str(self.dir / "poe.epub")]), 0)
        book = read_epub(self.dir / "poe.epub")
        self.assertEqual(book.author, "Edgar Allan Poe")
        self.assertEqual([c.title for c in book.chapters],
                         ["The Tell-Tale Heart", "The Masque of the Red Death", "The Cask of Amontillado"])
        self.assertTrue(book.chapters[0].text.startswith("True!—nervous—very, very dreadfully nervous"))
        for tale in (ROOT / "samples" / "texts").glob("*.txt"):
            self.assertNotIn("gutenberg", tale.read_text(encoding="utf-8").lower(), tale.name)


if __name__ == "__main__":
    unittest.main()
