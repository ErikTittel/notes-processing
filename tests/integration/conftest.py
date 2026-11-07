"""Throwaway OneNote notebooks for integration tests (marked `onenote`).

Notebooks are created under %TEMP%\\notes-processing-it\\<timestamp>\\ and are NEVER deleted
automatically (constitution III). Their paths are printed at the end of the session.
"""

from __future__ import annotations

import base64
import html
import re
import struct
import tempfile
import time
import wave
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from notes_processing.onexml import NS, parse, q, tostring

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
CREATED: list[str] = []


@pytest.fixture(scope="session")
def it_folder():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(tempfile.gettempdir()) / "notes-processing-it" / stamp
    folder.mkdir(parents=True)
    yield folder
    (folder / "created_notebooks.txt").write_text("\n".join(CREATED), encoding="utf-8")
    print("\nIntegrationstests haben diese Notizbücher angelegt (bitte in OneNote schließen):")
    for path in CREATED:
        print(f"  {path}")


@pytest.fixture(scope="session")
def attachments(it_folder):
    doc = it_folder / "anhang.txt"
    doc.write_text("Inhalt der eingebetteten Datei\n", encoding="utf-8")
    audio = it_folder / "ton.wav"
    with wave.open(str(audio), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", 0) for _ in range(800)))
    base64.b64decode(PNG)  # sanity
    return {"file": str(doc), "audio": str(audio)}


def outline(x: float, y: float, w: float, h: float, paragraphs: list[str]) -> str:
    oes = "".join(f"<one:OE><one:T><![CDATA[{p}]]></one:T></one:OE>" for p in paragraphs)
    return (
        f'<one:Outline><one:Position x="{x}" y="{y}" z="0"/>'
        f'<one:Size width="{w}" height="{h}" isSetByUser="true"/>'
        f"<one:OEChildren>{oes}</one:OEChildren></one:Outline>"
    )


def image(x: float, y: float) -> str:
    return (
        f'<one:Image format="png"><one:Position x="{x}" y="{y}" z="1"/>'
        f'<one:Size width="40" height="40"/><one:Data>{PNG}</one:Data></one:Image>'
    )


def inserted_file(path: str, x: float, y: float) -> str:
    return (
        f'<one:InsertedFile pathSource="{html.escape(path)}" preferredName="anhang.txt">'
        f'<one:Position x="{x}" y="{y}" z="2"/><one:Size width="60" height="60"/></one:InsertedFile>'
    )


def media_file(path: str, x: float, y: float) -> str:
    return (
        f'<one:MediaFile pathSource="{html.escape(path)}" preferredName="ton.wav">'
        f'<one:Position x="{x}" y="{y}" z="3"/><one:Size width="60" height="60"/></one:MediaFile>'
    )


def link(target: str, text: str) -> str:
    """Placeholder resolved to the real OneNote link once all pages exist."""
    return f'<a href="{{{{link:{target}}}}}">{text}</a>'


_LINK = re.compile(r"\{\{link:([^}]*)\}\}")


def build_notebook(gw, folder: Path, name: str, spec: dict) -> dict[str, str]:
    """Create a notebook from `spec` = {group: {section: [(title, level, [element xml])]}}.

    Returns "group/section/title" -> page ID (and "group/section" -> section ID, "group" -> ID).
    """
    nb_id = gw.create_notebook(str(folder), name)
    CREATED.append(str(folder / name))
    ids: dict[str, str] = {"": nb_id}
    contents: list[tuple[str, int, str, list[str]]] = []
    for group, sections in spec.items():
        gid = ids[group] = gw.create_section_group(group)
        for section, pages in sections.items():
            sid = ids[f"{group}/{section}"] = gw.create_section(section, gid)
            for title, level, elements in pages:
                pid = ids[f"{group}/{section}/{title}"] = gw.create_page(sid)
                contents.append((pid, level, title, elements))
    for pid, level, title, elements in contents:
        page = parse(gw.page_xml(pid))
        page.set("pageLevel", str(level))
        t = page.find(f"{q('Title')}/{q('OE')}/{q('T')}")
        t.text = html.escape(title, quote=False)
        for el in elements:
            el = _LINK.sub(lambda m: html.escape(_resolve(gw, ids, m.group(1)), quote=True), el)
            page.append(ET.fromstring(f'<w xmlns:one="{NS}">{el}</w>')[0])
        gw.update_page(tostring(page))
    return ids


def settled_hierarchy(gw, notebook_id: str, quiet_seconds: int = 4, timeout: int = 30):
    """Hierarchy of a freshly built notebook once OneNote has stopped saving it.

    OneNote re-saves new sections a few seconds after the last write (bumping their
    lastModifiedTime), so a snapshot taken right away is not a stable "before" state.
    """
    from notes_processing.hierarchy import parse_hierarchy
    from notes_processing.onenote.gateway import HS_PAGES

    last = parse_hierarchy(gw.hierarchy(notebook_id, HS_PAGES))
    quiet = 0
    for _ in range(timeout):
        time.sleep(1)
        current = parse_hierarchy(gw.hierarchy(notebook_id, HS_PAGES))
        quiet = quiet + 1 if current == last else 0
        last = current
        if quiet >= quiet_seconds:
            return current
    raise AssertionError("OneNote hat das Testnotizbuch nicht fertig gespeichert")


def _resolve(gw, ids: dict[str, str], target: str) -> str:
    if target.startswith("http"):
        return target
    return gw.link_to(ids[target])
