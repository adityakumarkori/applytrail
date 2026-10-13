"""Phase 5 resume-bytes tests: in-memory PDF parsing, no disk writes."""

import io

import pytest
from pypdf import PdfWriter

from core import resume
from core.resume import (
    EncryptedResumeError,
    ResumeParseError,
    parse_pdf_bytes,
    parse_text,
)


def _blank_pdf_bytes():
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    return buf.getvalue()


def _locked_pdf_bytes():
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret-password")
    writer.write(buf)
    return buf.getvalue()


def test_parse_bytes_uses_injected_reader_content(monkeypatch):
    text = "Java Spring Boot developer with 1.5 years of experience."

    class FakePage:
        def extract_text(self):
            return text

    class FakeReader:
        def __init__(self, _stream):
            self.is_encrypted = False
            self.pages = [FakePage()]

    monkeypatch.setattr(resume, "PdfReader", FakeReader)
    result = parse_pdf_bytes(b"%PDF-1.4 fake-bytes", source="cv.pdf")
    expected = parse_text(text, source="cv.pdf")
    assert result["skills"] == expected["skills"]
    assert result["experience_years"] == 1.5
    assert result["source"] == "cv.pdf"


def test_parse_bytes_rejects_empty_and_non_bytes():
    with pytest.raises(ResumeParseError):
        parse_pdf_bytes(b"")
    with pytest.raises(ResumeParseError):
        parse_pdf_bytes("not-bytes")


def test_parse_bytes_rejects_garbage():
    with pytest.raises(ResumeParseError):
        parse_pdf_bytes(b"definitely not a pdf")


def test_parse_bytes_blank_warns_without_claiming_scanned():
    result = parse_pdf_bytes(_blank_pdf_bytes())
    assert result["skills"] == []
    assert result["warnings"]
    assert "may be" in " ".join(result["warnings"]).lower()


def test_parse_bytes_encrypted_raises():
    with pytest.raises(EncryptedResumeError):
        parse_pdf_bytes(_locked_pdf_bytes())
