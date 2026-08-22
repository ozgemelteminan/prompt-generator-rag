"""Small SQLAlchemy type bridge for pgvector without a second vector dependency."""

import json

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.types import TypeDecorator, UserDefinedType


class _PostgresVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self._dimension})"


class PgVector(TypeDecorator[list[float]]):
    """Uses native pgvector in PostgreSQL and JSON text only for SQLite unit tests."""

    impl = Text
    cache_ok = True

    def __init__(self, dimension: int) -> None:
        super().__init__()
        self.dimension = dimension

    def load_dialect_impl(self, dialect: object) -> object:
        if getattr(dialect, "name", None) == "postgresql":
            return dialect.type_descriptor(_PostgresVector(self.dimension))  # type: ignore[union-attr]
        return dialect.type_descriptor(TEXT())  # type: ignore[union-attr]

    def process_bind_param(self, value: list[float] | None, dialect: object) -> str | None:
        if value is None:
            return None
        if len(value) != self.dimension:
            raise ValueError(f"Expected vector dimension {self.dimension}.")
        if getattr(dialect, "name", None) == "postgresql":
            return "[" + ",".join(str(float(item)) for item in value) + "]"
        return json.dumps(value)

    def process_result_value(
        self, value: str | list[float] | None, _: object
    ) -> list[float] | None:
        if value is None or isinstance(value, list):
            return value
        return [float(item) for item in json.loads(value)]
