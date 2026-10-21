# only testing validation + hashing here, those run before Firestore is
# ever touched so there's nothing to mock

from __future__ import annotations

import bcrypt
import pytest

from create_account import create_account, hash_password


def test_hash_password_round_trips_with_bcrypt() -> None:
    hashed = hash_password("correct horse battery staple")

    assert bcrypt.checkpw(b"correct horse battery staple", hashed.encode("utf-8"))
    assert not bcrypt.checkpw(b"wrong password", hashed.encode("utf-8"))


def test_create_account_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="role"):
        create_account("alice", "a-long-enough-password", "Admin")


def test_create_account_rejects_empty_username() -> None:
    with pytest.raises(ValueError, match="username"):
        create_account("   ", "a-long-enough-password", "Student")


def test_create_account_rejects_short_password() -> None:
    with pytest.raises(ValueError, match="password"):
        create_account("alice", "short", "Student")
