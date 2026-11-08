"""OneNote hierarchy XML -> SourceNotebook (research R12)."""

import xml.etree.ElementTree as ET

from .model import IgnoredItem, SourceGroup, SourceNotebook, SourcePage, SourceSection
from .onexml import local, parse, q


def _true(elem: ET.Element, attr: str) -> bool:
    return elem.get(attr, "false").lower() == "true"


def notebooks(xml: str) -> dict[str, str]:
    """Notebook name -> ID from a GetHierarchy("", hsNotebooks) result."""
    root = parse(xml)
    items = [root] if local(root.tag) == "Notebook" else root.iter(q("Notebook"))
    return {nb.get("name", ""): nb.get("ID", "") for nb in items}


def _pages(section: ET.Element) -> tuple[SourcePage, ...]:
    pages = []
    for p in section.findall(q("Page")):
        if _true(p, "isInRecycleBin"):
            continue
        pages.append(
            SourcePage(
                id=p.get("ID", ""),
                title=p.get("name", ""),
                level=max(1, min(3, int(p.get("pageLevel", "1") or 1))),
                last_modified=p.get("lastModifiedTime", ""),
            )
        )
    return tuple(pages)


def _section(s: ET.Element) -> SourceSection:
    return SourceSection(
        id=s.get("ID", ""),
        name=s.get("name", ""),
        path=s.get("path", ""),
        last_modified=s.get("lastModifiedTime", ""),
        locked=_true(s, "locked") or _true(s, "encrypted"),
        pages=_pages(s),
    )


def parse_hierarchy(xml: str) -> SourceNotebook:
    root = parse(xml)
    nb = root if local(root.tag) == "Notebook" else root.find(q("Notebook"))
    if nb is None:
        raise ValueError("Kein Notizbuch im Hierarchie-XML")
    groups: list[SourceGroup] = []
    ignored: list[IgnoredItem] = []
    for child in nb:
        tag = local(child.tag)
        if tag == "Section":
            ignored.append(
                IgnoredItem(
                    "loose_section",
                    child.get("ID", ""),
                    child.get("name", ""),
                    child.get("path", ""),
                )
            )
        elif tag == "SectionGroup":
            if _true(child, "isRecycleBin"):
                continue
            gname = child.get("name", "")
            sections = []
            for sub in child:
                stag = local(sub.tag)
                if stag == "Section":
                    sections.append(_section(sub))
                elif stag == "SectionGroup" and not _true(sub, "isRecycleBin"):
                    ignored.append(
                        IgnoredItem(
                            "nested_group",
                            sub.get("ID", ""),
                            sub.get("name", ""),
                            sub.get("path", ""),
                            parent=gname,
                        )
                    )
            groups.append(
                SourceGroup(child.get("ID", ""), gname, child.get("path", ""), tuple(sections))
            )
    return SourceNotebook(
        id=nb.get("ID", ""),
        name=nb.get("name", ""),
        path=nb.get("path", ""),
        groups=tuple(groups),
        ignored=tuple(ignored),
    )
