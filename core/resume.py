"""Phase 2 — offline PDF resume parsing and cautious skill/experience hints.

Dependencies: stdlib + `pypdf` + `core.skills` only. No Streamlit,
network, sklearn, or job/matching logic, so the module stays reusable
from a future backend.

Experience policy (conservative):
- Explicit `N years` -> years=N, confidence `explicit`, kind `exact`.
- `N+ years` or range `A-B years` -> years=N (lower bound only),
  confidence `explicit`, kind `lower_bound`. The upper bound is never
  treated as the candidate's actual experience.
- Fresher / entry-level / intern hints -> years=0.0, confidence `hint`,
  kind `fresher_hint`, plus a warning. Missing information never
  becomes 0.0.
- No match -> years=None, confidence `unknown`, plus a warning.
"""

import re
from pathlib import Path

from pypdf import PdfReader

from core.skills import (
    JAVA_ROLE_SKILLS,
    PYTHON_ROLE_SKILLS,
    find_skills,
    skill_evidence,
)

SHORT_TEXT_CHARS = 200

_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:\+)?\s*"
    r"(years?|yrs?|yr|yoe)\b",
    re.IGNORECASE,
)
_PLUS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+\s*(years?|yrs?|yr|yoe)\b", re.IGNORECASE
)
_EXACT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(years?|yrs?|yr|yoe)\b", re.IGNORECASE
)
_FRESHER_RE = re.compile(
    r"\b(freshers?|entry[\s-]?level|entrylevel|interns?(?:hip)?s?|trainee\s?(?:engineer)?)\b",
    re.IGNORECASE,
)


class ResumeParseError(Exception):
    """Base error for unreadable or malformed resume PDFs."""


class EncryptedResumeError(ResumeParseError):
    """Raised when an encrypted PDF cannot be decrypted (empty password)."""


def _role_hint(skills):
    """Suggest a backend role direction from detected skills."""
    found = set(skills)
    java_hits = len(found & set(JAVA_ROLE_SKILLS))
    py_hits = len(found & set(PYTHON_ROLE_SKILLS))
    if java_hits and py_hits and java_hits == py_hits:
        return "backend (java/spring + python/fastapi)"
    if java_hits > py_hits:
        return "backend (java/spring)"
    if py_hits > java_hits:
        return "backend (python/fastapi)"
    if "backend" in found:
        return "backend (general)"
    return None


def _extract_experience(text):
    """Return (years, confidence, kind, matched_text) conservatively.

    Checks ranges first (so `0-2 years` is not misread as exact `2`),
    then `N+`, then exact. Ranges and `+` forms report the lower bound
    with kind `lower_bound`.
    """
    match = _RANGE_RE.search(text)
    if match:
        lower = float(match.group(1))
        return lower, "explicit", "lower_bound", match.group(0).strip()
    match = _PLUS_RE.search(text)
    if match:
        return float(match.group(1)), "explicit", "lower_bound", match.group(0).strip()
    match = _EXACT_RE.search(text)
    if match:
        return float(match.group(1)), "explicit", "exact", match.group(0).strip()
    match = _FRESHER_RE.search(text)
    if match:
        return 0.0, "hint", "fresher_hint", match.group(0).strip()
    return None, "unknown", None, None


def extract_text_from_pdf(path):
    """Extract text from a PDF, returning (text, warnings).

    Raises:
        FileNotFoundError: path does not exist / is not a file.
        EncryptedResumeError: encrypted and empty-password decrypt fails.
        ResumeParseError: malformed PDF or unreadable content.
    """
    pdf_path = Path(path)
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"Resume PDF not found: {pdf_path}")
    try:
        reader = PdfReader(str(pdf_path))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ResumeParseError(f"Cannot read PDF {pdf_path.name}: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            ok = reader.decrypt("")
        except Exception as exc:
            raise EncryptedResumeError(
                f"Encrypted PDF {pdf_path.name} cannot be decrypted: {exc}"
            ) from exc
        if not ok:
            raise EncryptedResumeError(
                f"Encrypted PDF {pdf_path.name} requires a password; "
                "not decrypted with an empty password."
            )

    try:
        pages = reader.pages
    except Exception as exc:
        raise ResumeParseError(f"Cannot read pages of {pdf_path.name}: {exc}") from exc

    chunks = []
    for page in pages:
        try:
            chunk = page.extract_text() or ""
        except Exception as exc:
            raise ResumeParseError(
                f"Text extraction failed for {pdf_path.name}: {exc}"
            ) from exc
        chunks.append(chunk)
    text = "\n".join(chunks)

    warnings = []
    if not text.strip():
        warnings.append(
            "No extractable text found — PDF may be scanned/image-only, "
            "empty, or text extraction failed; manual review needed."
        )
    elif len(text.strip()) < SHORT_TEXT_CHARS:
        warnings.append(
            f"Very little extractable text ({len(text.strip())} chars); "
            "results may be incomplete."
        )
    return text, warnings


def parse_text(text, source=""):
    """Parse already-extracted resume text into a structured dict."""
    raw = text if isinstance(text, str) else ""
    skills = find_skills(raw)
    evidence = skill_evidence(raw)
    years, confidence, kind, matched = _extract_experience(raw)

    warnings = []
    if not raw.strip():
        warnings.append(
            "No extractable text provided — skills and experience unknown."
        )
    if not skills:
        warnings.append("No known skills detected; manual review needed.")
    if confidence == "unknown":
        warnings.append(
            "Experience not found — leaving experience_years as null "
            "(unknown), not zero."
        )
    elif confidence == "hint":
        warnings.append(
            "Entry-level hint detected — experience set to 0.0 with hint "
            "confidence; verify manually."
        )
    elif kind == "lower_bound":
        warnings.append(
            f"Range/minimum {matched!r} detected — using lower bound {years} "
            "as a conservative minimum, not the upper bound."
        )

    return {
        "source": source,
        "skills": skills,
        "skill_evidence": evidence,
        "experience_years": years,
        "experience_confidence": confidence,
        "experience_kind": kind,
        "experience_text": matched,
        "role_hint": _role_hint(skills),
        "text_chars": len(raw.strip()),
        "warnings": warnings,
    }


def parse_resume(path):
    """Extract a PDF and return the structured resume dict."""
    text, extract_warnings = extract_text_from_pdf(path)
    result = parse_text(text, source=Path(path).name)
    # Extraction warnings first, without duplicating identical messages.
    merged = list(extract_warnings)
    for warning in result["warnings"]:
        if warning not in merged:
            merged.append(warning)
    result["warnings"] = merged
    return result
