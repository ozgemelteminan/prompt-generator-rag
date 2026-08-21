"""Deterministic text cleanup and lightweight language detection."""

import re
import unicodedata

from app.document_processing.models import NormalizedDocument, ParsedDocument, TextBlock

_SPACE_RUN = re.compile(r"[ \t]+")
_TURKISH_WORDS = frozenset({"ve", "bir", "bu", "için", "ile", "olarak", "daha", "çok", "de", "da"})
_ENGLISH_WORDS = frozenset({"the", "and", "for", "with", "this", "that", "from", "are", "is", "to"})


def normalize_document(document: ParsedDocument) -> NormalizedDocument:
    blocks = tuple(
        normalized
        for block in document.blocks
        if (normalized := normalize_block(block)) is not None
    )
    return NormalizedDocument(
        document_id=document.document_id,
        blocks=blocks,
        language=detect_language("\n\n".join(block.text for block in blocks)),
    )


def normalize_block(block: TextBlock) -> TextBlock | None:
    text = _strip_controls(block.text).replace("\r\n", "\n").replace("\r", "\n")
    if block.block_type == "code":
        cleaned = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    else:
        cleaned = "\n".join(_SPACE_RUN.sub(" ", line).strip() for line in text.split("\n"))
        cleaned = cleaned.strip()
    if not cleaned:
        return None
    return TextBlock(
        block_type=block.block_type,
        text=cleaned,
        order_index=block.order_index,
        page_number=block.page_number,
        heading_level=block.heading_level,
        section=block.section,
    )


def detect_language(text: str) -> str | None:
    """Use a small local heuristic; short or inconclusive text remains unknown."""
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text.lower())
    if len(words) < 4:
        return None
    turkish_score = sum(word in _TURKISH_WORDS for word in words) + sum(
        character in text.lower() for character in "çğıöşü"
    )
    english_score = sum(word in _ENGLISH_WORDS for word in words)
    if turkish_score >= 2 and turkish_score > english_score:
        return "tr"
    if english_score >= 2 and english_score > turkish_score:
        return "en"
    return None


def _strip_controls(text: str) -> str:
    return "".join(
        character
        for character in text
        if character in {"\n", "\r", "\t"} or unicodedata.category(character) != "Cc"
    )
