"""Link parsing, indexing, classification and rewriting (FR-009b, research R7). Pure."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

from .model import LinkKind, SourceNotebook
from .onexml import content_elements, parse, q, tostring

_ANCHOR = re.compile(
    r"""<a\s[^>]*?href=(["'])(.*?)\1[^>]*>(.*?)</a\s*>""", re.IGNORECASE | re.DOTALL
)
_TAG = re.compile(r"<[^>]*>")
ANCHOR = _ANCHOR  # <a href=…>text</a> inside one:T HTML (shared with pagebuilder)


@dataclass(frozen=True)
class ParsedLink:
    path: str
    title: str
    section_guid: str | None
    page_guid: str | None
    object_guid: str | None


def _param(fragment: str, key: str) -> str | None:
    m = re.search(rf"(?:^|&){key}=(\{{[^}}]*\}}|[^&]*)", fragment)
    return m.group(1) if m else None


_ABSOLUTE = re.compile(r"^(/*[A-Za-z]:|\\\\|[a-z]+://|/)", re.IGNORECASE)
_BASE_PATH = re.compile(r"&base-path=(.*)$", re.DOTALL)


def parse_onenote_href(href: str) -> ParsedLink | None:
    """Parse a OneNote link.

    OneNote stores links inside pages in a relative form, for example
    ``onenote:#Title&section-id=...&base-path=C:\\...\\2023.one`` or
    ``onenote:Projekte.one#...&base-path=C:\\...\\Notebook``. The path is resolved against
    ``base-path`` so that it can be compared with hierarchy paths.
    """
    if not href.lower().startswith("onenote:"):
        return None
    rest = href[len("onenote:") :]
    base = None
    m = _BASE_PATH.search(rest)
    if m:
        base, rest = m.group(1), rest[: m.start()]
    path, _, fragment = rest.partition("#")
    if base is not None:
        if not path:
            path = base
        elif not _ABSOLUTE.match(path):
            path = base.rstrip("\\/") + "\\" + path
    first = fragment.split("&", 1)[0]
    title = "" if "=" in first and first.split("=", 1)[0].endswith("-id") else unquote(first)
    return ParsedLink(
        path=path,
        title=title,
        section_guid=_param(fragment, "section-id"),
        page_guid=_param(fragment, "page-id"),
        object_guid=_param(fragment, "object-id"),
    )


def norm_path(path: str) -> str:
    """Comparable form: decoded, forward slashes, no trailing slash, no "///" before a drive."""
    p = unquote(path).replace("\\", "/").rstrip("/").casefold()
    return re.sub(r"^/+(?=[a-z]:)", "", p)


def same_target(a: str, b: str) -> bool:
    """True if two OneNote links point at the same object (GUIDs, else resolved path)."""
    pa, pb = parse_onenote_href(a), parse_onenote_href(b)
    if pa is None or pb is None:
        return a == b
    ids_a = tuple(norm_guid(g) for g in (pa.section_guid, pa.page_guid, pa.object_guid))
    ids_b = tuple(norm_guid(g) for g in (pb.section_guid, pb.page_guid, pb.object_guid))
    if any(ids_a) or any(ids_b):
        return ids_a == ids_b
    return norm_path(pa.path) == norm_path(pb.path)


def norm_guid(g: str | None) -> str:
    return (g or "").strip("{}").casefold()


def guid_from_url(url: str, key: str) -> str | None:
    """The `section-id` / `page-id` / `object-id` of a OneNote URL."""
    parsed = parse_onenote_href(url)
    if parsed is None:
        return None
    return {
        "section-id": parsed.section_guid,
        "page-id": parsed.page_guid,
        "object-id": parsed.object_guid,
    }[key]


@dataclass
class LinkIndex:
    notebook_path: str
    pages: dict[tuple[str, str], str] = field(default_factory=dict)  # in scope
    sections: dict[str, str] = field(default_factory=dict)  # in scope
    all_sections: dict[str, str] = field(default_factory=dict)
    groups: dict[str, str] = field(default_factory=dict)  # by path, in scope
    all_groups: dict[str, str] = field(default_factory=dict)
    section_paths: dict[str, str] = field(default_factory=dict)  # in scope
    all_section_paths: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, source: SourceNotebook, section_ids: set[str], group_ids: set[str]) -> LinkIndex:
        idx = cls(norm_path(source.path))
        for g in source.groups:
            idx.all_groups[norm_path(g.path)] = g.id
            if g.id in group_ids:
                idx.groups[norm_path(g.path)] = g.id
            for s in g.sections:
                idx.all_section_paths[norm_path(s.path)] = s.id
                sg = norm_guid(s.link_section_guid)
                if sg:
                    idx.all_sections[sg] = s.id
                if s.id not in section_ids:
                    continue
                idx.section_paths[norm_path(s.path)] = s.id
                if sg:
                    idx.sections[sg] = s.id
                    for p in s.pages:
                        if p.link_page_guid:
                            idx.pages[(sg, norm_guid(p.link_page_guid))] = p.id
        return idx

    def in_notebook(self, path: str) -> bool:
        n = norm_path(path)
        return n == "" or n.startswith(self.notebook_path + "/")


def classify(href: str, index: LinkIndex) -> tuple[LinkKind, str | None]:
    parsed = parse_onenote_href(href)
    if parsed is None:
        return LinkKind.EXTERNAL, None
    sg, pg = norm_guid(parsed.section_guid), norm_guid(parsed.page_guid)
    if pg:
        if (sg, pg) in index.pages:
            kind = (
                LinkKind.TRANSFERRED_PARAGRAPH if parsed.object_guid else LinkKind.TRANSFERRED_PAGE
            )
            return kind, index.pages[(sg, pg)]
        if sg in index.sections:
            return LinkKind.TARGET_NOT_FOUND, None
        if sg in index.all_sections:
            return LinkKind.OUTSIDE_TRANSFER, None
        if index.in_notebook(parsed.path):
            return LinkKind.TARGET_NOT_FOUND, None
        return LinkKind.OUTSIDE_TRANSFER, None
    if sg:
        if sg in index.sections:
            return LinkKind.TRANSFERRED_SECTION, index.sections[sg]
        if sg in index.all_sections:
            return LinkKind.OUTSIDE_TRANSFER, None
        if index.in_notebook(parsed.path):
            return LinkKind.TARGET_NOT_FOUND, None
        return LinkKind.OUTSIDE_TRANSFER, None
    path = norm_path(parsed.path)
    if path in index.groups:
        return LinkKind.TRANSFERRED_GROUP, index.groups[path]
    if path in index.section_paths:
        return LinkKind.TRANSFERRED_SECTION, index.section_paths[path]
    if path in index.all_groups or path in index.all_section_paths or path == index.notebook_path:
        return LinkKind.OUTSIDE_TRANSFER, None
    if index.in_notebook(parsed.path):
        return LinkKind.TARGET_NOT_FOUND, None
    return LinkKind.OUTSIDE_TRANSFER, None


def html_text(fragment: str) -> str:
    return html.unescape(_TAG.sub("", fragment))


def extract_links(page_xml: str) -> list[tuple[str, str]]:
    """(visible text, href) of every anchor in the page content, in document order."""
    page = parse(page_xml)
    out = []
    for el in content_elements(page):
        for t in el.iter(q("T")):
            for m in _ANCHOR.finditer(t.text or ""):
                out.append((html_text(m.group(3)), html.unescape(m.group(2))))
    return out


def rewrite_text(text: str, mapping: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        new = mapping.get(html.unescape(m.group(2)))
        if new is None:
            return m.group(0)
        quote = m.group(1)
        start, end = m.span(2)
        base = m.start(0)
        raw = html.escape(new, quote=True)
        whole = m.group(0)
        return whole[: start - base] + raw + whole[end - base :] if quote else whole

    return _ANCHOR.sub(sub, text)


def rewrite_hrefs(page_xml: str, mapping: dict[str, str]) -> str:
    """Change only `href` values found in `mapping`; link text and all else stay unchanged."""
    page = parse(page_xml)
    for t in page.iter(q("T")):
        if t.text and "<a" in t.text.lower():
            t.text = rewrite_text(t.text, mapping)
    return tostring(page)
