from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExternalIdentityContext:
    provider: str
    provider_user_id: str
    provider_username: str | None = None
    provider_display_name: str | None = None


@dataclass(slots=True)
class LocalRegistrationCommand:
    username: str
    password: str
    display_name: str | None = None
    email: str | None = None


@dataclass(slots=True)
class LocalAuthenticationCommand:
    username: str
    password: str
