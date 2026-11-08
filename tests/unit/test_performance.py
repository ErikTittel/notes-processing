"""Smoke test against accidental quadratic work (toward SC-005)."""

import time

from notes_processing import runner
from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import PageStatus, Scope
from notes_processing.onenote.fake import FakeGateway
from notes_processing.onexml import NS
from notes_processing.planner import make_plan

GROUPS, SECTIONS, PAGES = 15, 12, 30


def generate():
    parts = [f'<one:Notebook xmlns:one="{NS}" name="Gross" ID="NB" path="C:\\N\\Gross">']
    pages = {}
    for g in range(GROUPS):
        parts.append(f'<one:SectionGroup name="{2010 + g}" ID="G{g}" path="C:\\N\\Gross\\{g}">')
        for s in range(SECTIONS):
            sid = f"S{g}-{s}"
            yy = 10 + g
            parts.append(
                f'<one:Section name="{yy}-{s + 1:02d}" ID="{sid}" '
                f'path="C:\\N\\Gross\\{g}\\{s}.one" lastModifiedTime="t">'
            )
            for p in range(PAGES):
                pid = f"P{g}-{s}-{p}"
                title = f"{p + 1:02d}.{s + 1:02d}.{yy}" if p < 28 else f"Notiz {p}"
                parts.append(
                    f'<one:Page ID="{pid}" name="{title}" pageLevel="1" lastModifiedTime="t"/>'
                )
                link = ""
                if p == 0 and s > 0:
                    link = (
                        f' <a href="onenote:C:\\N\\Gross\\{g}\\{s - 1}.one#x&amp;section-id='
                        f'{{L-S{g}-{s - 1}}}&amp;page-id={{L-P{g}-{s - 1}-3}}&amp;end">z</a>'
                    )
                pages[pid] = (
                    f'<one:Page xmlns:one="{NS}" ID="{pid}" name="{title}">'
                    '<one:QuickStyleDef index="0" name="PageTitle"/>'
                    '<one:QuickStyleDef index="1" name="p"/>'
                    f'<one:Title><one:OE quickStyleIndex="0" objectID="{pid}-t"><one:T>{title}'
                    "</one:T></one:OE></one:Title>"
                    '<one:Outline objectID="o"><one:Position x="36" y="86" z="0"/>'
                    '<one:Size width="400" height="40"/><one:OEChildren>'
                    f'<one:OE objectID="{pid}-1" quickStyleIndex="1"><one:T><![CDATA[Text {pid}'
                    f"{link}]]></one:T></one:OE>"
                    f'<one:OE objectID="{pid}-2" quickStyleIndex="1"><one:T>Mehr</one:T></one:OE>'
                    "</one:OEChildren></one:Outline></one:Page>"
                )
            parts.append("</one:Section>")
        parts.append("</one:SectionGroup>")
    parts.append("</one:Notebook>")
    return "".join(parts), pages


def test_full_size_notebook_runs_quickly():
    xml, pages = generate()
    gw = FakeGateway(xml, pages)
    start = time.perf_counter()
    source = parse_hierarchy(gw.hierarchy("NB", 4))
    plan, indexed = make_plan(gw, source, Scope(), "Neu", r"C:\Out")
    report = runner.run(plan, gw, indexed, progress=lambda m: None, clock=lambda: "T")
    elapsed = time.perf_counter() - start
    assert report.summary.pages == GROUPS * SECTIONS
    assert report.summary.source_pages == GROUPS * SECTIONS * PAGES
    assert all(p.status == PageStatus.VERIFIED for p in report.pages)
    assert sum(lo.status == "updated" for lo in report.links) == GROUPS * (SECTIONS - 1)
    assert elapsed < 60, elapsed
