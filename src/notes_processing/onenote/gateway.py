"""OneNoteGateway: the ONLY module that talks to OneNote through COM (constitution II).

``comtypes`` is imported lazily inside ``__init__`` so unit tests never load it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import OneNoteCallFailed, OneNoteUnavailable, WriteOutsideTarget

TYPELIB_GUID = "{0EA692EE-BB50-4E3C-AEF0-356D91732725}"

HS_NOTEBOOKS = 2
HS_PAGES = 4
XS_2013 = 2
PI_BASIC = 0
PI_BINARY_DATA_FILE_TYPE = 5
CFT_NOTEBOOK = 1
CFT_FOLDER = 2
CFT_SECTION = 3
NPS_BLANK_PAGE_WITH_TITLE = 1
SL_DEFAULT_NOTEBOOK_FOLDER = 2

_UNAVAILABLE_HRESULTS = {
    0x8001010A,  # RPC_E_SERVERCALL_RETRYLATER
    0x80010108,  # RPC_E_DISCONNECTED
    0x800706BA,  # RPC_S_SERVER_UNAVAILABLE
    0x800706BE,  # RPC_S_CALL_FAILED
}


class OneNoteGateway:
    def __init__(self) -> None:
        try:
            import comtypes.client
            from comtypes import COMError

            self._com_error: type[Exception] = COMError
            tlb = comtypes.client.GetModule((TYPELIB_GUID, 1, 1))
            self._app: Any = comtypes.client.CreateObject(
                "OneNote.Application", interface=tlb.IApplication
            )
        except Exception as exc:
            raise OneNoteUnavailable(f"OneNote ist nicht verfügbar: {exc}") from exc
        self.target_notebook_id: str | None = None
        self._target_ids: set[str] = set()

    # ------------------------------------------------------------------ plumbing
    def _call(self, method: str, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except self._com_error as exc:
            hresult = (getattr(exc, "hresult", 0) or 0) & 0xFFFFFFFF
            if hresult in _UNAVAILABLE_HRESULTS:
                raise OneNoteUnavailable(f"{method}: OneNote antwortet nicht") from exc
            raise OneNoteCallFailed(method, hresult, str(exc)) from exc
        except OSError as exc:
            raise OneNoteUnavailable(f"{method}: {exc}") from exc

    def _guard(self, object_id: str) -> None:
        if self.target_notebook_id is None or object_id not in self._target_ids:
            raise WriteOutsideTarget(
                f"Schreibzugriff auf {object_id!r} außerhalb des Zielnotizbuchs verweigert"
            )

    # ------------------------------------------------------------------ reads
    def hierarchy(self, start_id: str, scope: int) -> str:
        return self._call("GetHierarchy", lambda: self._app.GetHierarchy(start_id, scope, XS_2013))

    def page_xml(self, page_id: str, binary: bool = True) -> str:
        info = PI_BINARY_DATA_FILE_TYPE if binary else PI_BASIC
        return self._call(
            "GetPageContent", lambda: self._app.GetPageContent(page_id, info, XS_2013)
        )

    def link_to(self, hierarchy_id: str, object_id: str = "") -> str:
        return self._call(
            "GetHyperlinkToObject", lambda: self._app.GetHyperlinkToObject(hierarchy_id, object_id)
        )

    def special_folder(self) -> str:
        return self._call(
            "GetSpecialLocation", lambda: self._app.GetSpecialLocation(SL_DEFAULT_NOTEBOOK_FOLDER)
        )

    def notebook_names(self) -> list[str]:
        from ..hierarchy import notebooks

        return list(notebooks(self.hierarchy("", HS_NOTEBOOKS)))

    # ------------------------------------------------------------------ writes
    def create_notebook(self, folder: str, name: str) -> str:
        if self.target_notebook_id is not None:
            raise WriteOutsideTarget("Das Zielnotizbuch wurde bereits angelegt")
        path = f"{folder.rstrip('\\/')}\\{name}"
        nb_id = self._call("OpenHierarchy", lambda: self._app.OpenHierarchy(path, "", CFT_NOTEBOOK))
        self.target_notebook_id = nb_id
        self._target_ids.add(nb_id)
        return nb_id

    def create_section(self, name: str, parent_id: str | None = None) -> str:
        """New section in the target notebook (or in a section group created by this gateway)."""
        if self.target_notebook_id is None:
            raise WriteOutsideTarget("Abschnitt vor dem Zielnotizbuch angelegt")
        parent = parent_id or self.target_notebook_id
        self._guard(parent)
        sid = self._call(
            "OpenHierarchy", lambda: self._app.OpenHierarchy(f"{name}.one", parent, CFT_SECTION)
        )
        self._target_ids.add(sid)
        return sid

    def create_section_group(self, name: str) -> str:
        """New section group in the target notebook (used to build test notebooks)."""
        if self.target_notebook_id is None:
            raise WriteOutsideTarget("Abschnittsgruppe vor dem Zielnotizbuch angelegt")
        nb_id = self.target_notebook_id
        gid = self._call("OpenHierarchy", lambda: self._app.OpenHierarchy(name, nb_id, CFT_FOLDER))
        self._target_ids.add(gid)
        return gid

    def create_page(self, section_id: str) -> str:
        self._guard(section_id)
        pid = self._call(
            "CreateNewPage", lambda: self._app.CreateNewPage(section_id, NPS_BLANK_PAGE_WITH_TITLE)
        )
        self._target_ids.add(pid)
        return pid

    def update_page(self, xml: str) -> None:
        from ..onexml import parse

        self._guard(parse(xml).get("ID", ""))
        self._call("UpdatePageContent", lambda: self._app.UpdatePageContent(xml, 0, XS_2013, False))
