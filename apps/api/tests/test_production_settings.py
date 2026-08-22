import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_settings_keep_debug_disabled_and_require_explicit_cors() -> None:
    settings = Settings(
        app_environment="production",
        debug=False,
        cors_origins="https://app.example.com",
    )

    assert settings.debug is False
    assert settings.cors_origins == ["https://app.example.com"]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"app_environment": "production", "debug": True}, "DEBUG must be false"),
        ({"cors_origins": "*"}, "CORS_ORIGINS must list explicit origins"),
    ],
)
def test_unsafe_runtime_settings_are_rejected(values: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**values)
