"""Read an EPUB with the standard library: container.xml -> OPF (metadata, manifest, spine) -> XHTML chapters."""
from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
}
XHTML_TYPES = {"application/xhtml+xml", "text/html"}
BLOCK_TAGS = {"p", "div", "li", "blockquote", "section", "article", "tr", "pre", "hr", "dd", "dt",
              "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"head", "script", "style", "svg"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class EpubError(ValueError):
    """The file is not an EPUB that can be read."""


@dataclass
class Chapter:
    title: str
    text: str  # paragraphs separated by blank lines


@dataclass
class Book:
    title: str
    author: str
    chapters: list[Chapter] = field(default_factory=list)


class _Extractor(HTMLParser):
    """Collects the visible text (paragraph breaks kept), the first heading, and the links of an XHTML file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.heading: str | None = None
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._heading: list[str] | None = None
        self._link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n\n")
        if tag in HEADINGS and self.heading is None and self._heading is None:
            self._heading = []
        if tag == "a" and dict(attrs).get("href"):
            self._link = (dict(attrs)["href"], [])

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n\n")
        if tag in HEADINGS and self._heading is not None:
            self.heading = " ".join("".join(self._heading).split()) or None
            self._heading = None
        if tag == "a" and self._link:
            self.links.append((self._link[0], " ".join("".join(self._link[1]).split())))
            self._link = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._link:
            self._link[1].append(data)
        if self._heading is not None:
            self._heading.append(data)  # the first heading becomes the chapter title, not passage text
        else:
            self.parts.append(data)

    def text(self) -> str:
        paragraphs = (" ".join(p.split()) for p in re.split(r"\n\s*\n", "".join(self.parts)))
        return "\n\n".join(p for p in paragraphs if p)


def _parse_html(data: bytes) -> _Extractor:
    parser = _Extractor()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    parser.close()
    return parser


def _resolve(base: str, href: str) -> str:
    """Zip member name for an href relative to the folder ``base`` (fragment dropped, %-escapes decoded)."""
    return posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))


def _xml(zf: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError as e:
        raise EpubError(f"missing {name}") from e
    except ET.ParseError as e:
        raise EpubError(f"{name} is not valid XML ({e})") from e


def _rootfile(zf: zipfile.ZipFile) -> str:
    """Path of the OPF package file, from META-INF/container.xml (or the first .opf if the container is missing)."""
    if "META-INF/container.xml" in zf.namelist():
        root = _xml(zf, "META-INF/container.xml").find(".//c:rootfile", NS)
        if root is not None and root.get("full-path"):
            return root.get("full-path")
    opfs = [n for n in zf.namelist() if n.lower().endswith(".opf")]
    if not opfs:
        raise EpubError("no OPF package file")
    return opfs[0]


def _toc_titles(zf: zipfile.ZipFile, manifest: dict, spine: ET.Element | None, base: str) -> dict[str, str]:
    """Chapter titles by zip member name, from the EPUB 3 nav document or else the EPUB 2 NCX."""
    titles: dict[str, str] = {}
    nav = next((i for i in manifest.values() if "nav" in (i.get("properties") or "").split()), None)
    if nav is not None:
        href = _resolve(base, nav.get("href", ""))
        if href in zf.namelist():
            for link, label in _parse_html(zf.read(href)).links:
                if label:
                    titles.setdefault(_resolve(posixpath.dirname(href), link), label)
    ncx = manifest.get(spine.get("toc")) if spine is not None else None
    ncx = ncx if ncx is not None else next(
        (i for i in manifest.values() if i.get("media-type") == "application/x-dtbncx+xml"), None)
    if not titles and ncx is not None:
        href = _resolve(base, ncx.get("href", ""))
        if href in zf.namelist():
            for point in _xml(zf, href).iter(f"{{{NS['ncx']}}}navPoint"):
                label = point.find("ncx:navLabel/ncx:text", NS)
                content = point.find("ncx:content", NS)
                if label is not None and label.text and content is not None and content.get("src"):
                    titles.setdefault(_resolve(posixpath.dirname(href), content.get("src")), " ".join(label.text.split()))
    return titles


def _meta(opf: ET.Element, tag: str) -> str:
    element = opf.find(f".//dc:{tag}", NS)
    return " ".join((element.text or "").split()) if element is not None else ""


def read_epub(path: str | Path) -> Book:
    """Read title, author and the chapters (in spine order) of an EPUB file."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise EpubError(f"not a readable EPUB ({e})") from e
    with zf:
        opf_path = _rootfile(zf)
        opf = _xml(zf, opf_path)
        base = posixpath.dirname(opf_path)
        book = Book(_meta(opf, "title") or Path(path).stem, _meta(opf, "creator") or "Unknown author")
        manifest = {i.get("id"): i for i in opf.iterfind(".//opf:manifest/opf:item", NS)}
        spine = opf.find(".//opf:spine", NS)
        titles = _toc_titles(zf, manifest, spine, base)
        for ref in spine.iterfind("opf:itemref", NS) if spine is not None else []:
            item = manifest.get(ref.get("idref"))
            if (item is None or ref.get("linear") == "no" or item.get("media-type") not in XHTML_TYPES
                    or "nav" in (item.get("properties") or "").split()):
                continue
            name = _resolve(base, item.get("href", ""))
            try:
                parsed = _parse_html(zf.read(name))
            except KeyError:
                continue  # a spine entry pointing at a missing file: skip it
            text = parsed.text()
            if text:
                title = titles.get(name) or parsed.heading or f"Section {len(book.chapters) + 1}"
                book.chapters.append(Chapter(title, text))
    return book
