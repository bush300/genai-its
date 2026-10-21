# creates a user account instead of adding one to Firestore by hand.
# Writes users/{username} with a bcrypt password_hash and a role.
#
#   python 1.5_security/create_account.py --username alice --role Student
#
# Password is a hidden prompt, not a command-line arg (so it's not in shell
# history). Needs Firebase Admin creds available, e.g.
#   set GOOGLE_APPLICATION_CREDENTIALS=path\to\service-account.json

from __future__ import annotations

import argparse
import getpass
import sys

import bcrypt
import firebase_admin
from firebase_admin import firestore

VALID_ROLES = {"Student", "Teacher"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_account(username: str, password: str, role: str, overwrite: bool = False) -> None:
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
    if not username.strip():
        raise ValueError("username must not be empty")
    if not username.isalnum():
        # student_performance doc IDs are f"{student_id}_{subject}_{week}", and a
        # couple of pages find a student's own records by prefix-matching that ID.
        # An underscore (or any separator) in the username lets one username be a
        # prefix of another's doc ID, e.g. "alice" would match "alice_smith"'s
        # records too. Letters/digits only closes that off.
        raise ValueError("username must contain only letters and digits (no underscores, spaces, etc.)")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    db = firestore.client()

    doc_ref = db.collection("users").document(username.strip())

    if doc_ref.get().exists and not overwrite:
        raise RuntimeError(
            f"An account for '{username}' already exists. Pass --overwrite to replace it."
        )

    doc_ref.set({
        "password_hash": hash_password(password),
        "role": role,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a CyberNexa user account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing account with the same username.",
    )
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    try:
        create_account(args.username, password, args.role, overwrite=args.overwrite)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Account created: {args.username} ({args.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
