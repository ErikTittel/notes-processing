import dataclasses
import hashlib
import json

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope
from notes_processing.planner import make_plan
from notes_processing.report import plan_to_json, to_jsonable
from tests.conftest import make_gateway, read_fixture


def build(xml=None):
    gw = make_gateway()
    source = parse_hierarchy(xml or read_fixture("hierarchy_small.xml"))
    return make_plan(gw, source, Scope(), "Neu", r"C:\Out")


def test_byte_identical_json():
    assert plan_to_json(build()[0]) == plan_to_json(build()[0])


def test_last_modified_changes_fingerprint():
    a = build()[0]
    xml = read_fixture("hierarchy_small.xml").replace(
        'ID="P8" name="Kosten" pageLevel="1" lastModifiedTime="2023-06-02T10:00:00.000Z"',
        'ID="P8" name="Kosten" pageLevel="1" lastModifiedTime="2024-01-01T10:00:00.000Z"',
    )
    b = build(xml)[0]
    assert dataclasses.replace(a, fingerprint="") == dataclasses.replace(b, fingerprint="")
    assert a.fingerprint != b.fingerprint


def test_fingerprint_definition():
    plan, source = build()
    body = to_jsonable(dataclasses.replace(plan, fingerprint=""))
    modified = [
        [s.id, s.last_modified, [[p.id, p.last_modified] for p in s.pages]]
        for g in source.groups
        for s in g.sections
    ]
    canonical = json.dumps(
        [body, modified], sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert plan.fingerprint == hashlib.sha256(canonical.encode()).hexdigest()
    assert len(plan.fingerprint) == 64
