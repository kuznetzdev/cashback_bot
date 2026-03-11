from __future__ import annotations

from collections.abc import Callable

from app.application.auth.models import ExternalIdentityContext, LocalAuthenticationCommand, LocalRegistrationCommand
from app.application.auth.normalization import normalize_email, normalize_username
from app.application.auth.passwords import PasswordHasherPort
from app.application.contracts.ports import UnitOfWorkPort
from app.domain.errors import NotFoundError, ValidationError
from app.domain.models import UserAccount, UserIdentity


class RegisterLocalUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], password_hasher: PasswordHasherPort, default_language: str) -> None:
        self.uow_factory = uow_factory
        self.password_hasher = password_hasher
        self.default_language = default_language

    async def execute(self, command: LocalRegistrationCommand) -> UserAccount:
        username = normalize_username(command.username)
        email = normalize_email(command.email)
        password = command.password.strip()
        if len(password) < 8:
            raise ValidationError("errors.invalid_password")
        display_name = (command.display_name or username).strip()
        if not display_name:
            raise ValidationError("errors.invalid_display_name")

        async with self.uow_factory() as uow:
            if await uow.credentials.get_by_username(username):
                raise ValidationError("errors.username_taken")
            if email is not None and await uow.credentials.get_by_email(email):
                raise ValidationError("errors.email_taken")
            user = await uow.users.create(display_name=display_name, default_language=self.default_language)
            await uow.credentials.create(
                user_id=user.id,
                username=username,
                email=email,
                password_hash=self.password_hasher.hash_password(password),
            )
            await uow.logs.add(user.id, "local_user_registered", {"username": username})
            await uow.commit()
            return user


class AuthenticateLocalUserUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], password_hasher: PasswordHasherPort) -> None:
        self.uow_factory = uow_factory
        self.password_hasher = password_hasher

    async def execute(self, command: LocalAuthenticationCommand) -> UserAccount:
        username = normalize_username(command.username)
        async with self.uow_factory() as uow:
            credentials = await uow.credentials.get_by_username(username)
            if credentials is None or not self.password_hasher.verify_password(command.password, credentials.password_hash):
                raise ValidationError("errors.invalid_credentials")
            user = await uow.users.get_by_id(credentials.user_id)
            if user is None:
                raise NotFoundError("errors.unexpected")
            await uow.logs.add(user.id, "local_user_authenticated", {"username": username})
            await uow.commit()
            return user


class AuthenticateExternalIdentityUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort], default_language: str) -> None:
        self.uow_factory = uow_factory
        self.default_language = default_language

    async def execute(
        self,
        identity: ExternalIdentityContext,
        *,
        create_user_if_missing: bool,
        log_action: str | None = None,
    ) -> UserAccount:
        async with self.uow_factory() as uow:
            existing = await uow.identities.get_by_provider_identity(
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
            )
            if existing is not None:
                user = await uow.users.get_by_id(existing.user_id)
                if user is None:
                    raise NotFoundError("errors.unexpected")
                if log_action:
                    await uow.logs.add(
                        user.id,
                        log_action,
                        {"provider": identity.provider, "provider_user_id": identity.provider_user_id},
                    )
                    await uow.commit()
                return user

            if not create_user_if_missing:
                raise ValidationError("errors.identity_not_linked")

            display_name = (
                identity.provider_display_name
                or identity.provider_username
                or f"{identity.provider}:{identity.provider_user_id}"
            ).strip()
            user = await uow.users.create(display_name=display_name, default_language=self.default_language)
            await uow.identities.upsert_for_user(
                user_id=user.id,
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
                provider_username=identity.provider_username,
                provider_display_name=identity.provider_display_name,
            )
            action = log_action or "external_identity_authenticated"
            await uow.logs.add(
                user.id,
                action,
                {"provider": identity.provider, "provider_user_id": identity.provider_user_id},
            )
            await uow.commit()
            return user


class LinkExternalIdentityUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, identity: ExternalIdentityContext) -> UserIdentity:
        async with self.uow_factory() as uow:
            existing = await uow.identities.get_by_provider_identity(
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
            )
            if existing is not None and existing.user_id != user_id:
                raise ValidationError("errors.identity_already_linked")

            linked = await uow.identities.upsert_for_user(
                user_id=user_id,
                provider=identity.provider,
                provider_user_id=identity.provider_user_id,
                provider_username=identity.provider_username,
                provider_display_name=identity.provider_display_name,
            )
            await uow.logs.add(
                user_id,
                "external_identity_linked",
                {"provider": identity.provider, "provider_user_id": identity.provider_user_id},
            )
            await uow.commit()
            return linked


class UnlinkExternalIdentityUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int, provider: str) -> None:
        async with self.uow_factory() as uow:
            has_local_credentials = await uow.credentials.has_for_user(user_id)
            identities_count = await uow.identities.count_for_user(user_id)
            if not has_local_credentials and identities_count <= 1:
                raise ValidationError("errors.last_identity_unlink_forbidden")
            removed = await uow.identities.remove_for_user(user_id=user_id, provider=provider)
            if not removed:
                raise NotFoundError("errors.identity_not_found")
            await uow.logs.add(user_id, "external_identity_unlinked", {"provider": provider})
            await uow.commit()


class GetUserAccountUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int) -> UserAccount | None:
        async with self.uow_factory() as uow:
            return await uow.users.get_by_id(user_id)


class ListExternalIdentitiesUseCase:
    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self.uow_factory = uow_factory

    async def execute(self, *, user_id: int) -> list[UserIdentity]:
        async with self.uow_factory() as uow:
            return await uow.identities.list_for_user(user_id)
