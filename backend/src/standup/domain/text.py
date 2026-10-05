"""Text identity. Pure."""

import hashlib


def content_sha256(text: str) -> str:
    """The content hash pinned into the audit chain at ingestion.

    One definition, used both when the hash is pinned and when
    verify_evidence recomputes it: if the two ever differed, every stored
    update would look tampered with.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
