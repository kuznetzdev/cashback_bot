# Identity Migration: Clean Break

## Scope

This migration moves the product from a Telegram-centric identity model to a platform account model with linked identities and local credentials.

Migration file:

- `alembic/versions/20260311_0002_platform_identity.py`

## Schema Changes

### `users`

- add `display_name`
- keep `telegram_user_id`, but make it nullable

### `user_identities`

Stores external identities in normalized form:

- `user_id`
- `provider`
- `provider_user_id`
- `provider_username`
- `provider_display_name`

Constraints:

- unique `(provider, provider_user_id)`
- unique `(user_id, provider)`

### `local_credentials`

Stores local auth material:

- `user_id`
- `username`
- `email`
- `password_hash`

## Backfill Rules

Legacy users with `users.telegram_user_id` are backfilled into `user_identities` with:

- `provider = "telegram"`
- `provider_user_id = CAST(users.telegram_user_id AS TEXT)`
- `provider_username = users.username`
- `provider_display_name = users.full_name`

If duplicate Telegram ids exist in legacy data, the migration keeps the user with the smallest `users.id` as the owner of that Telegram identity.

## Behavioral Changes After Migration

- a platform user may exist without Telegram
- web local auth becomes possible
- reminder delivery resolves targets through `user_identities`
- `users.telegram_user_id` is no longer the authoritative identity source

## Compatibility Notes

The migration establishes `user_identities` as the source of truth for external identities.
Legacy columns on `users` remain in the schema as deprecated compatibility data:

- `users.telegram_user_id`
- `users.username`
- `users.full_name`

New runtime writes no longer mirror Telegram linkage into those columns.
New application logic must not treat these legacy columns as the canonical identity model.

## Operational Checklist

Before migration:

1. take a database backup
2. confirm application version includes new repositories and ports
3. confirm `AUTO_MIGRATE` policy for the environment

After migration:

1. verify `user_identities` row count is consistent with legacy Telegram users
2. verify at least one legacy Telegram user can still authenticate in the bot
3. verify local registration/login works in web
4. verify monthly reminder target query returns Telegram-linked users

## Reminder Behavior After Migration

Current reminder flow:

- selects reminder targets from `user_identities`
- resolves transport through a delivery provider injected by bootstrap wiring
- starts the reminder loop from application runtime rather than Telegram polling lifecycle
- now reads the delivery provider from `REMINDER_DELIVERY_PROVIDER`
- bundled compose keeps reminder ownership on the Telegram profile service
- uses `users.notifications_enabled` as the on/off switch

This means reminder routing is identity-based, while the current operational delivery transport remains Telegram-specific by configuration rather than by application hardcode or Telegram adapter ownership.

## Rollback Notes

Downgrade logic restores legacy Telegram linkage from `user_identities` back into `users.telegram_user_id` and removes:

- `local_credentials`
- `user_identities`
- `users.display_name`

Rollback limitation:

- any identities created only after the migration may be collapsed when mapping back to the single legacy Telegram column
- local credential records are dropped entirely on downgrade
