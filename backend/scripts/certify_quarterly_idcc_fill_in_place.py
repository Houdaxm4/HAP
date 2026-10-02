"""Obsolete IDCC fill-in-place certification.

HAP no longer fills or reconstructs financial statements. This script refuses
to run so the retired certification cannot be re-executed. Historical artifacts
are unchanged; see backend/STATEMENT_FILL_SUPERSESSION.md.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "REFUSED: statement fill/reconstruction certification is superseded. "
        "See backend/STATEMENT_FILL_SUPERSESSION.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
