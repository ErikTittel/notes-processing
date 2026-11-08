"""Block layout of former pages on the merged page (FR-006a, research R4). Pure."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

HEADING_X = 36.0


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects(self, other: Box) -> bool:
        return (
            self.x < other.x + other.width
            and other.x < self.x + self.width
            and self.y < other.bottom
            and other.y < self.bottom
        )


@dataclass(frozen=True)
class BlockInput:
    elements: tuple[Box, ...]


@dataclass(frozen=True)
class BlockPlacement:
    top: float
    heading: Box
    elements: tuple[Box, ...]  # placed boxes, same order as the input
    bottom: float

    @property
    def boxes(self) -> tuple[Box, ...]:
        return (self.heading, *self.elements)


def layout_blocks(
    blocks: Sequence[BlockInput],
    title_bottom: float,
    heading_height: float,
    gap: float = 36.0,
    margin: float = 6.0,
    heading_width: float = 400.0,
) -> list[BlockPlacement]:
    """Stack blocks top to bottom; each keeps its elements' relative positions."""
    placements = []
    top = title_bottom
    for block in blocks:
        heading = Box(HEADING_X, top, heading_width, heading_height)
        content_top = top + heading_height
        if block.elements:
            min_y = min(b.y for b in block.elements)
            placed = tuple(
                Box(b.x, content_top + (b.y - min_y), b.width, b.height) for b in block.elements
            )
            bottom = max(heading.bottom, *(b.bottom for b in placed)) + margin
        else:
            placed = ()
            bottom = heading.bottom + margin
        placements.append(BlockPlacement(top, heading, placed, bottom))
        top = bottom + gap
    return placements


def find_overlaps(placements: Sequence[BlockPlacement]) -> list[tuple[int, int]]:
    """Pairs of block indices where a box of one block intersects a box of another."""
    out = []
    for i, a in enumerate(placements):
        for j in range(i + 1, len(placements)):
            b = placements[j]
            if any(x.intersects(y) for x in a.boxes for y in b.boxes):
                out.append((i, j))
    return out
