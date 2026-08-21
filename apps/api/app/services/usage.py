"""Separate rate-limit and monthly quota orchestration."""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.caller import CallerContext
from app.core.rate_limits import InMemoryRateLimiter
from app.repositories.usage import (
    QuotaReservation,
    UsageAccountingError,
    UsageCounter,
    UsageQuotaExceededError,
    UsageRepository,
)

logger = logging.getLogger(__name__)


class UsageAction(StrEnum):
    PROMPT_GENERATION = "prompt_generation"
    PROMPT_EXECUTION = "prompt_execution"


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Application rate limit exceeded.")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class ActionPolicy:
    rate_limit: int
    rate_window_seconds: int
    quota_limit: int


@dataclass(frozen=True)
class UsageStatus:
    generation: UsageCounter
    execution: UsageCounter


class UsageGuard:
    """Apply burst limits before transactional quota reservations."""

    def __init__(
        self,
        *,
        caller: CallerContext,
        rate_limiter: InMemoryRateLimiter,
        repository: UsageRepository,
        generation_policy: ActionPolicy,
        execution_policy: ActionPolicy,
    ) -> None:
        self._caller = caller
        self._rate_limiter = rate_limiter
        self._repository = repository
        self._policies = {
            UsageAction.PROMPT_GENERATION: generation_policy,
            UsageAction.PROMPT_EXECUTION: execution_policy,
        }

    def start(self, action: UsageAction) -> QuotaReservation:
        policy = self._policies[action]
        decision = self._rate_limiter.check(
            caller_id=self._caller.id,
            action=action,
            limit=policy.rate_limit,
            window_seconds=policy.rate_window_seconds,
        )
        if not decision.allowed:
            logger.warning("rate_limit_rejected action=%s caller=%s", action, self._caller.id)
            raise RateLimitExceededError(decision.retry_after_seconds or 1)
        try:
            return self._repository.reserve(
                caller_id=self._caller.id, event_type=action, limit=policy.quota_limit
            )
        except UsageQuotaExceededError:
            logger.warning("quota_rejected action=%s caller=%s", action, self._caller.id)
            raise
        except UsageAccountingError:
            logger.error("usage_accounting_failed action=%s caller=%s", action, self._caller.id)
            raise

    def complete(self, reservation: QuotaReservation) -> None:
        try:
            self._repository.complete(reservation)
        except UsageAccountingError:
            logger.error(
                "usage_accounting_failed action=%s caller=%s",
                reservation.event_type,
                self._caller.id,
            )
            raise
        logger.info(
            "usage_event_recorded action=%s caller=%s", reservation.event_type, self._caller.id
        )

    def release(self, reservation: QuotaReservation) -> None:
        try:
            self._repository.release(reservation)
        except UsageAccountingError:
            logger.error(
                "usage_release_failed action=%s caller=%s",
                reservation.event_type,
                self._caller.id,
            )
            raise

    def status(self) -> UsageStatus:
        return UsageStatus(
            generation=self._repository.status(
                caller_id=self._caller.id,
                event_type=UsageAction.PROMPT_GENERATION,
                limit=self._policies[UsageAction.PROMPT_GENERATION].quota_limit,
            ),
            execution=self._repository.status(
                caller_id=self._caller.id,
                event_type=UsageAction.PROMPT_EXECUTION,
                limit=self._policies[UsageAction.PROMPT_EXECUTION].quota_limit,
            ),
        )


def as_reset_iso(value: datetime) -> str:
    return value.isoformat()
