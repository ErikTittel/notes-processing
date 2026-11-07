"""Shared helpers for OneNote 2013 XML."""

import xml.etree.ElementTree as ET

NS = "http://schemas.microsoft.com/office/onenote/2013/onenote"
ET.register_namespace("one", NS)

# Top-level positioned content elements of a page (research R3/R4).
CONTENT_TAGS = ("Outline", "Image", "InkDrawing", "InsertedFile", "MediaFile")


def q(tag: str) -> str:
    """Qualified tag name in the OneNote namespace."""
    return f"{{{NS}}}{tag}"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def tostring(elem: ET.Element) -> str:
    return ET.tostring(elem, encoding="unicode")


def content_elements(page: ET.Element) -> list[ET.Element]:
    """Top-level content elements of a page (everything after Title), in document order."""
    return [
        child
        for child in page
        if child.tag.startswith(f"{{{NS}}}")
        and local(child.tag)
        not in {
            "TagDef",
            "QuickStyleDef",
            "XPSFile",
            "Meta",
            "MediaPlaylist",
            "MeetingInfo",
            "PageSettings",
            "Title",
        }
    ]


def oe_ids(elements: list[ET.Element]) -> list[str]:
    """objectIDs of every OE inside the given elements, in document order."""
    return [oe.get("objectID", "") for el in elements for oe in el.iter(q("OE"))]
