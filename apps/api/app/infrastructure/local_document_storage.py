"""Local filesystem adapter for untrusted uploaded document bytes."""

import hashlib
from pathlib import Path


class LocalDocumentStorage:
    """Store internal keys below one configured root; filenames never control paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def save(self, *, workspace_id: str, document_id: str, content: bytes) -> str:
        workspace_key = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:24]
        storage_key = f"{workspace_key}/{document_id}/original"
        destination = self._resolve(storage_key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        except OSError as error:
            raise DocumentStorageError("Document could not be stored.") from error
        return storage_key

    def delete(self, storage_key: str) -> None:
        path = self._resolve(storage_key)
        try:
            path.unlink(missing_ok=True)
            for parent in (path.parent, path.parent.parent):
                if parent != self._root:
                    parent.rmdir()
        except OSError as error:
            raise DocumentStorageError("Document could not be deleted.") from error

    def read(self, storage_key: str) -> bytes:
        """Read a previously stored original through an internal validated key."""
        try:
            return self._resolve(storage_key).read_bytes()
        except OSError as error:
            raise DocumentStorageError("Document could not be read.") from error

    def _resolve(self, storage_key: str) -> Path:
        candidate = (self._root / storage_key).resolve()
        if self._root not in candidate.parents:
            raise DocumentStorageError("Invalid document storage reference.")
        return candidate


class DocumentStorageError(Exception):
    """Safe storage failure without filesystem implementation details."""
