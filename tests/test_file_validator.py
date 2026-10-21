"""Automated tests for content-based upload validation (Security Module 7).

Covers:
1. Genuine files of every supported kind are accepted with the right kind
2. Files whose content doesn't match their extension are rejected
3. Unsupported, missing and empty files are rejected
4. quiz_extractor rejects a disguised upload before parsing or the security gate
"""

import io
from pathlib import Path

import pytest
from PIL import Image

import file_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from file_validator import FileValidationError, validate_upload  # noqa: E402


def make_image(image_format: str) -> bytes:
    """Return the bytes of a tiny real image in the given PIL format."""

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, image_format)
    return buffer.getvalue()


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
EXE_BYTES = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 300
ZIP_BYTES = b"PK\x03\x04\x14\x00\x00\x00" + b"\x00" * 300


# ── 1. Genuine files are accepted ──────────────────────────────────────

@pytest.mark.parametrize(
    "filename, image_format",
    [
        ("diagram.png", "PNG"),
        ("photo.jpg", "JPEG"),
        ("photo.jpeg", "JPEG"),
        ("animation.gif", "GIF"),
        ("screenshot.webp", "WEBP"),
        ("scan.bmp", "BMP"),
        ("scan.tif", "TIFF"),
        ("scan.tiff", "TIFF"),
    ],
)
def test_real_images_are_accepted(filename, image_format):
    assert validate_upload(make_image(image_format), filename) == "image"


def test_real_pdf_is_accepted():
    assert validate_upload(PDF_BYTES, "quiz.pdf") == "pdf"


def test_extension_check_is_case_insensitive():
    assert validate_upload(PDF_BYTES, "QUIZ.PDF") == "pdf"


def test_image_saved_with_another_image_extension_is_accepted():
    # A PNG named .jpg is harmless: both go through the same OCR step.
    assert validate_upload(make_image("PNG"), "photo.jpg") == "image"


@pytest.mark.parametrize(
    "filename, content",
    [
        ("solution.py", b"def add(a, b):\n    return a + b\n"),
        ("notes.md", "# Week 1\nCafé – naïve ✓".encode("utf-8")),
        ("legacy.txt", "Café".encode("cp1252")),
        ("query.sql", b"SELECT * FROM users WHERE id = 1;"),
    ],
)
def test_text_and_code_files_are_accepted(filename, content):
    assert validate_upload(content, filename) == "text"


def test_text_starting_with_bmp_signature_is_still_text():
    # filetype reports any content starting with "BM" as a BMP image,
    # so text files must not be judged by filetype.
    assert validate_upload(b"BMI = weight / height ** 2\n", "bmi.txt") == "text"


# ── 2. Content that doesn't match the extension is rejected ────────────

@pytest.mark.parametrize(
    "content, filename, expected_message",
    [
        (EXE_BYTES, "notes.txt", "contains binary data"),
        (ZIP_BYTES, "script.py", "contains binary data"),
        (b"just some text", "quiz.pdf", "claims to be a PDF"),
        (make_image("PNG"), "quiz.pdf", "image/png"),
        (PDF_BYTES, "photo.png", "application/pdf"),
        (EXE_BYTES, "photo.jpg", "application/x-msdownload"),
        (b"just some text", "photo.png", "claims to be a IMAGE"),
    ],
)
def test_mismatched_content_is_rejected(content, filename, expected_message):
    with pytest.raises(FileValidationError, match=expected_message):
        validate_upload(content, filename)


# ── 3. Unsupported, missing and empty files are rejected ───────────────

@pytest.mark.parametrize("filename", ["virus.exe", "archive.zip", "README"])
def test_unsupported_extensions_are_rejected(filename):
    with pytest.raises(FileValidationError, match="Unsupported file type"):
        validate_upload(b"hello", filename)


def test_unsupported_extension_is_rejected_even_with_valid_content():
    with pytest.raises(FileValidationError, match="Unsupported file type"):
        validate_upload(PDF_BYTES, "quiz.exe")


@pytest.mark.parametrize("filename", ["empty.txt", "empty.pdf", "empty.png"])
def test_empty_files_are_rejected(filename):
    with pytest.raises(FileValidationError, match="is empty"):
        validate_upload(b"", filename)


def test_file_validation_error_is_a_value_error():
    # Existing callers that catch ValueError keep working.
    assert issubclass(FileValidationError, ValueError)


def test_supported_extensions_cover_every_kind():
    assert file_validator.SUPPORTED_EXTENSIONS == (
        file_validator.PDF_EXTENSIONS
        | file_validator.IMAGE_EXTENSIONS
        | file_validator.TEXT_EXTENSIONS
    )


# ── 4. quiz_extractor wiring ───────────────────────────────────────────

@pytest.fixture
def quiz_extractor(monkeypatch):
    """Import quiz_extractor with the security gate replaced by a recorder."""

    import quiz_extractor as module

    gate_calls = []
    monkeypatch.setattr(module, "_check_content_safe", gate_calls.append)
    module.gate_calls = gate_calls
    return module


def test_disguised_upload_is_rejected_before_the_security_gate(quiz_extractor, tmp_path):
    upload = tmp_path / "quiz.txt"
    upload.write_bytes(EXE_BYTES)

    with pytest.raises(FileValidationError):
        quiz_extractor._source_to_text(str(upload))

    assert quiz_extractor.gate_calls == []


def test_genuine_code_upload_is_read_and_gated(quiz_extractor, tmp_path):
    upload = tmp_path / "quiz.py"
    upload.write_bytes(b"def hash_password(pw):\n    pass\n")

    text = quiz_extractor._source_to_text(str(upload))

    assert "hash_password" in text
    assert quiz_extractor.gate_calls == [text]


def test_upload_widget_types_come_from_file_validator(quiz_extractor):
    assert quiz_extractor.SUPPORTED_UPLOAD_EXTENSIONS == sorted(
        file_validator.SUPPORTED_EXTENSIONS
    )
