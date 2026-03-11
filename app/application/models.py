from __future__ import annotations

from dataclasses import dataclass

from app.application.workflow.models import (
    Action,
    Effect,
    Screen,
    UserCommand,
    WorkflowResult,
    WorkflowState,
)


@dataclass(slots=True)
class UserContext:
    external_user_id: int
    username: str | None
    full_name: str | None


# Transitional compatibility re-exports.
# New code should import workflow contracts from app.application.workflow.models directly.
__all__ = [
    "Action",
    "Effect",
    "Screen",
    "UserCommand",
    "UserContext",
    "WorkflowResult",
    "WorkflowState",
]
