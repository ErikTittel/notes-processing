"""Embedded online videos (research R13). Pure.

OneNote's page XML shows an embedded online video (for example from YouTube) only as an
ordinary `one:Image` holding the preview picture: there is no video address and no marker,
and writing a video address never embeds a video again (only pasting in OneNote does). The
preview is therefore recognised by the shape OneNote gives it, and the video address is taken
from the video links on the same page.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from .links import ANCHOR
from .onexml import content_elements, local, q

# Sizes (in points) OneNote gives a newly embedded online video, unless the user resized it.
PREVIEW_SIZES = ((267.0, 150.0), (360.0, 202.5))
# Alternative text OneNote (German UI) gives an embedded web video.
PREVIEW_ALT = "Webinhalt"
VIDEO_URL = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch|shorts/|embed/|live/)|youtu\.be/|vimeo\.com/)",
    re.IGNORECASE,
)


def is_video_preview(image: ET.Element) -> bool:
    """True if `image` looks like the preview picture of an embedded online video."""
    if local(image.tag) != "Image":
        return False
    if image.get("alt", "").startswith(PREVIEW_ALT):
        return True
    size = image.find(q("Size"))
    if size is None or size.get("isSetByUser", "false").lower() == "true":
        return False
    try:
        width, height = float(size.get("width", "0")), float(size.get("height", "0"))
    except ValueError:
        return False
    return any(abs(width - w) < 0.5 and abs(height - h) < 0.5 for w, h in PREVIEW_SIZES)


def find_video_previews(page: ET.Element) -> list[tuple[ET.Element, str | None]]:
    """Video previews of a page in document order, each with its video address (or None).

    Each preview gets the last video link before it on the page; if there is none, the first
    one after it. OneNote embeds a video right below the pasted link, so this is the link
    the video was made from.
    """
    order: list[tuple[str, ET.Element | str]] = []
    for el in content_elements(page):
        for node in el.iter():
            if node.tag == q("T"):
                for m in ANCHOR.finditer(node.text or ""):
                    href = html.unescape(m.group(2))
                    if VIDEO_URL.match(href):
                        order.append(("link", href))
            elif is_video_preview(node):
                order.append(("preview", node))
    links = [(i, v) for i, (kind, v) in enumerate(order) if kind == "link"]
    out: list[tuple[ET.Element, str | None]] = []
    for i, (kind, value) in enumerate(order):
        if kind != "preview":
            continue
        before = [href for j, href in links if j < i]
        after = [href for j, href in links if j > i]
        url = before[-1] if before else (after[0] if after else None)
        out.append((value, url))  # type: ignore[arg-type]
    return out


def preview_message(url: str | None, linked: bool) -> str:
    """German text for plan and report."""
    if url is None:
        return (
            "Eingebettetes Video (vermutlich): nur das Vorschaubild wird übertragen; "
            "keine Video-Adresse auf der Seite gefunden"
        )
    action = "mit dem Video verlinkt" if linked else "behält seinen bisherigen Link"
    return (
        f"Eingebettetes Video (vermutlich): nur das Vorschaubild wird übertragen und "
        f"{action}. Zum Wiederherstellen den Link auf der neuen Seite einfügen: {url}"
    )
