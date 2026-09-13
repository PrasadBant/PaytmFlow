import tempfile
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest

from app.evidence.extract import extract_text_from_document, parse_financial_patterns
from app.evidence.storage import (
    FileTooLargeError,
    InvalidFileFormatError,
    store_evidence_file,
    validate_upload,
)


def create_sample_pdf(text: str) -> bytes:
    """Helper creating a minimal valid PDF in-memory using PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_upload_validation_size_limit():
    # 12 MB payload exceeds 10 MB limit
    twelve_mb = b"%PDF-" + b"0" * (12 * 1024 * 1024)
    with pytest.raises(FileTooLargeError) as exc_info:
        validate_upload(twelve_mb, filename="large_statement.pdf", max_bytes=10 * 1024 * 1024)
    assert "exceeds the maximum limit" in str(exc_info.value)


def test_upload_validation_magic_bytes_and_disallowed_extensions():
    # 1. ZIP archive renamed to .pdf
    zip_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"
    with pytest.raises(InvalidFileFormatError) as exc_info:
        validate_upload(zip_bytes, filename="fake_salary_slip.pdf")
    assert "Unsupported file format" in str(exc_info.value)

    # 2. Executable / Archive extension
    with pytest.raises(InvalidFileFormatError) as exc_info:
        validate_upload(b"%PDF-1.4 valid pdf", filename="malicious.zip")
    assert "Disallowed file extension" in str(exc_info.value)

    # 3. Empty file
    with pytest.raises(InvalidFileFormatError) as exc_info:
        validate_upload(b"", filename="empty.pdf")
    assert "empty" in str(exc_info.value)


def test_upload_validation_valid_formats():
    # PDF
    mime, ext = validate_upload(b"%PDF-1.4\n%header", filename="doc.pdf")
    assert mime == "application/pdf"
    assert ext == ".pdf"

    # JPEG
    mime, ext = validate_upload(b"\xff\xd8\xff\xe0\x00\x10JFIF", filename="photo.jpg")
    assert mime == "image/jpeg"
    assert ext == ".jpg"

    # PNG
    mime, ext = validate_upload(b"\x89PNG\r\n\x1a\n\x00\x00", filename="screenshot.png")
    assert mime == "image/png"
    assert ext == ".png"


def test_storage_and_sha256_deduplication():
    with tempfile.TemporaryDirectory() as tmp_dir:
        journey_id = uuid4()
        pdf_content = create_sample_pdf("Salary slip for testing")

        # 1. Store first time
        file_path1, sha1, size1, mime1 = store_evidence_file(
            journey_id=journey_id,
            filename="salary_slip.pdf",
            content=pdf_content,
            storage_dir=tmp_dir,
        )
        assert Path(file_path1).exists()
        assert size1 == len(pdf_content)
        assert mime1 == "application/pdf"

        # 2. Store identical content again -> deduplication path
        file_path2, sha2, size2, mime2 = store_evidence_file(
            journey_id=journey_id,
            filename="salary_slip_copy.pdf",
            content=pdf_content,
            storage_dir=tmp_dir,
        )
        assert file_path1 == file_path2
        assert sha1 == sha2


def test_pymupdf_extraction_and_pattern_parsing():
    sample_text = (
        "ACME INFOTECH INDIA PRIVATE LIMITED\n"
        "Employee Name: Rohit Sharma\n"
        "Permanent Account Number: ABCDE1234F\n"
        "Aadhaar Number: 9876 5432 1098\n"
        "Bank Account IFSC: HDFC0001234\n"
        "Salary Period: 01/03/2026 to 31/03/2026\n"
        "Gross Pay: ₹95,000\n"
        "Net Pay: ₹85,000\n"
    )

    pdf_bytes = create_sample_pdf(sample_text)
    extracted = extract_text_from_document(pdf_bytes, mime_type="application/pdf")

    assert "ABCDE1234F" in extracted
    assert "HDFC0001234" in extracted
    assert "85,000" in extracted

    patterns = parse_financial_patterns(extracted)
    assert patterns["pan"] == "ABCDE1234F"
    assert patterns["aadhaar"] == "987654321098"
    assert patterns["ifsc"] == "HDFC0001234"
    assert patterns["monthly_income"] in [85000, 95000]
    assert 85000 in patterns["detected_amounts"]
    assert "01/03/2026" in patterns["detected_dates"]
