"""Phase 5.1 profile tests: malformed values never crash, defaults restored."""

import math

import pytest

from app import sanitize_profile


def test_valid_profile_preserved_without_warnings():
    raw = {
        "exp_pref_min": 3,
        "exp_pref_max": 4,
        "query": "spring",
        "skills": ["java", "python"],
        "experience_years": 1.5,
    }
    clean, warnings = sanitize_profile(raw)
    assert warnings == []
    assert clean == {
        "exp_pref_min": 3.0,
        "exp_pref_max": 4.0,
        "query": "spring",
        "skills": ["java", "python"],
        "experience_years": 1.5,
        "target_roles": [],
        "min_score": 0,
        "posted_within": None,
    }


def test_non_dict_profile_restored_to_defaults():
    for bad in (None, [], "prefs", 42):
        clean, warnings = sanitize_profile(bad)
        assert clean["exp_pref_min"] == 0.0
        assert clean["exp_pref_max"] == 2.0
        assert clean["experience_years"] is None
        assert warnings


def test_wrong_typed_prefs_restored_sibling_preserved():
    clean, warnings = sanitize_profile({"exp_pref_min": "lots", "exp_pref_max": 4})
    assert clean["exp_pref_min"] == 0.0
    assert clean["exp_pref_max"] == 4.0
    assert len(warnings) == 1
    for bad in (True, None, float("nan"), float("inf"), -1, 21):
        clean, warnings = sanitize_profile({"exp_pref_min": bad})
        assert clean["exp_pref_min"] == 0.0
        assert warnings


def test_inverted_range_resets_both_to_defaults():
    clean, warnings = sanitize_profile({"exp_pref_min": 5, "exp_pref_max": 2})
    assert (clean["exp_pref_min"], clean["exp_pref_max"]) == (0.0, 2.0)
    assert warnings


def test_boundary_prefs_accepted():
    clean, warnings = sanitize_profile({"exp_pref_min": 0, "exp_pref_max": 20})
    assert (clean["exp_pref_min"], clean["exp_pref_max"]) == (0.0, 20.0)
    assert warnings == []


def test_skills_query_experience_coerced_conservatively():
    clean, warnings = sanitize_profile(
        {
            "query": 123,
            "skills": ["java", "cobol", 42, None],
            "experience_years": "a lot",
        }
    )
    assert clean["query"] == "java"
    assert clean["skills"] == ["java"]
    assert clean["experience_years"] is None
    assert warnings  # unknown skill entries reported
    for bad_years in (True, float("nan"), -1, 31):
        clean, _ = sanitize_profile({"experience_years": bad_years})
        assert clean["experience_years"] is None
    clean, _ = sanitize_profile({"experience_years": 0})
    assert clean["experience_years"] == 0.0


def test_sanitized_prefs_fit_widgets_and_filters():
    from core.filters import filter_jobs

    clean, _ = sanitize_profile({"exp_pref_min": -5, "exp_pref_max": "x"})
    assert 0.0 <= clean["exp_pref_min"] <= clean["exp_pref_max"] <= 20.0
    job = {
        "id": "j",
        "title": "Java Developer",
        "company": "A",
        "location": "Remote",
        "work_mode": "remote",
        "description": "0-2 years Java",
        "source": "s",
        "source_url": "u",
        "apply_url": "u",
        "posted_date": None,
        "fetched_at": "t",
    }
    candidate = {"skills": ["java"], "experience_years": 1.0, "role_hint": None}
    result = filter_jobs(
        [job], candidate, clean["exp_pref_min"], clean["exp_pref_max"]
    )
    assert len(result["kept"]) == 1


def test_no_nan_or_bool_leaks_into_numbers():
    clean, _ = sanitize_profile({"exp_pref_min": float("nan")})
    assert not math.isnan(clean["exp_pref_min"])


def test_empty_profile_produces_zero_warnings_with_defaults():
    clean, warnings = sanitize_profile({})
    assert warnings == []
    assert clean == {
        "exp_pref_min": 0.0,
        "exp_pref_max": 2.0,
        "query": "java",
        "skills": [],
        "experience_years": None,
        "target_roles": [],
        "min_score": 0,
        "posted_within": None,
    }


def test_missing_keys_use_defaults_silently():
    clean, warnings = sanitize_profile({"query": "spring", "skills": ["java"]})
    assert warnings == []
    assert (clean["exp_pref_min"], clean["exp_pref_max"]) == (0.0, 2.0)
    assert clean["experience_years"] is None
    assert clean["query"] == "spring"
    assert clean["skills"] == ["java"]


def test_present_but_invalid_prefs_still_warn():
    clean, warnings = sanitize_profile({"exp_pref_min": -1})
    assert (clean["exp_pref_min"], clean["exp_pref_max"]) == (0.0, 2.0)
    assert len(warnings) == 1
    assert "minimum" in warnings[0].lower()
    clean, warnings = sanitize_profile({"exp_pref_min": 5})
    assert (clean["exp_pref_min"], clean["exp_pref_max"]) == (0.0, 2.0)
    assert warnings  # inverted range against the silent default still resets


def test_new_fields_valid_values_preserved():
    clean, warnings = sanitize_profile(
        {
            "exp_pref_min": 0,
            "exp_pref_max": 2,
            "target_roles": ["Backend", " Java Developer "],
            "min_score": 40,
            "posted_within": 7,
        }
    )
    assert warnings == []
    assert clean["target_roles"] == ["Backend", "Java Developer"]
    assert clean["min_score"] == 40
    assert clean["posted_within"] == 7


def test_new_fields_malformed_values_restored():
    clean, warnings = sanitize_profile(
        {
            "exp_pref_min": 0,
            "exp_pref_max": 2,
            "target_roles": "backend",
            "min_score": 150,
            "posted_within": 5,
        }
    )
    assert clean["target_roles"] == []
    assert clean["min_score"] == 0
    assert clean["posted_within"] is None
    assert len(warnings) == 3
    clean, warnings = sanitize_profile(
        {"target_roles": ["ok", "", None, 42], "min_score": True, "posted_within": "7"}
    )
    assert clean["target_roles"] == ["ok"]
    assert clean["min_score"] == 0
    assert clean["posted_within"] is None
    assert warnings
