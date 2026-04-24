from __future__ import annotations

import pytest

from app.application.use_cases.find_user_by_identity import FindUserByExternalIdentityUseCase


@pytest.mark.asyncio
async def test_returns_none_when_identity_missing(uow_factory):
    use_case = FindUserByExternalIdentityUseCase(uow_factory)

    result = await use_case.execute(provider="telegram", provider_user_id="42")

    assert result is None


@pytest.mark.asyncio
async def test_returns_user_when_identity_linked(uow_factory, store):
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="Иван", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="42",
            provider_username="ivan",
            provider_display_name="Иван",
        )
        await uow.commit()

    use_case = FindUserByExternalIdentityUseCase(uow_factory)
    result = await use_case.execute(provider="telegram", provider_user_id="42")

    assert result is not None
    assert result.display_name == "Иван"


@pytest.mark.asyncio
async def test_returns_none_for_other_provider(uow_factory):
    async with uow_factory() as uow:
        user = await uow.users.create(display_name="U", default_language="ru")
        await uow.identities.upsert_for_user(
            user_id=user.id,
            provider="telegram",
            provider_user_id="42",
            provider_username=None,
            provider_display_name=None,
        )
        await uow.commit()

    use_case = FindUserByExternalIdentityUseCase(uow_factory)
    # Same provider_user_id but a different provider — must not cross-match.
    result = await use_case.execute(provider="google", provider_user_id="42")

    assert result is None
