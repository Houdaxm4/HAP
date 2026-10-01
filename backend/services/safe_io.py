"""Small safety helpers for storage paths and JSON persistence.

No analysis logic belongs here.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

# Analysis IDs are UUID4 strings today. Accept any short, filesystem-safe token so
# existing fixtures keep working, but never anything that could escape a directory.
_ANALYSIS_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class InvalidAnalysisIdError(ValueError):
    """Raised when an analysis ID is not a safe single path component."""


def validate_analysis_id(analysis_id: str) -> str:
    """Return ``analysis_id`` if it is safe to use as a directory/file name."""
    if not isinstance(analysis_id, str) or not _ANALYSIS_ID_RE.fullmatch(analysis_id):
        raise InvalidAnalysisIdError(f"Invalid analysis id: {analysis_id!r}")
    return analysis_id


def write_json_atomic(path: Path, payload: Any, *, indent: int | None = 2, default: Any = None) -> None:
    """Write JSON so readers never see a half-written file.

    Writes to a temp file in the same directory, then ``os.replace`` (atomic on
    POSIX and Windows when source and target share a volume).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=indent, default=default)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
