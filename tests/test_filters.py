"""Phase 4 filter tests: strict experience, role, and location rules."""

import copy
from pathlib import Path

from core.filters import (
    filter_jobs,
    is_eligible,
    is_location_relevant,
    is_role_relevant,
    parse_job_experience,
)


def _job(title, description, location="Remote", work_mode="remote"):
    return {
        "id": "j1",
        "title": title,
        "company": "Acme",
        "location": location,
        "work_mode": work_mode,
        "description": description,
        "source": "remotive",
        "source_url": "https://example.com/j1",
        "apply_url": "https://example.com/j1",
        "posted_date": None,
        "fetched_at": "2026-10-13T00:00:00+00:00",
    }


def _candidate(years=1.5, skills=None, role_hint="backend (java/spring)"):
    return {
        "skills": ["java", "spring boot"] if skills is None else skills,
        "experience_years": years,
        "experience_confidence": "explicit" if years is not None else "unknown",
        "role_hint": role_hint,
    }


def test_parse_range_plus_exact_fresher_unknown():
    assert parse_job_experience(_job("T", "0-2 years experience"))["min_years"] == 0.0
    assert parse_job_experience(_job("T", "3+ years required"))["kind"] == "minimum"
    assert parse_job_experience(_job("T", "2 years experience"))["kind"] == "exact"
    assert parse_job_experience(_job("T", "Freshers welcome!"))["kind"] == "fresher"
    assert parse_job_experience(_job("T", "Great team, apply now"))["kind"] == "unknown"


def test_accept_0_to_1_and_0_to_2_roles():
    assert is_eligible(_job("T", "0-1 years experience"), 0.5)[0] is True
    assert is_eligible(_job("T", "0-2 years experience"), 1.5)[0] is True


def test_accept_0_to_3_only_with_explicit_0_2_evidence():
    ok, _ = is_eligible(_job("T", "0-3 years experience"), 1.5)
    assert ok is True
    ok, reasons = is_eligible(_job("T", "2-3 years experience"), 2.5)
    assert ok is False
    assert any("0–2" in r for r in reasons)


def test_reject_minimum_above_two_years():
    ok, reasons = is_eligible(_job("T", "3+ years of experience"), 1.5)
    assert ok is False
    assert any("above" in r for r in reasons)


def test_reject_seniority_band_above_three():
    ok, _ = is_eligible(_job("T", "2-5 years of experience"), 2.0)
    assert ok is False


def test_exclude_unclear_requirements_by_default():
    ok, reasons = is_eligible(_job("T", "Join our amazing team!"), 1.5)
    assert ok is False
    assert any("unclear" in r for r in reasons)


def test_unknown_candidate_never_becomes_zero():
    ok, _ = is_eligible(_job("T", "0-2 years experience"), None)
    assert ok is True  # min 0 explicitly stated
    ok, reasons = is_eligible(_job("T", "1-2 years experience"), None)
    assert ok is False
    assert any("never assumed zero" in r for r in reasons)


def test_candidate_below_minimum_rejected_with_evidence():
    ok, reasons = is_eligible(_job("T", "2 years of experience"), 1.5)
    assert ok is False
    assert any("evidence" in r for r in reasons)


def test_role_shared_skills_accepted_nontech_rejected():
    ok, _ = is_role_relevant(
        _job("Java Backend Developer", "Spring Boot role"), _candidate()
    )
    assert ok is True
    ok, _ = is_role_relevant(_job("Sales Executive", "Field sales role"), _candidate())
    assert ok is False
    ok, reasons = is_role_relevant(_job("Team Member", "Great role"), _candidate(skills=[]))
    assert ok is True
    assert any("kept for scoring" in r or "unclear" in r for r in reasons)


def test_location_remote_hybrid_india_kept_onsite_abroad_dropped():
    assert is_location_relevant(_job("T", "D", location="Remote", work_mode="remote"))[0] is True
    assert is_location_relevant(_job("T", "D", location="Hybrid", work_mode="hybrid"))[0] is True
    assert is_location_relevant(
        _job("T", "Java role in Bengaluru", location="Bengaluru", work_mode="onsite")
    )[0] is True
    ok, _ = is_location_relevant(
        _job("T", "Java role in Berlin", location="Berlin", work_mode="onsite")
    )
    assert ok is False
    ok, reasons = is_location_relevant(_job("T", "D", location="", work_mode="unknown"))
    assert ok is True
    assert any("flag" in r for r in reasons)


def test_filter_jobs_shape_reasons_and_no_mutation():
    good = _job("Java Backend Developer", "0-2 years, Spring Boot, Remote role")
    bad = _job("Senior Java Developer", "5+ years of experience in Berlin office")
    candidate = _candidate()
    snapshot = (copy.deepcopy(candidate), copy.deepcopy([good, bad]))
    result = filter_jobs([good, bad], candidate)
    assert [e["job"]["title"] for e in result["kept"]] == ["Java Backend Developer"]
    assert [e["job"]["title"] for e in result["rejected"]] == ["Senior Java Developer"]
    assert all(e["reasons"] for e in result["kept"] + result["rejected"])
    assert (candidate, [good, bad]) == snapshot


def test_filters_module_imports_stay_minimal():
    src = (Path(__file__).resolve().parent.parent / "core" / "filters.py").read_text(
        encoding="utf-8"
    )
    import_lines = [
        line for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]
    blob = "\n".join(import_lines)
    for banned in ("streamlit", "sklearn", "scikit", "requests", "pypdf", "fastapi"):
        assert banned not in blob, f"core/filters.py must not import {banned}"
