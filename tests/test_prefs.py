"""Phase 5 preference tests: configurable experience window.

Omitted pref_min/pref_max must behave exactly like the locked
0-2 strict / 0-3 conditional policy; explicit values retarget it
(e.g. 3-4) without source changes.
"""

import pytest

from core.filters import filter_jobs, is_eligible


def _job(description):
    return {"title": "T", "description": description}


def test_defaults_match_locked_policy():
    assert is_eligible(_job("0-2 years"), 1.5) == is_eligible(
        _job("0-2 years"), 1.5, None, None
    )
    assert is_eligible(_job("2-3 years"), 2.5) == is_eligible(
        _job("2-3 years"), 2.5, 0, 2
    )
    ok_default, _ = is_eligible(_job("0-2 years"), 1.5)
    ok_explicit, _ = is_eligible(_job("0-2 years"), 1.5, 0, 2)
    assert ok_default is True and ok_explicit is True


def test_3_to_4_target_accepts_matching_roles():
    ok, _ = is_eligible(_job("3-4 years of experience"), 3.5, 3, 4)
    assert ok is True
    ok, _ = is_eligible(_job("3-4 years of experience"), 3.5)  # defaults reject
    assert ok is False


def test_3_to_4_target_still_enforces_minimum_and_band():
    ok, _ = is_eligible(_job("3-4 years of experience"), 2.5, 3, 4)
    assert ok is False  # below stated minimum
    ok, _ = is_eligible(_job("5+ years of experience"), 4.0, 3, 4)
    assert ok is False  # above strict cap
    ok, reasons = is_eligible(_job("3.5-5 years of experience"), 5.0, 2, 4)
    assert ok is False
    assert any("2–4-year eligibility" in r for r in reasons)


def test_unknown_candidate_with_nonzero_target_stays_rejected():
    ok, _ = is_eligible(_job("3-4 years of experience"), None, 3, 4)
    assert ok is False


def test_invalid_window_rejected():
    with pytest.raises(ValueError):
        is_eligible(_job("0-2 years"), 1.0, pref_min=4, pref_max=3)


def test_filter_jobs_honors_preferences():
    job = {
        "id": "j",
        "title": "Java Developer",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "remote",
        "description": "3-4 years of Java experience, remote role",
        "source": "remotive",
        "source_url": "https://example.com/j",
        "apply_url": "https://example.com/j",
        "posted_date": None,
        "fetched_at": "t",
    }
    candidate = {"skills": ["java"], "experience_years": 3.5, "role_hint": None}
    assert len(filter_jobs([job], candidate)["kept"]) == 0  # default 0-2
    assert len(filter_jobs([job], candidate, 3, 4)["kept"]) == 1
