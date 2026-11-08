"""Immutable data model (see specs/001-merge-sections-to-pages/data-model.md).

All collection fields are tuples so instances stay hashable and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# --------------------------------------------------------------------------- enums


class TitleStatus(StrEnum):
    UNCHANGED = "unchanged"
    CORRECTED = "corrected"
    COULD_NOT_CORRECT = "could_not_correct"
    OUT_OF_ORDER = "out_of_order"
    UNTITLED = "untitled"
    NO_SECTION_MONTH = "no_section_month"


class LinkKind(StrEnum):
    TRANSFERRED_PAGE = "transferred_page"
    TRANSFERRED_PARAGRAPH = "transferred_paragraph"
    TRANSFERRED_SECTION = "transferred_section"
    TRANSFERRED_GROUP = "transferred_group"
    OUTSIDE_TRANSFER = "outside_transfer"
    TARGET_NOT_FOUND = "target_not_found"
    EXTERNAL = "external"

    @property
    def transferred(self) -> bool:
        return self.value.startswith("transferred_")


class PageStatus(StrEnum):
    PLANNED = "planned"
    CREATED = "created"
    CONTENT_WRITTEN = "content_written"
    LINKS_UPDATED = "links_updated"
    VERIFIED = "verified"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    VERIFICATION_FAILED = "verification_failed"
    SKIPPED = "skipped"
    NOT_STARTED = "not_started"


UNTITLED_HEADING = "(Untitled page)"

# --------------------------------------------------------------------------- source side


@dataclass(frozen=True)
class SourcePage:
    id: str
    title: str
    level: int
    last_modified: str
    link_page_guid: str | None = None


@dataclass(frozen=True)
class SourceSection:
    id: str
    name: str
    path: str
    last_modified: str
    locked: bool
    pages: tuple[SourcePage, ...] = ()
    link_section_guid: str | None = None


@dataclass(frozen=True)
class SourceGroup:
    id: str
    name: str
    path: str
    sections: tuple[SourceSection, ...] = ()


@dataclass(frozen=True)
class IgnoredItem:
    kind: str  # "loose_section" | "nested_group"
    id: str
    name: str
    path: str
    parent: str = ""  # name of the top-level group it sits in ("" = notebook root)


@dataclass(frozen=True)
class SourceNotebook:
    id: str
    name: str
    path: str
    groups: tuple[SourceGroup, ...] = ()
    ignored: tuple[IgnoredItem, ...] = ()


# --------------------------------------------------------------------------- planning


@dataclass(frozen=True)
class Scope:
    kind: str = "all"  # "all" | "group" | "section"
    group: str | None = None
    section: str | None = None

    def __str__(self) -> str:
        if self.kind == "group":
            return f"group:{self.group}"
        if self.kind == "section":
            return f"section:{self.group}/{self.section}"
        return "all"

    @classmethod
    def build(cls, group: str | None, section: str | None) -> Scope:
        if section is not None:
            return cls("section", group, section)
        if group is not None:
            return cls("group", group)
        return cls()


@dataclass(frozen=True)
class AttentionItem:
    kind: str
    message: str
    names: tuple[str, ...] = ()
    source_id: str = ""


@dataclass(frozen=True)
class TitleDecision:
    page_id: str
    original: str
    heading: str
    status: TitleStatus
    section_name: str = ""


@dataclass(frozen=True)
class LinkRef:
    source_page_id: str
    text: str
    href: str
    kind: LinkKind
    target_source_id: str | None = None


@dataclass(frozen=True)
class PlannedPage:
    source_section_id: str
    source_section_name: str
    title: str
    blocks: tuple[TitleDecision, ...]
    source_page_count: int


@dataclass(frozen=True)
class PlannedSection:
    source_group_id: str
    name: str
    pages: tuple[PlannedPage, ...]


@dataclass(frozen=True)
class Plan:
    source_notebook: str
    source_notebook_id: str
    target_notebook_name: str
    target_folder: str
    scope: Scope
    sections: tuple[PlannedSection, ...]
    title_decisions: tuple[TitleDecision, ...] = ()
    links: tuple[LinkRef, ...] = ()
    attention: tuple[AttentionItem, ...] = ()
    fingerprint: str = ""

    @property
    def pages(self) -> tuple[PlannedPage, ...]:
        return tuple(p for s in self.sections for p in s.pages)


# --------------------------------------------------------------------------- applying


@dataclass(frozen=True)
class PageOutcome:
    source_section_id: str
    source_section_name: str
    target_section_name: str
    title: str
    status: PageStatus
    message: str = ""
    target_page_id: str = ""


@dataclass(frozen=True)
class LinkOutcome:
    source_page_id: str
    text: str
    href: str
    kind: LinkKind
    status: str  # "updated" | "kept"
    new_href: str = ""
    reason: str = ""


@dataclass(frozen=True)
class ContentIssue:
    source_page_id: str
    source_page_title: str
    source_section_name: str
    element: str
    message: str


@dataclass(frozen=True)
class Mismatch:
    source_page_id: str
    source_page_title: str
    kind: str  # "heading" | "missing" | "changed" | "extra"
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    target_page_id: str
    target_page_title: str
    source_section_id: str
    ok: bool
    mismatches: tuple[Mismatch, ...] = ()


@dataclass(frozen=True)
class Summary:
    sections: int = 0
    pages: int = 0
    source_pages: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    incomplete: int = 0
    not_started: int = 0
    verification_failed: int = 0


@dataclass(frozen=True)
class RunReport:
    plan_fingerprint: str
    started: str
    finished: str
    target_notebook_id: str
    pages: tuple[PageOutcome, ...] = ()
    title_decisions: tuple[TitleDecision, ...] = ()
    links: tuple[LinkOutcome, ...] = ()
    content_issues: tuple[ContentIssue, ...] = ()
    verification: tuple[VerificationResult, ...] = ()
    summary: Summary = field(default_factory=Summary)
    stopped: bool = False
    stop_reason: str = ""
