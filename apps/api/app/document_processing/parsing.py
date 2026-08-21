"""Parsing contracts isolated from HTTP, persistence, and storage."""

from typing import Protocol

from app.document_processing.models import DocumentMetadata, ParsedDocument


class DocumentParser(Protocol):
    def parse(self, content: bytes, metadata: DocumentMetadata) -> ParsedDocument: ...


class DocumentParserError(Exception):
    """Raised when validated document bytes cannot be parsed safely."""
