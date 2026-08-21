from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from prompt_engine.compiler import GenericPromptCompiler
from prompt_engine.errors import EmptyRawRequestError, StructuredAnalysisBackendError
from prompt_engine.execution import ExecutionResult
from prompt_engine.gaps import GapAnalyzer
from prompt_engine.intent import IntentAnalyzer, StructuredAnalysisRequest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import (
    get_prompt_execution_service,
    get_prompt_generation_service,
    get_usage_guard,
)
from app.core.caller import CallerContext
from app.core.rate_limits import InMemoryRateLimiter
from app.db.models import Base, UsageEventRecord
from app.main import app
from app.repositories.usage import UsageQuotaExceededError, UsageRepository
from app.services.prompt_execution import PromptExecutionService
from app.services.prompt_generation import PromptGenerationService
from app.services.usage import ActionPolicy, RateLimitExceededError, UsageAction, UsageGuard


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@dataclass
class FakeAnalysisBackend:
    calls: int = 0
    error: Exception | None = None

    def analyze(self, _: StructuredAnalysisRequest) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {"task": {"type": "general", "objective": "Help me."}, "language": "en"}


@dataclass
class FakeExecutionBackend:
    calls: int = 0
    error: Exception | None = None

    def execute(self, _: str) -> ExecutionResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ExecutionResult(output="Done")


def make_guard(
    *,
    generation_rate: int = 10,
    execution_rate: int = 10,
    generation_quota: int = 10,
    execution_quota: int = 10,
    clock: FakeClock | None = None,
) -> UsageGuard:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    repository = UsageRepository(Session(engine), now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC))
    return UsageGuard(
        caller=CallerContext("local-test"),
        rate_limiter=InMemoryRateLimiter(clock or FakeClock()),
        repository=repository,
        generation_policy=ActionPolicy(generation_rate, 60, generation_quota),
        execution_policy=ActionPolicy(execution_rate, 60, execution_quota),
    )


def make_generation_service(
    backend: FakeAnalysisBackend, guard: UsageGuard
) -> PromptGenerationService:
    return PromptGenerationService(
        intent_analyzer=IntentAnalyzer(backend),
        gap_analyzer=GapAnalyzer(),
        compiler=GenericPromptCompiler(),
        usage_guard=guard,
    )


def test_rate_limits_are_independent_and_reset_without_sleeping() -> None:
    clock = FakeClock()
    guard = make_guard(generation_rate=1, execution_rate=1, clock=clock)
    generation = guard.start(UsageAction.PROMPT_GENERATION)
    guard.release(generation)

    with pytest.raises(RateLimitExceededError) as error:
        guard.start(UsageAction.PROMPT_GENERATION)
    assert error.value.retry_after_seconds == 60

    execution = guard.start(UsageAction.PROMPT_EXECUTION)
    guard.release(execution)
    clock.value = 60
    reset_generation = guard.start(UsageAction.PROMPT_GENERATION)
    guard.release(reset_generation)


def test_quota_events_and_counters_are_authoritative_and_independent() -> None:
    guard = make_guard(generation_quota=1, execution_quota=2)
    generation = guard.start(UsageAction.PROMPT_GENERATION)
    guard.complete(generation)

    with pytest.raises(UsageQuotaExceededError):
        guard.start(UsageAction.PROMPT_GENERATION)

    execution = guard.start(UsageAction.PROMPT_EXECUTION)
    guard.complete(execution)
    status = guard.status()
    assert (status.generation.used, status.generation.remaining) == (1, 0)
    assert (status.execution.used, status.execution.remaining) == (1, 1)
    assert status.generation.reset_at == datetime(2026, 9, 1, tzinfo=UTC)


def test_success_completion_appends_one_server_side_usage_event() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    repository = UsageRepository(session, now=datetime(2026, 8, 21, tzinfo=UTC))
    reservation = repository.reserve(
        caller_id="local-test", event_type="prompt_generation", limit=2
    )

    repository.complete(reservation)

    assert session.scalar(select(func.count()).select_from(UsageEventRecord)) == 1


def test_open_reservation_blocks_parallel_capacity_until_released() -> None:
    guard = make_guard(generation_quota=1)
    reservation = guard.start(UsageAction.PROMPT_GENERATION)

    with pytest.raises(UsageQuotaExceededError):
        guard.start(UsageAction.PROMPT_GENERATION)

    guard.release(reservation)
    replacement = guard.start(UsageAction.PROMPT_GENERATION)
    guard.release(replacement)


def test_quota_rejection_blocks_generation_provider_call() -> None:
    guard = make_guard(generation_quota=0)
    backend = FakeAnalysisBackend()
    service = make_generation_service(backend, guard)

    with pytest.raises(UsageQuotaExceededError):
        service.generate("Help me.", language="en")
    assert backend.calls == 0


def test_validation_failure_is_not_rate_limited_or_counted() -> None:
    guard = make_guard(generation_rate=1, generation_quota=1)
    backend = FakeAnalysisBackend()
    service = make_generation_service(backend, guard)

    with pytest.raises(EmptyRawRequestError):
        service.generate("   ", language="en")
    assert guard.status().generation.used == 0
    service.generate("Help me.", language="en")
    assert backend.calls == 1


def test_provider_failure_releases_reservation_without_counting_usage() -> None:
    guard = make_guard()
    backend = FakeAnalysisBackend(error=RuntimeError("private provider detail"))
    service = make_generation_service(backend, guard)

    with pytest.raises(StructuredAnalysisBackendError):
        service.generate("Help me.", language="en")
    assert guard.status().generation.used == 0


def test_successful_generation_and_execution_count_separately() -> None:
    guard = make_guard()
    analysis = FakeAnalysisBackend()
    execution = FakeExecutionBackend()
    make_generation_service(analysis, guard).generate("Help me.", language="en")
    PromptExecutionService(
        backend=execution, max_input_characters=1_000, usage_guard=guard
    ).execute("Compiled prompt")

    status = guard.status()
    assert status.generation.used == 1
    assert status.execution.used == 1
    assert analysis.calls == 1
    assert execution.calls == 1


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_rate_limit_api_returns_stable_429_without_provider_details(client: TestClient) -> None:
    guard = make_guard(generation_rate=1)
    backend = FakeAnalysisBackend()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_generation_service(
        backend, guard
    )

    assert (
        client.post(
            "/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"}
        ).status_code
        == 200
    )
    response = client.post("/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.json()["error"]["details"]["retryAfterSeconds"] == 60
    assert response.headers["retry-after"] == "60"
    assert backend.calls == 1


def test_quota_api_is_distinct_and_usage_status_is_provider_independent(client: TestClient) -> None:
    guard = make_guard(generation_quota=0)
    backend = FakeAnalysisBackend()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_generation_service(
        backend, guard
    )
    app.dependency_overrides[get_usage_guard] = lambda: guard

    response = client.post("/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"})
    usage = client.get("/api/v1/usage")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "usage_quota_exceeded"
    assert backend.calls == 0
    assert usage.status_code == 200
    assert usage.json()["generation"] == {
        "used": 0,
        "limit": 0,
        "remaining": 0,
        "resetAt": "2026-09-01T00:00:00+00:00",
    }


def test_execution_rate_limit_rejection_does_not_call_backend(client: TestClient) -> None:
    guard = make_guard(execution_rate=1)
    backend = FakeExecutionBackend()
    service = PromptExecutionService(backend=backend, max_input_characters=1_000, usage_guard=guard)
    app.dependency_overrides[get_prompt_execution_service] = lambda: service

    assert (
        client.post("/api/v1/prompts/execute", json={"compiledPrompt": "Run this."}).status_code
        == 200
    )
    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": "Run this."})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert backend.calls == 1


def test_unexpected_internal_error_uses_stable_envelope_without_leaking() -> None:
    class ExplodingService:
        def generate(self, *_: object, **__: object) -> object:
            raise RuntimeError("private internal detail")

    app.dependency_overrides[get_prompt_generation_service] = lambda: ExplodingService()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"}
        )
    app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private internal detail" not in response.text
