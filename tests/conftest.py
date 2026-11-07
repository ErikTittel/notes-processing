import pathlib

import pytest

from notes_processing.onenote.fake import FakeGateway

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def all_pages() -> dict[str, str]:
    return {
        p.stem: p.read_text(encoding="utf-8") for p in sorted((FIXTURES / "pages").glob("*.xml"))
    }


def make_gateway(**kwargs) -> FakeGateway:
    return FakeGateway(read_fixture("hierarchy_small.xml"), all_pages(), **kwargs)


@pytest.fixture
def load_fixture():
    return read_fixture


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return make_gateway()
