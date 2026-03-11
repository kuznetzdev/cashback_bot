from __future__ import annotations

import base64
import hashlib
import hmac
import os

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in environments without argon2-cffi
    PasswordHasher = None
    InvalidHashError = ValueError
    VerificationError = ValueError

from app.application.auth.passwords import PasswordHasherPort


class Argon2PasswordHasher(PasswordHasherPort):
    def __init__(self) -> None:
        self._hasher = PasswordHasher() if PasswordHasher is not None else None

    def hash_password(self, password: str) -> str:
        if self._hasher is not None:
            return self._hasher.hash(password)
        salt = os.urandom(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
        return "scrypt$16384$8$1$%s$%s" % (
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )

    def verify_password(self, password: str, password_hash: str) -> bool:
        if password_hash.startswith("scrypt$"):
            return self._verify_scrypt(password, password_hash)
        if self._hasher is None:
            return False
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False

    @staticmethod
    def _verify_scrypt(password: str, password_hash: str) -> bool:
        try:
            _, n_raw, r_raw, p_raw, salt_raw, digest_raw = password_hash.split("$", maxsplit=5)
            salt = base64.b64decode(salt_raw.encode("ascii"))
            expected = base64.b64decode(digest_raw.encode("ascii"))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n_raw),
                r=int(r_raw),
                p=int(p_raw),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)
