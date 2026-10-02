"""Obsolete IDCC quarterly reconstruction certification.

HAP no longer clears statement bodies or reconstructs them from SEC. This
script refuses to run so it cannot overwrite historical outputs. See
backend/STATEMENT_FILL_SUPERSESSION.md.
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
