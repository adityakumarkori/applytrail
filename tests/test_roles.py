"""Phase 6 role/save tests: target roles, advanced filters, offline save."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import build_profile_payload, save_preferences
from core.views import apply_local_filters, match_roles, posted_age_days


def _entry(job_id, title, score, job_skills, posted_date="2026-10-01T00:00:00+00:00"):
    return {
        "job": {
            "id": job_id,
            "title": title,
            "company": "Acme",
            "location": "Remote",
            "work_mode": "remote",
            "description": f"{title} role",
            "source": "remotive",
            "source_url": f"https://example.com/{job_id}",
            "apply_url": f"https://example.com/{job_id}",
            "posted_date": posted_date,
            "fetched_at": "t",
        },
        "match": {
            "score": score,
            "matched_skills": list(job_skills),
            "missing_skills": [],
            "job_skills": list(job_skills),
            "primary_hits": 0,
            "reasons": [],
        },
    }


def _recent(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_match_roles_empty_means_no_restriction():
    job = {"title": "Anything At All"}
    assert match_roles(job, []) is True
    assert match_roles(job, None) is True


def test_match_roles_case_insensitive_substring_any():
    job = {"title": "Senior JAVA Backend Developer"}
    assert match_roles(job, ["java"]) is True
    assert match_roles(job, ["python", "backend"]) is True
    assert match_roles(job, ["  BACKEND  "]) is True
    assert match_roles(job, ["back end"]) is False  # no such substring
    assert match_roles(job, ["golang"]) is False


def test_match_roles_handles_invalid_titles():
    assert match_roles({"title": None}, ["java"]) is False
    assert match_roles({}, ["java"]) is False
    assert match_roles(None, ["java"]) is False
    assert match_roles("not-a-dict", ["java"]) is False
    assert match_roles({"title": "Java Dev"}, ["", "  ", None, 42]) is True


def test_min_score_boundaries_inclusive():
    entries = [
        _entry("a", "T", 80, ["java"]),
        _entry("b", "T", 40, ["java"]),
    ]
    assert [e["job"]["id"] for e in apply_local_filters(entries, min_score=0)] == ["a", "b"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, min_score=40)] == ["a", "b"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, min_score=41)] == ["a"]
    assert apply_local_filters(entries, min_score=100) == []
    assert len(apply_local_filters(entries, min_score="junk")) == 2


def test_skill_match_modes_and_default_parity():
    entries = [_entry("a", "T", 50, ["java", "docker"])]
    default = apply_local_filters(entries, skills=["java", "kafka"])
    assert [e["job"]["id"] for e in default] == ["a"]  # any: java hits
    assert apply_local_filters(entries, skills=["java", "kafka"], skill_match="all") == []
    assert apply_local_filters(
        entries, skills=["java", "docker"], skill_match="all"
    )[0]["job"]["id"] == "a"
    assert apply_local_filters(entries, skills=["java"], skill_match="weird") == default


def test_recency_windows_and_unknown_dates():
    entries = [
        _entry("new", "T", 50, [], _recent(2)),
        _entry("edge-in", "T", 50, [], _recent(6.9)),
        _entry("edge-out", "T", 50, [], _recent(7.2)),
        _entry("old", "T", 50, [], _recent(40)),
        _entry("nodate", "T", 50, [], None),
        _entry("baddate", "T", 50, [], "not-a-date"),
        _entry("emptydate", "T", 50, [], "   "),
    ]
    assert len(apply_local_filters(entries)) == 7  # None = no restriction
    week = apply_local_filters(entries, posted_within_days=7)
    assert [e["job"]["id"] for e in week] == ["new", "edge-in"]
    month = apply_local_filters(entries, posted_within_days=30)
    assert [e["job"]["id"] for e in month] == ["new", "edge-in", "edge-out"]
    assert posted_age_days(None) is None
    assert posted_age_days("garbage") is None
    assert posted_age_days(12345) is None


def test_target_roles_narrow_local_results():
    entries = [
        _entry("a", "Java Backend Developer", 80, ["java"]),
        _entry("b", "Python Developer", 70, ["python"]),
    ]
    assert [e["job"]["id"] for e in apply_local_filters(entries, target_roles=["java"])] == ["a"]
    assert len(apply_local_filters(entries, target_roles=[])) == 2


def test_build_profile_payload_valid_and_invalid():
    payload = build_profile_payload(0, 2, "java", ["java"], 1.5, ["Backend"], 40, 7)
    assert payload["target_roles"] == ["Backend"]
    assert payload["min_score"] == 40
    assert payload["posted_within"] == 7
    with pytest.raises(ValueError):
        build_profile_payload(4, 2, "java", [], None, [], 0, None)
    with pytest.raises(ValueError):
        build_profile_payload(0, 2, "java", [], None, [], 150, None)
    with pytest.raises(ValueError):
        build_profile_payload(0, 2, "java", [], None, [], 0, 5)


def test_save_preferences_persists_without_network(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "storage.save_store",
        lambda name, data: saved.setdefault("args", (name, data)),
    )
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        payload = build_profile_payload(3, 4, "spring", ["java"], None, ["Backend"], 50, 14)
        save_preferences(payload)
    assert saved["args"][0] == "profile"
    assert saved["args"][1]["target_roles"] == ["Backend"]
    assert saved["args"][1]["posted_within"] == 14
