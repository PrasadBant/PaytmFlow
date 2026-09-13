import hashlib
from pathlib import Path
from uuid import UUID

from app.config import settings


class EvidenceError(Exception):
    """Base exception for evidence processing errors."""


class FileTooLargeError(EvidenceError):
    """Raised when uploaded file exceeds maximum allowed bytes (413)."""


class InvalidFileFormatError(EvidenceError):
    """Raised when uploaded file is empty, has invalid magic bytes, or disallowed format (400)."""


ALLOWED_MAGIC_BYTES = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
]


def validate_upload(
    content: bytes,
    filename: str | None = None,
    max_bytes: int | None = None,
) -> tuple[str, str]:
    """Validates file byte size, non-emptiness, and magic bytes.

    Returns:
        (detected_mime_type, file_extension)

    Raises:
        FileTooLargeError: If file exceeds max_bytes limit.
        InvalidFileFormatError: If file is empty, has invalid magic bytes, or extension mismatch.
    """
    limit = max_bytes if max_bytes is not None else settings.EVIDENCE_MAX_BYTES

    if len(content) > limit:
        raise FileTooLargeError(
            f"Uploaded file size ({len(content)} bytes) exceeds the maximum limit of {limit} bytes."
        )

    if not content:
        raise InvalidFileFormatError("Uploaded file is empty.")

    detected_mime: str | None = None
    detected_ext: str | None = None

    for magic, mime, ext in ALLOWED_MAGIC_BYTES:
        if content.startswith(magic):
            detected_mime = mime
            detected_ext = ext
            break

    if not detected_mime or not detected_ext:
        raise InvalidFileFormatError(
            "Unsupported file format or magic bytes mismatch. "
            "Only valid PDF, JPEG, and PNG files are accepted."
        )

    # If filename is supplied, enforce allow-list on extension and reject renamed archives
    if filename:
        fn_lower = filename.lower()
        if fn_lower.endswith((".zip", ".tar", ".gz", ".exe", ".sh", ".bat", ".bin", ".rar")):
            raise InvalidFileFormatError(f"Disallowed file extension in filename '{filename}'.")

    return detected_mime, detected_ext


def store_evidence_file(
    journey_id: UUID | str,
    filename: str,
    content: bytes,
    storage_dir: str | Path | None = None,
) -> tuple[str, str, int, str]:
    """Validates, deduplicates by sha256, and stores the evidence file to disk.

    Returns:
        (file_path, sha256_checksum, file_size_bytes, mime_type)
    """
    mime_type, ext = validate_upload(content=content, filename=filename)

    sha256_hash = hashlib.sha256(content).hexdigest()
    file_size_bytes = len(content)

    base_dir = Path(storage_dir or settings.EVIDENCE_STORAGE_DIR)
    target_dir = base_dir / str(journey_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / f"{sha256_hash}{ext}"

    # Deduplicate: Only write if file doesn't already exist on disk
    if not target_file.exists():
        target_file.write_bytes(content)

    return str(target_file), sha256_hash, file_size_bytes, mime_type
