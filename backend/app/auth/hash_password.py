"""Purpose: Print an argon2 hash for the interviewer password.

Public API:
- main
"""

import argparse

from app.auth.passwords import hash_password


def main() -> None:
    """Hash a password from --password or an interactive prompt."""
    parser = argparse.ArgumentParser(description="Hash the interviewer password.")
    parser.add_argument("--password", help="Password to hash. Prefer the prompt so it stays out of shell history.")
    args = parser.parse_args()
    password = args.password
    if not password:
        import getpass

        password = getpass.getpass("Password: ")
    print(hash_password(password))


if __name__ == "__main__":
    main()
