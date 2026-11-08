"""Text extraction and comparison of source and merged pages (FR-011, research R9). Pure."""

from __future__ import annotations

import difflib
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from .links import ANCHOR, html_text
from .model import Mismatch, PlannedPage, VerificationResult
from .onexml import content_elements, local, parse, q

HEADING_STYLE_NAMES = {"h1", "h2", "h3"}


def paragraphs(element: ET.Element) -> list[str]:
    """Plain text of every one:T below `element` (tags removed, entities decoded)."""
    return [html_text(t.text or "") for t in element.iter(q("T"))]


def extract_text(element: ET.Element) -> str:
    return "\n".join(paragraphs(element))


def page_paragraphs(page_xml: str) -> list[str]:
    """All paragraphs of a page's content (title excluded)."""
    return [p for el in content_elements(parse(page_xml)) for p in paragraphs(el)]


_WEB = re.compile(r"^https?://", re.IGNORECASE)


def web_links(element: ET.Element) -> list[str]:
    """Addresses of the web (http/https) links below `element`, in document order."""
    return [
        href
        for t in element.iter(q("T"))
        for m in ANCHOR.finditer(t.text or "")
        if _WEB.match(href := html.unescape(m.group(2)))
    ]


def page_web_links(page_xml: str) -> list[str]:
    """Web link addresses of a page's content (title excluded)."""
    return [h for el in content_elements(parse(page_xml)) for h in web_links(el)]


def _style_names(page: ET.Element) -> dict[str, str]:
    return {e.get("index", ""): e.get("name", "") for e in page.findall(q("QuickStyleDef"))}


def _heading_text(el: ET.Element, styles: dict[str, str]) -> str | None:
    """Text of `el` if it is a heading outline (one OE in an h1-h3 style), else None."""
    if local(el.tag) != "Outline":
        return None
    oes = list(el.iter(q("OE")))
    if len(oes) != 1 or styles.get(oes[0].get("quickStyleIndex", "")) not in HEADING_STYLE_NAMES:
        return None
    return extract_text(oes[0])


def split_target_blocks(
    target_xml: str, headings: Sequence[str]
) -> list[tuple[ET.Element | None, list[ET.Element]]]:
    """Split a merged page at its heading outlines, matched to `headings` in order."""
    page = parse(target_xml)
    styles = _style_names(page)
    blocks: list[tuple[ET.Element | None, list[ET.Element]]] = [(None, []) for _ in headings]
    nxt, current = 0, None
    for el in content_elements(page):
        text = _heading_text(el, styles)
        match = None
        if text is not None:
            match = next((k for k in range(nxt, len(headings)) if headings[k] == text), None)
        if match is not None:
            blocks[match] = (el, [])
            current, nxt = match, match + 1
        elif current is not None:
            blocks[current][1].append(el)
    return blocks


def verify_page(
    planned: PlannedPage,
    source_texts: Sequence[Sequence[str]],
    target_xml: str,
    target_page_id: str = "",
    source_links: Sequence[Sequence[str]] | None = None,
) -> VerificationResult:
    """Compare the merged page with the source paragraphs of each former page.

    With `source_links`, the web link addresses of each former page are compared too, so a
    web link that OneNote did not recreate (see pagebuilder.unlink_bare_urls) is reported.
    """
    headings = [b.heading for b in planned.blocks]
    split = split_target_blocks(target_xml, headings)
    problems: list[Mismatch] = []
    links = source_links if source_links is not None else [None] * len(planned.blocks)
    for block, expected, want_links, (heading_el, elements) in zip(
        planned.blocks, source_texts, links, split, strict=True
    ):

        def add(kind: str, detail: str, block=block) -> None:
            problems.append(Mismatch(block.page_id, block.original, kind, detail))

        if heading_el is None:
            add("heading", f"Überschrift „{block.heading}“ fehlt")
        if want_links is not None:
            got_links = [h for el in elements for h in web_links(el)]
            if list(want_links) != got_links:
                for href in want_links:
                    if href not in got_links:
                        add("link", f"Weblink fehlt: {href}")
                for href in got_links:
                    if href not in want_links:
                        add("link", f"Weblink zusätzlich: {href}")
                if set(want_links) == set(got_links):
                    add("link", "Weblinks in anderer Reihenfolge oder Anzahl")
        # OneNote drops whitespace at the end of a paragraph when a page is saved, so it is not
        # compared (spec FR-011). Everything else, including leading and inner whitespace, is.
        expected = [p.rstrip() for p in expected]
        actual = [p.rstrip() for el in elements for p in paragraphs(el)]
        if expected == actual:
            continue
        sm = difflib.SequenceMatcher(a=list(expected), b=actual, autojunk=False)
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if op == "delete":
                for text in expected[a1:a2]:
                    add("missing", f"fehlt: „{text}“")
            elif op == "insert":
                for text in actual[b1:b2]:
                    add("extra", f"zusätzlich: „{text}“")
            elif op == "replace":
                for old, new in zip(expected[a1:a2], actual[b1:b2], strict=False):
                    add("changed", f"geändert: „{old}“ → „{new}“")
                for text in expected[a1 + (b2 - b1) : a2]:
                    add("missing", f"fehlt: „{text}“")
                for text in actual[b1 + (a2 - a1) : b2]:
                    add("extra", f"zusätzlich: „{text}“")
    return VerificationResult(
        target_page_id, planned.title, planned.source_section_id, not problems, tuple(problems)
    )
