"""Source page XML -> merged target page XML (FR-006..FR-008, research R3/R4/R5). Pure."""

from __future__ import annotations

import copy
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from .layout import BlockInput, Box, find_overlaps, layout_blocks
from .links import ANCHOR, html_text
from .model import ContentIssue, PlannedPage, SourcePage, TitleDecision
from .onexml import content_elements, local, parse, q, tostring

TITLE_BOTTOM = 86.4
HEADING_HEIGHT = 30.0
HEADING_STYLES = {
    "h1": {"fontColor": "#1e4e79", "font": "Calibri Light", "fontSize": "16.0"},
    "h2": {"fontColor": "#2e75b5", "font": "Calibri Light", "fontSize": "14.0"},
    "h3": {"fontColor": "#1f3763", "font": "Calibri Light", "fontSize": "12.0"},
}
_HEAD_TAGS = ("TagDef", "QuickStyleDef")
_ELEMENT_NAMES = {
    "Image": "Bild",
    "InkDrawing": "Freihandzeichnung",
    "InsertedFile": "eingebettete Datei",
    "MediaFile": "Audio-/Videodatei",
}


_WEB_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
# Characters after which OneNote turns a bare web address back into the same link when a page
# is saved, and characters that may follow it. Tested against OneNote (spec FR-007).
_RELINK_BEFORE = frozenset("([{\"'„“‚«»‹<-–:;,.!?=)")
_RELINK_AFTER = frozenset(")]}\"'“”‘’»›.,;:!?")


def unlink_bare_urls(text: str) -> str:
    """Send a web link whose visible text is its own address as plain text, where safe.

    When such a link directly follows a character other than a space (for example "(" in
    "(https://…)"), OneNote's automatic link detection inserts a visible space before it when
    the page is saved. Sent as plain text, OneNote recreates the identical link without the
    space. This is done only where OneNote was tested to do so: the characters between the
    previous space and the link are all in `_RELINK_BEFORE`, and the link is followed by a
    space, the end of the paragraph, or a character in `_RELINK_AFTER`. Verification compares
    web link addresses, so a link OneNote does not recreate is reported (FR-011).
    """

    def sub(m: re.Match[str]) -> str:
        href, inner = html.unescape(m.group(2)), m.group(3)
        if "<" in inner or html_text(inner) != href or not _WEB_URL.match(href):
            return m.group(0)
        before = html_text(text[: m.start()])
        if not before or before[-1].isspace():
            return m.group(0)  # OneNote keeps these links unchanged
        word = re.split(r"\s", before)[-1]
        if any(c not in _RELINK_BEFORE for c in word):
            return m.group(0)
        after = html_text(text[m.end() :])
        if after and not (after[0].isspace() or after[0] in _RELINK_AFTER):
            return m.group(0)
        return inner

    return ANCHOR.sub(sub, text)


class LayoutError(Exception):
    """Blocks of former pages would overlap on the merged page."""


class _Defs:
    """Merged QuickStyleDef / TagDef lists of the target page."""

    def __init__(self, page: ET.Element) -> None:
        self.styles: list[ET.Element] = [e for e in page if e.tag == q("QuickStyleDef")]
        self.tags: list[ET.Element] = [e for e in page if e.tag == q("TagDef")]
        self.style_by_name = {e.get("name", ""): int(e.get("index", "0")) for e in self.styles}
        self.tag_by_key = {self._tag_key(e): int(e.get("index", "0")) for e in self.tags}

    @staticmethod
    def _tag_key(e: ET.Element) -> tuple[str, str, str]:
        return (e.get("symbol", ""), e.get("type", ""), e.get("name", ""))

    def style(self, src: ET.Element) -> int:
        name = src.get("name", "")
        if name not in self.style_by_name:
            new = copy.deepcopy(src)
            idx = max(self.style_by_name.values(), default=-1) + 1
            new.set("index", str(idx))
            self.styles.append(new)
            self.style_by_name[name] = idx
        return self.style_by_name[name]

    def heading_style(self, level: int) -> int:
        name = f"h{level}"
        attrs = {
            "name": name,
            "highlightColor": "automatic",
            "spaceBefore": "0.0",
            "spaceAfter": "0.0",
            **HEADING_STYLES[name],
        }
        return self.style(ET.Element(q("QuickStyleDef"), attrs))

    def tag(self, src: ET.Element) -> int:
        key = self._tag_key(src)
        if key not in self.tag_by_key:
            new = copy.deepcopy(src)
            idx = max(self.tag_by_key.values(), default=-1) + 1
            new.set("index", str(idx))
            self.tags.append(new)
            self.tag_by_key[key] = idx
        return self.tag_by_key[key]


def _t_element(text: str) -> ET.Element:
    t = ET.Element(q("T"))
    t.text = html.escape(text, quote=False)
    return t


def _box(el: ET.Element) -> Box:
    pos, size = el.find(q("Position")), el.find(q("Size"))
    x = float(pos.get("x", "36")) if pos is not None else 36.0
    y = float(pos.get("y", "0")) if pos is not None else 0.0
    w = float(size.get("width", "100")) if size is not None else 100.0
    h = float(size.get("height", "20")) if size is not None else 20.0
    return Box(x, y, w, h)


def _set_position(el: ET.Element, box: Box) -> None:
    pos = el.find(q("Position"))
    if pos is None:
        pos = ET.Element(q("Position"), {"z": "0"})
        el.insert(0, pos)
    pos.set("x", f"{box.x:g}")
    pos.set("y", f"{box.y:g}")


def _heading_outline(text: str, style_index: int, box: Box) -> ET.Element:
    outline = ET.Element(q("Outline"))
    ET.SubElement(outline, q("Position"), {"x": f"{box.x:g}", "y": f"{box.y:g}", "z": "0"})
    ET.SubElement(outline, q("Size"), {"width": f"{box.width:g}", "height": f"{box.height:g}"})
    children = ET.SubElement(outline, q("OEChildren"))
    oe = ET.SubElement(children, q("OE"), {"quickStyleIndex": str(style_index)})
    oe.append(_t_element(text))
    return outline


def _prepare(
    el: ET.Element,
    src_styles: dict[str, ET.Element],
    src_tags: dict[str, ET.Element],
    defs: _Defs,
    issue,
) -> ET.Element | None:
    """Copy one top-level element; returns None if it can't be carried over (issue recorded)."""
    tag = local(el.tag)
    if tag not in ("Outline", "Image", "InkDrawing", "InsertedFile", "MediaFile"):
        issue(tag, "Element kann nicht übertragen werden")
        return None
    new = copy.deepcopy(el)
    # Children that can't be copied are removed from inside outlines, and reported.
    for parent in list(new.iter()):
        for child in list(parent):
            reason = _uncopyable(child)
            if reason:
                issue(local(child.tag), reason)
                parent.remove(child)
    reason = _uncopyable(new)
    if reason:
        issue(tag, reason)
        return None
    for node in new.iter():
        node.attrib.pop("objectID", None)
        node.attrib.pop("selected", None)
        if node.tag == q("T") and node.text and "<a" in node.text.lower():
            node.text = unlink_bare_urls(node.text)
        if "quickStyleIndex" in node.attrib:
            src = src_styles.get(node.get("quickStyleIndex", ""))
            if src is None:
                node.attrib.pop("quickStyleIndex")
            else:
                node.set("quickStyleIndex", str(defs.style(src)))
        if node.tag == q("Tag") and "index" in node.attrib:
            src = src_tags.get(node.get("index", ""))
            if src is not None:
                node.set("index", str(defs.tag(src)))
        if node.tag in (q("InsertedFile"), q("MediaFile")):
            node.set("pathSource", node.get("pathCache", ""))
    return new


def _uncopyable(el: ET.Element) -> str | None:
    tag = local(el.tag)
    if tag in ("Image", "InkDrawing") and el.find(q("Data")) is None:
        return f"{_ELEMENT_NAMES[tag]} ohne Bilddaten (nicht kopierbar)"
    if tag in ("InsertedFile", "MediaFile") and not el.get("pathCache"):
        return f"{_ELEMENT_NAMES[tag]} ohne lokale Kopie (pathCache fehlt)"
    if tag == "FutureObject":
        return "Inhalt eines neueren OneNote-Formats (nicht kopierbar)"
    return None


def unlink_bare_urls_in_page(page_xml: str) -> str:
    """`unlink_bare_urls` applied to every paragraph of a page XML (used for every write)."""
    page = parse(page_xml)
    for t in page.iter(q("T")):
        if t.text and "<a" in t.text.lower():
            t.text = unlink_bare_urls(t.text)
    return tostring(page)


def build_target_page(
    planned: PlannedPage,
    source_pages: Sequence[tuple[SourcePage, TitleDecision, str]],
    target_page_skeleton: str,
    *,
    title_bottom: float = TITLE_BOTTOM,
    heading_height: float = HEADING_HEIGHT,
) -> tuple[str, list[ContentIssue]]:
    target = parse(target_page_skeleton)
    defs = _Defs(target)
    issues: list[ContentIssue] = []

    # Page title (FR-004)
    title = target.find(q("Title"))
    if title is None:
        title = ET.Element(q("Title"))
        target.append(title)
    title_oe = title.find(q("OE"))
    if title_oe is None:
        title_oe = ET.SubElement(title, q("OE"))
    for t in title_oe.findall(q("T")):
        title_oe.remove(t)
    title_oe.append(_t_element(planned.title))

    blocks: list[tuple[str, int, list[ET.Element]]] = []
    for page, decision, xml in source_pages:
        src = parse(xml)
        src_styles = {e.get("index", ""): e for e in src.findall(q("QuickStyleDef"))}
        src_tags = {e.get("index", ""): e for e in src.findall(q("TagDef"))}

        def issue(element: str, message: str, page=page) -> None:
            issues.append(
                ContentIssue(page.id, page.title, planned.source_section_name, element, message)
            )

        elements = []
        for el in content_elements(src):
            new = _prepare(el, src_styles, src_tags, defs, issue)
            if new is not None:
                elements.append(new)
        style = defs.heading_style(max(1, min(3, page.level)))
        blocks.append((decision.heading, style, elements))

    placements = layout_blocks(
        [BlockInput(tuple(_box(e) for e in els)) for _, _, els in blocks],
        title_bottom,
        heading_height,
    )
    overlaps = find_overlaps(placements)
    if overlaps:
        raise LayoutError(f"Blöcke überlappen sich: {overlaps}")

    content: list[ET.Element] = []
    for (heading, style, elements), placement in zip(blocks, placements, strict=True):
        content.append(_heading_outline(heading, style, placement.heading))
        for el, box in zip(elements, placement.elements, strict=True):
            _set_position(el, box)
            content.append(el)

    # Rebuild child order: TagDef*, QuickStyleDef*, other head elements, Title, content.
    others = [
        e
        for e in target
        if local(e.tag) not in _HEAD_TAGS and e is not title and e not in content_elements(target)
    ]
    for e in list(target):
        target.remove(e)
    for e in [*defs.tags, *defs.styles, *others, title, *content]:
        target.append(e)
    return tostring(target), issues
