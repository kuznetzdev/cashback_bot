from __future__ import annotations

import pytest

from app.adapters.auth_local import Argon2PasswordHasher
from app.application.auth.models import (
    ExternalIdentityContext,
    LocalAuthenticationCommand,
    LocalRegistrationCommand,
)
from app.application.auth.use_cases import (
    AuthenticateExternalIdentityUseCase,
    AuthenticateLocalUserUseCase,
    LinkExternalIdentityUseCase,
    RegisterLocalUserUseCase,
    UnlinkExternalIdentityUseCase,
)
from app.domain.errors import ValidationError


@pytest.mark.asyncio
async def test_register_and_login_local_user(uow_factory) -> None:
    hasher = Argon2PasswordHasher()
    register = RegisterLocalUserUseCase(uow_factory, hasher, default_language="ru")
    login = AuthenticateLocalUserUseCase(uow_factory, hasher)

    user = await register.execute(
        LocalRegistrationCommand(
            username="demo_user",
            password="strongpass123",
            display_name="Demo User",
            email="demo@example.com",
        )
    )
    authenticated = await login.execute(
        LocalAuthenticationCommand(username="demo_user", password="strongpass123")
    )

    assert authenticated.id == user.id
    assert authenticated.display_name == "Demo User"


@pytest.mark.asyncio
async def test_duplicate_username_is_rejected(uow_factory) -> None:
    hasher = Argon2PasswordHasher()
    register = RegisterLocalUserUseCase(uow_factory, hasher, default_language="ru")
    await register.execute(LocalRegistrationCommand(username="demo_user", password="strongpass123"))

    with pytest.raises(ValidationError) as error:
        await register.execute(LocalRegistrationCommand(username="demo_user", password="anotherpass123"))
    assert error.value.message_key == "errors.username_taken"


@pytest.mark.asyncio
async def test_wrong_password_is_rejected(uow_factory) -> None:
    hasher = Argon2PasswordHasher()
    register = RegisterLocalUserUseCase(uow_factory, hasher, default_language="ru")
    login = AuthenticateLocalUserUseCase(uow_factory, hasher)
    await register.execute(LocalRegistrationCommand(username="demo_user", password="strongpass123"))

    with pytest.raises(ValidationError) as error:
        await login.execute(LocalAuthenticationCommand(username="demo_user", password="wrongpass"))
    assert error.value.message_key == "errors.invalid_credentials"


@pytest.mark.asyncio
async def test_external_identity_link_conflict_is_rejected(uow_factory) -> None:
    hasher = Argon2PasswordHasher()
    register = RegisterLocalUserUseCase(uow_factory, hasher, default_language="ru")
    link = LinkExternalIdentityUseCase(uow_factory)

    user_a = await register.execute(LocalRegistrationCommand(username="user_a", password="strongpass123"))
    user_b = await register.execute(LocalRegistrationCommand(username="user_b", password="strongpass123"))
    identity = ExternalIdentityContext(
        provider="telegram", provider_user_id="42", provider_username="tg_user"
    )
    await link.execute(user_id=user_a.id, identity=identity)

    with pytest.raises(ValidationError) as error:
        await link.execute(user_id=user_b.id, identity=identity)
    assert error.value.message_key == "errors.identity_already_linked"


@pytest.mark.asyncio
async def test_unlink_last_identity_requires_local_credentials(uow_factory) -> None:
    authenticate_external = AuthenticateExternalIdentityUseCase(uow_factory, default_language="ru")
    unlink = UnlinkExternalIdentityUseCase(uow_factory)
    user = await authenticate_external.execute(
        ExternalIdentityContext(provider="telegram", provider_user_id="42", provider_username="tg_user"),
        create_user_if_missing=True,
    )

    with pytest.raises(ValidationError) as error:
        await unlink.execute(user_id=user.id, provider="telegram")
    assert error.value.message_key == "errors.last_identity_unlink_forbidden"
