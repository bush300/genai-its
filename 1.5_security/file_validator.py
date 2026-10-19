"""Content-based upload validation (Security Module 7).

A file's extension, and the MIME type the browser sends, are chosen by the
uploader and can't be trusted. This module checks what a file actually *is*
from its bytes before it reaches a parser or the LLM:

- PDFs and images are identified by their magic bytes using `filetype`.
- Text and code have no magic bytes, so they are accepted only if the content
  contains no NUL bytes. NUL bytes are a reliable sign of binary data (e.g. an
  .exe or .zip renamed to .txt). `filetype` is deliberately not used for text:
  it has no text signatures and some of its checks are loose (a text file that
  starts with "BM" is reported as a BMP image).

A file is rejected when its content doesn't match the kind its extension claims.
"""

from __future__ import annotations

from pathlib import Path

import filetype


# Supported upload types, grouped by how they are processed.
# This is the single list of accepted types: quiz_extractor.py and the upload
# widgets in streamlit_app.py read from here.
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
    ".html", ".css", ".json", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".sql",
}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | TEXT_EXTENSIONS

# MIME types (as reported by `filetype`) that each binary kind may contain.
# Any supported image format is accepted for any image extension, since e.g. a
# PNG saved as .jpg is harmless and the OCR step handles both.
_ALLOWED_MIMES = {
    "pdf": {"application/pdf"},
    "image": {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/tiff"},
}


class FileValidationError(ValueError):
    """Raised when an upload's content is unsupported or doesn't match its extension."""


def _kind_from_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS:
        return "text"
    raise FileValidationError(f"Unsupported file type: {ext or 'unknown'}")


def validate_upload(data: bytes, filename: str) -> str:
    """Check an upload's content and return its kind: "pdf", "image" or "text".

    Args:
        data: The file's raw bytes.
        filename: The original filename (used only for the claimed extension).

    Raises:
        FileValidationError: If the type is unsupported, the file is empty, or
            the content doesn't match the extension.
    """
    claimed_kind = _kind_from_extension(filename)

    if not data:
        raise FileValidationError(f"'{filename}' is empty.")

    if claimed_kind == "text":
        if b"\x00" in data:
            raise FileValidationError(
                f"'{filename}' has a text/code extension but contains binary data."
            )
        return "text"

    guess = filetype.guess(data)
    detected = guess.mime if guess else "unknown or text content"
    if detected not in _ALLOWED_MIMES[claimed_kind]:
        raise FileValidationError(
            f"'{filename}' claims to be a {claimed_kind.upper()} file "
            f"but its content is {detected}."
        )
    return claimed_kind
