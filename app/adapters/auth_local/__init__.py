"""Local authentication adapters."""

from app.adapters.auth_local.passwords import Argon2PasswordHasher

__all__ = ["Argon2PasswordHasher"]
