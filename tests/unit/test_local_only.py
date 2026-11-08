"""Constitution I/II, FR-015: no network libraries; only the gateway imports comtypes."""

import ast
import pathlib

SRC = pathlib.Path(__file__).parents[2] / "src" / "notes_processing"
NETWORK = {
    "socket",
    "http",
    "urllib.request",
    "urllib3",
    "requests",
    "httpx",
    "ssl",
    "ftplib",
    "smtplib",
    "aiohttp",
    "websocket",
    "xmlrpc",
    "telnetlib",
    "poplib",
    "imaplib",
}


def imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


def test_no_network_imports():
    for path in SRC.rglob("*.py"):
        for name in imports(path):
            assert not any(name == n or name.startswith(n + ".") for n in NETWORK), (path, name)


def test_only_gateway_imports_comtypes():
    users = {
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if any(n.split(".")[0] == "comtypes" for n in imports(p))
    }
    assert users == {"onenote/gateway.py"}
