"""Turn a ``RawSubmission`` into a canonical raw text plus offset-bearing items.

The whole citation contract rests on one invariant, asserted in
``tests/unit/test_normalizer.py``:

    raw_text[item.span_start:item.span_end] == item.text

So segmentation here never strips, normalises, or rewrites a span's text. It
only *finds boundaries*. Anything that would alter characters happens later and
carries its own offsets.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from standup.domain.enums import ItemKind
from standup.domain.errors import SpanDriftError
from standup.ingestion.base import RawSubmission

# Order matters: it is the order fields appear in the composed raw text.
FIELD_ORDER: tuple[ItemKind, ...] = (ItemKind.PROGRESS, ItemKind.BLOCKER, ItemKind.PLAN)

FIELD_HEADINGS: dict[ItemKind, str] = {
    ItemKind.PROGRESS: "Progress",
    ItemKind.BLOCKER: "Blockers",
    ItemKind.PLAN: "Today",
}

# A segment ends at a newline, a bullet, or sentence-final punctuation followed
# by whitespace. Deliberately simple: a wrong boundary costs readability, but
# can never cost faithfulness, because the span is still quoted verbatim.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+|(?:^|\n)\s*[-*•]\s*")

_ENTITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("issue", re.compile(r"(?:\b[\w.-]+/[\w.-]+)?#\d+")),
    ("url", re.compile(r"https?://\S+")),
    ("ticket", re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")),
    ("mention", re.compile(r"@[\w.-]+")),
)

_STOPWORDS = frozenset(
    """a an the i we my our is are am was were be been being to of in on at for with
    and or but if then so that this these those it its as by from up down out about
    still need needs needed get getting got have has had do does did doing not no""".split()
)


@dataclass(frozen=True)
class NormalizedItem:
    kind: ItemKind
    text: str
    span_start: int
    span_end: int
    normalized_key: str
    entity_refs: list[dict[str, str]]
    order: int


@dataclass(frozen=True)
class NormalizedUpdate:
    raw_text: str
    content_sha256: str
    items: tuple[NormalizedItem, ...]


_BLOCK_SEPARATOR = "\n\n"


def _compose(submission: RawSubmission) -> tuple[str, dict[ItemKind, int]]:
    """Build the raw text and record where each field's text starts in it.

    Offsets are taken while the string is built, never found afterwards by
    searching for a heading: a user can type "Blockers:" into Progress, and a
    search would match their text instead of the real heading.
    """
    blocks: list[str] = []
    starts: dict[ItemKind, int] = {}
    position = 0
    for kind in FIELD_ORDER:
        value = submission.text_fields.get(kind, "")
        if not value or not value.strip():
            continue
        if blocks:
            position += len(_BLOCK_SEPARATOR)
        heading = f"{FIELD_HEADINGS[kind]}:\n"
        starts[kind] = position + len(heading)
        block = heading + value.strip()
        blocks.append(block)
        position += len(block)
    return _BLOCK_SEPARATOR.join(blocks), starts


def compose_raw_text(submission: RawSubmission) -> str:
    """Build the canonical record of what someone submitted.

    Headings are included so the stored evidence reads the way the person filled
    the form in, and so spans have stable, meaningful surroundings.
    """
    return _compose(submission)[0]


def extract_entities(text: str) -> list[dict[str, str]]:
    """Find issue refs, URLs, tickets and mentions.

    Used for deterministic grouping and, from week 2, for validator rule V5:
    an entity in a claim must appear in a cited source.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if value not in seen:
                seen.add(value)
                found.append({"kind": label, "value": value})
    return found


def normalized_key(text: str) -> str:
    """A stable key for matching the same blocker across days.

    Lowercased, punctuation-stripped, stopwords removed, tokens sorted. Crude on
    purpose — it feeds carry-over detection in week 3, where a false negative
    (a missed carry-over) is far cheaper than a false positive (two people's
    different blockers merged into one).
    """
    lowered = unicodedata.normalize("NFKC", text).lower()
    tokens = re.findall(r"[a-z0-9#/-]+", lowered)
    meaningful = sorted({t for t in tokens if t not in _STOPWORDS and len(t) > 1})
    return " ".join(meaningful)[:500]


def _segment(block_text: str, block_offset: int) -> list[tuple[str, int, int]]:
    """Split a field's text into segments, returning exact spans.

    Spans are offsets into the composed raw text, not into ``block_text``.
    """
    segments: list[tuple[str, int, int]] = []
    cursor = 0
    for match in _BOUNDARY.finditer(block_text):
        end = match.start()
        piece = block_text[cursor:end]
        if piece.strip():
            start_pad = len(piece) - len(piece.lstrip())
            end_pad = len(piece) - len(piece.rstrip())
            segments.append(
                (
                    piece.strip(),
                    block_offset + cursor + start_pad,
                    block_offset + end - end_pad,
                )
            )
        cursor = match.end()

    tail = block_text[cursor:]
    if tail.strip():
        start_pad = len(tail) - len(tail.lstrip())
        end_pad = len(tail) - len(tail.rstrip())
        segments.append(
            (
                tail.strip(),
                block_offset + cursor + start_pad,
                block_offset + len(block_text) - end_pad,
            )
        )
    return segments


def normalize(submission: RawSubmission) -> NormalizedUpdate:
    """Compose the raw text and split it into items with verified spans."""
    raw_text, block_starts = _compose(submission)
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    items: list[NormalizedItem] = []
    order = 0
    for kind in FIELD_ORDER:
        value = submission.text_fields.get(kind, "")
        if not value or not value.strip():
            continue

        block_start = block_starts[kind]
        block_text = value.strip()

        for text, start, end in _segment(block_text, block_start):
            # Never emit a span that does not round-trip (invariant 3). A raised
            # error, not an assert: python -O strips asserts.
            if raw_text[start:end] != text:
                raise SpanDriftError(
                    f"span drift for {kind}: {raw_text[start:end]!r} != {text!r}"
                )
            items.append(
                NormalizedItem(
                    kind=kind,
                    text=text,
                    span_start=start,
                    span_end=end,
                    normalized_key=normalized_key(text),
                    entity_refs=extract_entities(text),
                    order=order,
                )
            )
            order += 1

    return NormalizedUpdate(raw_text=raw_text, content_sha256=digest, items=tuple(items))
