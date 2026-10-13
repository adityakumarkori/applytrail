"""Phase 5 view-model tests: merge, local-only filter/sort, no refetch."""

import copy
from unittest.mock import patch

from core import views
from core.views import (
    apply_local_filters,
    attach_filter_info,
    sort_results,
)


def _entry(job_id, title, company, location, mode, source, job_skills, score):
    return {
        "job": {
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "work_mode": mode,
            "description": f"{title} role",
            "source": source,
            "source_url": f"https://example.com/{job_id}",
            "apply_url": f"https://example.com/{job_id}",
            "posted_date": None,
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


def _entries():
    return [
        _entry("a", "Java Backend Developer", "Acme", "Remote", "remote", "remotive", ["java"], 80),
        _entry("b", "Python Developer", "Beta", "Bengaluru", "onsite", "adzuna", ["python"], 40),
        _entry("c", "Java Intern", "Gamma", "Hybrid Hub", "hybrid", "remoteok", ["java", "git"], 60),
    ]


def test_attach_merges_reasons_flags_by_id_without_mutation():
    ranked = [
        {"job": {"id": "a", "title": "T"}, "match": {"score": 10}},
        {"job": {"id": "zzz", "title": "U"}, "match": {"score": 5}},
    ]
    filtered = {"kept": [{"job": {"id": "a"}, "reasons": ["r1"], "flags": ["needs-review"]}]}
    snapshot = copy.deepcopy((ranked, filtered))
    merged = attach_filter_info(ranked, filtered)
    assert merged[0]["reasons"] == ["r1"]
    assert merged[0]["flags"] == ["needs-review"]
    assert merged[1]["reasons"] == [] and merged[1]["flags"] == []
    assert (ranked, filtered) == snapshot


def test_local_filters_narrow_without_network():
    entries = _entries()
    assert len(apply_local_filters(entries)) == 3  # empty means all
    assert [e["job"]["id"] for e in apply_local_filters(entries, role_keyword="python")] == ["b"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, skills=["git"])] == ["c"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, location="bengal")] == ["b"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, work_modes=["remote"])] == ["a"]
    assert [e["job"]["id"] for e in apply_local_filters(entries, sources=["adzuna"])] == ["b"]
    assert apply_local_filters(entries, role_keyword="cobol") == []
    assert apply_local_filters(["junk", None]) == []


def test_sort_options_are_local_and_stable():
    entries = _entries()
    assert [e["job"]["id"] for e in sort_results(entries, "Match score")] == ["a", "b", "c"]
    assert [e["job"]["id"] for e in sort_results(entries, "Company A–Z")] == ["a", "b", "c"]
    dated = [
        _entry("old", "T", "Zed", "R", "remote", "s", [], 0),
        _entry("new", "T", "Zed", "R", "remote", "s", [], 0),
    ]
    dated[0]["job"]["posted_date"] = "2026-09-01T00:00:00+00:00"
    dated[1]["job"]["posted_date"] = "2026-10-01T00:00:00+00:00"
    assert [e["job"]["id"] for e in sort_results(dated, "Newest first")] == ["new", "old"]


def test_filter_sort_pipeline_never_touches_network():
    from app import build_results

    raw = [
        {
            "id": "a",
            "title": "Java Backend Developer",
            "company": "Acme",
            "location": "Remote",
            "work_mode": "remote",
            "description": "0-2 years Java role",
            "source": "remotive",
            "source_url": "https://example.com/a",
            "apply_url": "https://example.com/a",
            "posted_date": None,
            "fetched_at": "t",
        }
    ]
    candidate = {"skills": ["java"], "experience_years": 1.0, "role_hint": None}
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("must not fetch")):
        merged, rejected = build_results(raw, candidate, 0, 2)
        shown = sort_results(apply_local_filters(merged, role_keyword="java"), "Match score")
    assert [e["job"]["id"] for e in shown] == ["a"]
    assert rejected == []
