"""
Tests for upload file validation helpers.
"""
from file_utils import detect_mime_from_header


def test_detect_mime_from_header_detects_pdf():
    assert detect_mime_from_header(b"%PDF-1.7\nbody") == "application/pdf"


def test_detect_mime_from_header_detects_text():
    assert detect_mime_from_header(b"plain contract text") == "text/plain"


def test_detect_mime_from_header_rejects_binary_without_supported_signature():
    assert detect_mime_from_header(b"\x00\x01not-a-supported-file") is None
