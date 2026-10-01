"""Golden-case regression harness.

Replays HAP's deterministic analysis (engine + final recommendation) from saved inputs and compares
the result with an approved baseline. Free, offline, takes seconds. Run it before accepting any change
to scoring rules or analysis code:  python -m regression check
"""
