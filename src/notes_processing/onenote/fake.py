"""In-memory stand-in for OneNoteGateway, used by unit tests (constitution V).

Link URLs are deterministic: the "GUID" of an object with ID ``X`` is ``{L-X}``, and the GUID of
paragraph ``O`` on page ``P`` is ``{L-P/O}`` (research R7 URL shapes).
"""

from __future__ import annotations

import itertools
import xml.etree.ElementTree as ET

from ..onexml import local, parse, q, tostring
from .errors import NotFound, OneNoteCallFailed, OneNoteUnavailable, WriteOutsideTarget

_SKELETON = (
    '<one:Page xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote" ID="{id}" '
    'name="" pageLevel="1">'
    '<one:QuickStyleDef index="0" name="PageTitle" fontColor="automatic" '
    'highlightColor="automatic" font="Calibri Light" fontSize="20.0" spaceBefore="0.0" '
    'spaceAfter="0.0"/>'
    '<one:PageSettings RTL="false" color="automatic"><one:PageSize><one:Automatic/>'
    '</one:PageSize><one:RuleLines visible="false"/></one:PageSettings>'
    '<one:Title lang="de"><one:OE quickStyleIndex="0" objectID="{id}-title">'
    "<one:T><![CDATA[]]></one:T></one:OE></one:Title>"
    "</one:Page>"
)


def guid(object_id: str) -> str:
    return f"{{L-{object_id}}}"


class FakeGateway:
    def __init__(
        self,
        hierarchy_xml: str,
        pages: dict[str, str] | None = None,
        *,
        fail_on: dict[str, int] | None = None,
        unavailable_after: int | None = None,
        unavailable_count: int | None = None,
        special_folder: str = r"C:\Notes",
    ) -> None:
        root = parse(hierarchy_xml)
        if local(root.tag) == "Notebook":
            wrapper = ET.Element(q("Notebooks"))
            wrapper.append(root)
            root = wrapper
        self._root = root
        self._pages: dict[str, str] = dict(pages or {})
        self._fail_on = dict(fail_on or {})
        self._unavailable_after = unavailable_after
        self._unavailable_left = unavailable_count
        self._special = special_folder
        self._counter = itertools.count(1)
        self._method_counts: dict[str, int] = {}
        self.calls: list[tuple[str, tuple]] = []
        self.target_notebook_id: str | None = None
        self._target_ids: set[str] = set()

    # ------------------------------------------------------------------ plumbing
    def _record(self, method: str, *args: object) -> None:
        self.calls.append((method, args))
        n = self._method_counts[method] = self._method_counts.get(method, 0) + 1
        if (
            self._unavailable_after is not None
            and len(self.calls) > self._unavailable_after
            and (self._unavailable_left is None or self._unavailable_left > 0)
        ):
            if self._unavailable_left is not None:
                self._unavailable_left -= 1
            raise OneNoteUnavailable(f"{method}: OneNote antwortet nicht (simuliert)")
        if self._fail_on.get(method) == n:
            raise OneNoteCallFailed(method, 0x80042014, "simulierter Fehler")

    def _find(self, object_id: str) -> ET.Element:
        for el in self._root.iter():
            if el.get("ID") == object_id:
                return el
        raise NotFound(object_id)

    def _parent(self, object_id: str) -> ET.Element:
        for parent in self._root.iter():
            for child in parent:
                if child.get("ID") == object_id:
                    return parent
        raise NotFound(object_id)

    def _guard(self, object_id: str) -> None:
        if self.target_notebook_id is None or object_id not in self._target_ids:
            raise WriteOutsideTarget(f"Schreibzugriff auf {object_id!r} verweigert")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._counter)}"

    @property
    def write_calls(self) -> list[tuple[str, tuple]]:
        writes = {
            "create_notebook",
            "create_section",
            "create_section_group",
            "create_page",
            "update_page",
        }
        return [c for c in self.calls if c[0] in writes]

    # ------------------------------------------------------------------ reads
    def hierarchy(self, start_id: str, scope: int) -> str:
        self._record("hierarchy", start_id, scope)
        if not start_id:
            if scope <= 2:  # notebooks only
                shallow = ET.Element(self._root.tag)
                for nb in self._root:
                    shallow.append(ET.Element(nb.tag, dict(nb.attrib)))
                return tostring(shallow)
            return tostring(self._root)
        return tostring(self._find(start_id))

    def page_xml(self, page_id: str, binary: bool = True) -> str:
        self._record("page_xml", page_id, binary)
        if page_id not in self._pages:
            raise OneNoteCallFailed("GetPageContent", 0x80042014, f"Seite {page_id} fehlt")
        return self._pages[page_id]

    def link_to(self, hierarchy_id: str, object_id: str = "") -> str:
        self._record("link_to", hierarchy_id, object_id)
        el = self._find(hierarchy_id)
        tag = local(el.tag)
        if tag == "Page":
            section = self._parent(hierarchy_id)
            url = (
                f"onenote:{section.get('path')}#{el.get('name', '')}"
                f"&section-id={guid(section.get('ID', ''))}&page-id={guid(hierarchy_id)}"
            )
            if object_id:
                url += f"&object-id={guid(f'{hierarchy_id}/{object_id}')}"
            return url + "&end"
        if tag == "Section":
            return f"onenote:{el.get('path')}#section-id={guid(hierarchy_id)}&end"
        return f"onenote:{el.get('path')}"

    def special_folder(self) -> str:
        self._record("special_folder")
        return self._special

    def notebook_names(self) -> list[str]:
        self._record("notebook_names")
        return [nb.get("name", "") for nb in self._root]

    # ------------------------------------------------------------------ writes
    def create_notebook(self, folder: str, name: str) -> str:
        self._record("create_notebook", folder, name)
        if self.target_notebook_id is not None:
            raise WriteOutsideTarget("Das Zielnotizbuch wurde bereits angelegt")
        nb_id = self._new_id("TNB")
        path = f"{folder.rstrip('\\/')}\\{name}"
        ET.SubElement(self._root, q("Notebook"), {"name": name, "ID": nb_id, "path": path})
        self.target_notebook_id = nb_id
        self._target_ids.add(nb_id)
        return nb_id

    def create_section(self, name: str, parent_id: str | None = None) -> str:
        if self.target_notebook_id is None:
            raise WriteOutsideTarget("Abschnitt vor dem Zielnotizbuch angelegt")
        self._guard(parent_id or self.target_notebook_id)
        self._record("create_section", name)
        parent = self._find(parent_id or self.target_notebook_id)
        sid = self._new_id("TS")
        ET.SubElement(
            parent,
            q("Section"),
            {"name": name, "ID": sid, "path": f"{parent.get('path')}\\{name}.one"},
        )
        self._target_ids.add(sid)
        return sid

    def create_section_group(self, name: str) -> str:
        if self.target_notebook_id is None:
            raise WriteOutsideTarget("Abschnittsgruppe vor dem Zielnotizbuch angelegt")
        self._record("create_section_group", name)
        nb = self._find(self.target_notebook_id)
        gid = self._new_id("TG")
        ET.SubElement(
            nb, q("SectionGroup"), {"name": name, "ID": gid, "path": f"{nb.get('path')}\\{name}"}
        )
        self._target_ids.add(gid)
        return gid

    def create_page(self, section_id: str) -> str:
        self._guard(section_id)  # like the real gateway: refused before any OneNote call
        self._record("create_page", section_id)
        pid = self._new_id("TP")
        ET.SubElement(self._find(section_id), q("Page"), {"ID": pid, "name": "", "pageLevel": "1"})
        self._pages[pid] = _SKELETON.format(id=pid)
        self._target_ids.add(pid)
        return pid

    def update_page(self, xml: str) -> None:
        """Merge like OneNote: sent elements with a known objectID replace the existing ones,
        new elements are added, elements not sent stay as they are."""
        update = parse(xml)
        pid = update.get("ID", "")
        self._guard(pid)
        self._record("update_page", xml)
        page = parse(self._pages[pid])
        for el in update:
            name = local(el.tag)
            if name in ("QuickStyleDef", "TagDef"):
                old = next(
                    (e for e in page.findall(el.tag) if e.get("index") == el.get("index")), None
                )
            elif name == "Title":
                old = page.find(el.tag)
            else:
                old = next(
                    (
                        e
                        for e in page
                        if el.get("objectID") and e.get("objectID") == el.get("objectID")
                    ),
                    None,
                )
            if name not in ("QuickStyleDef", "TagDef", "Title", "PageSettings") and not el.get(
                "objectID"
            ):
                el.set("objectID", self._new_id(f"{pid}-el"))
            if old is not None:
                page[list(page).index(old)] = el
            elif name in ("QuickStyleDef", "TagDef"):
                last = [
                    i for i, e in enumerate(page) if local(e.tag) in ("QuickStyleDef", "TagDef")
                ]
                page.insert(last[-1] + 1 if last else 0, el)
            else:
                page.append(el)
        for oe in page.iter(q("OE")):
            if not oe.get("objectID"):
                oe.set("objectID", self._new_id(f"{pid}-oe"))
        title = page.find(f"{q('Title')}/{q('OE')}/{q('T')}")
        if title is not None:
            page.set("name", title.text or "")
            self._find(pid).set("name", title.text or "")
        self._pages[pid] = tostring(page)

    # ------------------------------------------------------------------ test helpers
    def set_page(self, page_id: str, xml: str) -> None:
        """Change a page behind the tool's back (used to simulate edits)."""
        self._pages[page_id] = xml

    def stored_page(self, page_id: str) -> str:
        return self._pages[page_id]
