"""Phase 2 resume tests: cautious parsing, warnings, PDF edge cases."""

import pytest
from pypdf import PdfWriter

from core import resume
from core.resume import (
    EncryptedResumeError,
    ResumeParseError,
    extract_text_from_pdf,
    parse_resume,
    parse_text,
)


JAVA_RESUME = """Aditya Sharma
Backend Developer with 1.5 years of experience in Java, Spring Boot,
Microservices, MySQL and Docker. Built REST APIs with JUnit tests.
"""

RANGE_RESUME = "Software engineer with 0-2 years of experience in Java and Git."
PLUS_RESUME = "Senior profile with 3+ years of experience in Python."
FRESHER_RESUME = "Fresher Backend Developer skilled in Java and Spring Boot."
UNKNOWN_RESUME = "Backend developer skilled in Java, Spring Boot and Docker."


def test_parse_text_java_resume_skills_and_experience():
    result = parse_text(JAVA_RESUME, source="resume.pdf")
    assert "java" in result["skills"]
    assert "spring boot" in result["skills"]
    assert result["experience_years"] == 1.5
    assert result["experience_confidence"] == "explicit"
    assert result["experience_kind"] == "exact"
    assert result["experience_text"] is not None
    assert "1.5" in result["experience_text"]
    assert result["role_hint"] == "backend (java/spring)"
    assert not any("unknown" in w.lower() for w in result["warnings"])


def test_range_uses_lower_bound_never_upper():
    result = parse_text(RANGE_RESUME)
    assert result["experience_years"] == 0.0
    assert result["experience_confidence"] == "explicit"
    assert result["experience_kind"] == "lower_bound"
    assert any("lower bound" in w for w in result["warnings"])


def test_plus_form_uses_lower_bound():
    result = parse_text(PLUS_RESUME)
    assert result["experience_years"] == 3.0
    assert result["experience_kind"] == "lower_bound"
    assert result["experience_confidence"] == "explicit"


def test_fresher_hint_gives_zero_with_hint_confidence_and_warning():
    result = parse_text(FRESHER_RESUME)
    assert result["experience_years"] == 0.0
    assert result["experience_confidence"] == "hint"
    assert result["experience_kind"] == "fresher_hint"
    assert any("hint" in w.lower() for w in result["warnings"])


def test_missing_experience_is_null_never_zero():
    result = parse_text(UNKNOWN_RESUME)
    assert result["experience_years"] is None
    assert result["experience_confidence"] == "unknown"
    assert result["experience_kind"] is None
    assert result["experience_years"] != 0.0
    assert any("not zero" in w or "null" in w for w in result["warnings"])


def test_output_schema_keys_and_types():
    result = parse_text(JAVA_RESUME, source="r.pdf")
    assert set(result) == {
        "source",
        "skills",
        "skill_evidence",
        "experience_years",
        "experience_confidence",
        "experience_kind",
        "experience_text",
        "role_hint",
        "text_chars",
        "warnings",
    }
    assert isinstance(result["skills"], list)
    assert isinstance(result["skill_evidence"], dict)
    assert isinstance(result["warnings"], list)


def test_extract_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf(tmp_path / "nope.pdf")


def test_extract_malformed_file_raises_without_hang(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ResumeParseError):
        extract_text_from_pdf(bad)


def test_extract_encrypted_without_password_raises(tmp_path):
    locked = tmp_path / "locked.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret-password")
    with open(locked, "wb") as fh:
        writer.write(fh)
    with pytest.raises(EncryptedResumeError):
        extract_text_from_pdf(locked)


def test_extract_blank_page_warns_without_claiming_definitely_scanned(tmp_path):
    blank = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(blank, "wb") as fh:
        writer.write(fh)
    text, warnings = extract_text_from_pdf(blank)
    assert text.strip() == ""
    assert warnings, "expected an empty-extraction warning"
    joined = " ".join(warnings).lower()
    assert "may be" in joined
    assert "definitely scanned" not in joined


def test_parse_resume_uses_filename_only_and_merges_warnings(
    tmp_path, monkeypatch
):
    pdf = tmp_path / "MyResume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    resume_text = JAVA_RESUME

    class FakePage:
        def extract_text(self):
            return resume_text

    class FakeReader:
        def __init__(self, _path):
            self.is_encrypted = False
            self.pages = [FakePage()]

    monkeypatch.setattr(resume, "PdfReader", FakeReader)
    result = parse_resume(pdf)
    assert result["source"] == "MyResume.pdf"
    assert "/" not in result["source"] and "\\" not in result["source"]
    assert "java" in result["skills"]
    assert result["experience_years"] == 1.5
