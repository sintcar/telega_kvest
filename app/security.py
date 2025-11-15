"""Security helpers for password hashing and verification."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import ClassVar


_DEFAULT_ALGORITHM = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 390_000
_SALT_BYTES = 16


@dataclass(frozen=True)
class PasswordHash:
    """Represents a hashed password string."""

    algorithm: str
    iterations: int
    salt: bytes
    digest: bytes

    SEPARATOR: ClassVar[str] = "$"

    @classmethod
    def parse(cls, value: str) -> "PasswordHash":
        try:
            algorithm, iterations, salt_b64, digest_b64 = value.split(cls.SEPARATOR)
        except ValueError as exc:
            raise ValueError("Invalid password hash format") from exc

        if algorithm != _DEFAULT_ALGORITHM:
            raise ValueError("Unsupported password hash algorithm")

        try:
            iterations_int = int(iterations)
        except ValueError as exc:
            raise ValueError("Invalid hash iterations value") from exc

        try:
            salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
            digest = base64.urlsafe_b64decode(digest_b64.encode("utf-8"))
        except (base64.binascii.Error, ValueError) as exc:
            raise ValueError("Invalid hash encoding") from exc

        return cls(
            algorithm=algorithm,
            iterations=iterations_int,
            salt=salt,
            digest=digest,
        )

    def serialize(self) -> str:
        salt_b64 = base64.urlsafe_b64encode(self.salt).decode("utf-8")
        digest_b64 = base64.urlsafe_b64encode(self.digest).decode("utf-8")
        return self.SEPARATOR.join(
            [
                self.algorithm,
                str(self.iterations),
                salt_b64,
                digest_b64,
            ]
        )


def hash_password(password: str) -> str:
    """Generate a PBKDF2-based hash for the given password."""
    if not password:
        raise ValueError("Password must not be empty")

    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _DEFAULT_ITERATIONS
    )
    return PasswordHash(
        algorithm=_DEFAULT_ALGORITHM,
        iterations=_DEFAULT_ITERATIONS,
        salt=salt,
        digest=digest,
    ).serialize()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify the provided password against a stored PBKDF2 hash."""
    if not stored_hash:
        return False

    try:
        parsed = PasswordHash.parse(stored_hash)
    except ValueError:
        return False

    comparison_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        parsed.salt,
        parsed.iterations,
    )
    return hmac.compare_digest(comparison_digest, parsed.digest)
