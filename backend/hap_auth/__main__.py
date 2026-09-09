"""python -m hap_auth generate-password-hash | generate-session-secret"""

from __future__ import annotations

import argparse
import getpass
import sys

from hap_auth import hash_password, new_session_secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HAP auth helpers. Never commit real secrets.")
    parser.add_argument(
        "command",
        choices=("generate-password-hash", "generate-session-secret"),
    )
    args = parser.parse_args(argv)

    if args.command == "generate-session-secret":
        print(new_session_secret())
        return 0

    password = getpass.getpass("Password (input hidden): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
