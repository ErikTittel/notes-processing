"""Typed OneNote errors. Deliberately free of any comtypes import."""


class OneNoteError(Exception):
    """Base class for every OneNote-related failure."""


class OneNoteUnavailable(OneNoteError):
    """OneNote is not running, not installed or not responding."""


class OneNoteCallFailed(OneNoteError):
    """A COM call failed for any other reason."""

    def __init__(self, method: str, hresult: int | None = None, message: str = "") -> None:
        self.method = method
        self.hresult = hresult
        code = f" (HRESULT 0x{hresult & 0xFFFFFFFF:08X})" if hresult is not None else ""
        super().__init__(f"{method} fehlgeschlagen{code}{': ' + message if message else ''}")


class WriteOutsideTarget(OneNoteError):
    """A write was attempted on an object that is not inside the target notebook."""


class NotFound(OneNoteError):
    """A notebook, section group or section with the given name does not exist."""
