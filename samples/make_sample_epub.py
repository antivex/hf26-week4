"""Build samples/poe-tales.epub: a minimal, valid EPUB 3 with three public-domain tales by Edgar Allan Poe.

    python3 samples/make_sample_epub.py [OUTPUT.epub]

The tales in samples/texts/ are "The Tell-Tale Heart" (1843), "The Masque of the Red Death" (1842) and "The Cask of
Amontillado" (1846), cut from the plain-text Raven Edition, volume 2 (https://www.gutenberg.org/ebooks/2148), with all
Project Gutenberg header, footer and license text removed. Each file has the title on its first line, then paragraphs
separated by blank lines. Standard library only; fixed timestamps, so the same input gives the same file.
"""
from __future__ import annotations

import sys
import zipfile
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TALES = ["the-tell-tale-heart.txt", "the-masque-of-the-red-death.txt", "the-cask-of-amontillado.txt"]
STAMP = (2026, 10, 27, 0, 0, 0)

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-10-27T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{items}
  </manifest>
  <spine>
{itemrefs}
  </spine>
</package>
"""
XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head><title>{title}</title></head>
<body>
{body}
</body>
</html>
"""


def build_epub(path: str | Path, title: str, author: str, chapters: list[tuple[str, list[str]]],
               identifier: str = "urn:bookshelf-seance:sample") -> Path:
    """Write an EPUB 3 file; ``chapters`` is a list of (chapter title, paragraphs)."""
    files, items, itemrefs, links = {"META-INF/container.xml": CONTAINER}, [], [], []
    for number, (chapter, paragraphs) in enumerate(chapters, 1):
        name = f"chapter{number}.xhtml"
        body = f"<h1>{escape(chapter)}</h1>\n" + "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)
        files[f"OEBPS/{name}"] = XHTML.format(title=escape(chapter), body=body)
        items.append(f'    <item id="c{number}" href="{name}" media-type="application/xhtml+xml"/>')
        itemrefs.append(f'    <itemref idref="c{number}"/>')
        links.append(f'<li><a href="{name}">{escape(chapter)}</a></li>')
    nav = '<nav epub:type="toc" id="toc"><h1>Contents</h1>\n<ol>\n' + "\n".join(links) + "\n</ol></nav>"
    files["OEBPS/nav.xhtml"] = XHTML.format(title="Contents", body=nav)
    files["OEBPS/content.opf"] = OPF.format(identifier=escape(identifier), title=escape(title), author=escape(author),
                                            items="\n".join(items), itemrefs="\n".join(itemrefs))
    path = Path(path)
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in [("mimetype", "application/epub+zip"), *files.items()]:
            info = zipfile.ZipInfo(name, STAMP)
            info.external_attr = 0o644 << 16
            # the mimetype entry comes first and uncompressed, as the EPUB container format requires
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            zf.writestr(info, content.encode("utf-8"))
    return path


def read_tale(path: Path) -> tuple[str, list[str]]:
    title, _, rest = path.read_text(encoding="utf-8").partition("\n")
    return title.strip(), [" ".join(p.split()) for p in rest.split("\n\n") if p.strip()]


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else HERE / "poe-tales.epub"
    chapters = [read_tale(HERE / "texts" / name) for name in TALES]
    build_epub(out, "Three Tales of Terror", "Edgar Allan Poe", chapters, identifier="urn:bookshelf-seance:poe-tales")
    print(f"Wrote {out} ({len(chapters)} tales by Edgar Allan Poe)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
