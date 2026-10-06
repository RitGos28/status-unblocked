"""The shared pure helpers that replaced copies drifting apart (review D)."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

from standup.domain.text import content_sha256
from standup.domain.timezones import as_utc
from standup.domain.urls import digest_url, evidence_url
from standup.ingestion.base import FORM_FIELDS, text_fields_from


def test_content_hash_is_the_sha256_of_the_utf8_text():
    assert content_sha256("café") == hashlib.sha256("café".encode()).hexdigest()


def test_as_utc_treats_naive_as_utc_and_converts_aware():
    naive = datetime(2026, 9, 15, 9, 0)
    assert as_utc(naive) == datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    ist = datetime(2026, 9, 15, 14, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert as_utc(ist) == datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
    assert as_utc(ist).utcoffset() == timedelta(0)


def test_urls_join_cleanly_with_or_without_a_trailing_slash():
    for base in ("https://x.example", "https://x.example/"):
        assert digest_url(base, "d1") == "https://x.example/digest/d1"
        assert evidence_url(base, "i1") == "https://x.example/evidence/i1"


def test_one_field_map_feeds_every_adapter():
    assert set(FORM_FIELDS) == {"progress", "blockers", "plan"}
    fields = text_fields_from({"progress": "a", "blockers": None})
    assert list(fields.values()) == ["a", "", ""]
