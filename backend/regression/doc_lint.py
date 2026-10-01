"""Quality checks for generated Word deliverables (text only; no recomputation)."""

from __future__ import annotations

import collections
import re
from pathlib import Path

RECOMMENDATION_RE = re.compile(r"^Recommendation:\s+\S", re.I)
PLACEHOLDERS = ("CRF as-of", "{{", "None%")
BOILERPLATE = ("trademarks, service marks", "indicate by check mark", "exact name of registrant")
IDENTICAL_RE = re.compile(r"([+-]?0\.0%) \((\$[\d,.]+M?) vs\. (\$[\d,.]+M?)\)")


def paragraphs(path: Path) -> list[str]:
    from docx import Document

    return [p.text.strip() for p in Document(str(path)).paragraphs if p.text.strip()]


def lint_text(lines: list[str], kind: str) -> list[str]:
    """kind: 'annual' | 'new_company' | 'quarterly'. Returns human-readable problems."""
    problems: list[str] = []
    if kind in {"annual", "new_company"} and not any(RECOMMENDATION_RE.match(line) for line in lines):
        problems.append("No 'Recommendation:' line in the document.")
    repeated = [t for t, n in collections.Counter(lines).items() if n > 1 and len(t) > 30]
    problems += [f"Repeated line: {t[:80]}" for t in repeated]
    for line in lines:
        if any(p in line for p in PLACEHOLDERS) or re.search(r"nan", line):
            problems.append(f"Placeholder text: {line[:80]}")
        if any(b in line.lower() for b in BOILERPLATE):
            problems.append(f"Filing boilerplate used as content: {line[:80]}")
        match = IDENTICAL_RE.search(line)
        if match and match.group(2) == match.group(3):
            problems.append(f"Identical periods shown as a comparison: {line[:80]}")
        if "n/a vs. n/a" in line:
            problems.append(f"Empty comparison: {line[:80]}")
    return problems


def lint_docx(path: Path, kind: str) -> list[str]:
    return lint_text(paragraphs(path), kind)
