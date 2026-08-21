"""Transactional quota reservations and append-only usage events."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import UsageCounterRecord, UsageEventRecord


class UsageAccountingError(Exception):
    """Raised when authoritative usage state cannot be updated safely."""


class UsageQuotaExceededError(Exception):
    """Raised when no quota capacity remains for the current period."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__("Usage quota is exhausted.")
        self.reset_at = reset_at


@dataclass(frozen=True)
class QuotaReservation:
    caller_id: str
    event_type: str
    period_key: str


@dataclass(frozen=True)
class UsageCounter:
    used: int
    limit: int
    remaining: int
    reset_at: datetime


def monthly_period(now: datetime) -> tuple[str, datetime]:
    current = now.astimezone(UTC)
    if current.month == 12:
        reset_at = datetime(current.year + 1, 1, 1, tzinfo=UTC)
    else:
        reset_at = datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    return f"{current.year:04d}-{current.month:02d}", reset_at


class UsageRepository:
    """Reserve and consume quota under row locks in the current database."""

    def __init__(self, session: Session, *, now: datetime | None = None) -> None:
        self._session = session
        self._now = now

    def reserve(self, *, caller_id: str, event_type: str, limit: int) -> QuotaReservation:
        period_key, reset_at = monthly_period(self._current_time())
        try:
            self._lock_quota_key(caller_id, event_type, period_key)
            counter = self._locked_counter(caller_id, event_type, period_key)
            if counter is None:
                counter = UsageCounterRecord(
                    caller_id=caller_id,
                    event_type=event_type,
                    period_key=period_key,
                    reset_at=reset_at,
                )
                self._session.add(counter)
                self._session.flush()
            if counter.used_amount + counter.reserved_amount >= limit:
                self._session.rollback()
                raise UsageQuotaExceededError(reset_at)
            counter.reserved_amount += 1
            self._session.commit()
            return QuotaReservation(caller_id, event_type, period_key)
        except UsageQuotaExceededError:
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise UsageAccountingError("Usage capacity could not be reserved.") from error

    def complete(
        self,
        reservation: QuotaReservation,
        *,
        prompt_id: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        try:
            self._lock_quota_key(
                reservation.caller_id, reservation.event_type, reservation.period_key
            )
            counter = self._locked_counter(
                reservation.caller_id, reservation.event_type, reservation.period_key
            )
            if counter is None or counter.reserved_amount < 1:
                raise UsageAccountingError("Usage reservation is unavailable.")
            counter.reserved_amount -= 1
            counter.used_amount += 1
            self._session.add(
                UsageEventRecord(
                    id=str(uuid4()),
                    caller_id=reservation.caller_id,
                    event_type=reservation.event_type,
                    amount=1,
                    prompt_id=prompt_id,
                    execution_id=execution_id,
                )
            )
            self._session.commit()
        except UsageAccountingError:
            self._session.rollback()
            raise
        except SQLAlchemyError as error:
            self._session.rollback()
            raise UsageAccountingError("Usage event could not be recorded.") from error

    def release(self, reservation: QuotaReservation) -> None:
        try:
            self._lock_quota_key(
                reservation.caller_id, reservation.event_type, reservation.period_key
            )
            counter = self._locked_counter(
                reservation.caller_id, reservation.event_type, reservation.period_key
            )
            if counter is not None and counter.reserved_amount > 0:
                counter.reserved_amount -= 1
            self._session.commit()
        except SQLAlchemyError as error:
            self._session.rollback()
            raise UsageAccountingError("Usage reservation could not be released.") from error

    def status(self, *, caller_id: str, event_type: str, limit: int) -> UsageCounter:
        period_key, reset_at = monthly_period(self._current_time())
        try:
            counter = self._session.get(UsageCounterRecord, (caller_id, event_type, period_key))
        except SQLAlchemyError as error:
            self._session.rollback()
            raise UsageAccountingError("Usage status could not be read.") from error
        used = counter.used_amount if counter is not None else 0
        return UsageCounter(
            used=used, limit=limit, remaining=max(0, limit - used), reset_at=reset_at
        )

    def _locked_counter(
        self, caller_id: str, event_type: str, period_key: str
    ) -> UsageCounterRecord | None:
        return self._session.scalar(
            select(UsageCounterRecord)
            .where(
                UsageCounterRecord.caller_id == caller_id,
                UsageCounterRecord.event_type == event_type,
                UsageCounterRecord.period_key == period_key,
            )
            .with_for_update()
        )

    def _current_time(self) -> datetime:
        return self._now or datetime.now(UTC)

    def _lock_quota_key(self, caller_id: str, event_type: str, period_key: str) -> None:
        """Serialize a quota key, including safe first-row creation, on PostgreSQL."""
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:quota_key, 0))"),
                {"quota_key": f"{caller_id}:{event_type}:{period_key}"},
            )
