"""Phase 4 match tests: overlap scoring, gaps, deterministic ranking."""

import copy
from pathlib import Path

from core import match
from core.match import extract_job_skills, rank_jobs, score_job


def _job(job_id, title, description, work_mode="remote", posted_date=None):
    return {
        "id": job_id,
        "title": title,
        "company": "Acme",
        "location": "Remote",
        "work_mode": work_mode,
        "description": description,
        "source": "remotive",
        "source_url": f"https://example.com/{job_id}",
        "apply_url": f"https://example.com/{job_id}",
        "posted_date": posted_date,
        "fetched_at": "2026-10-13T00:00:00+00:00",
    }


def test_score_is_matched_over_total_times_100():
    job = _job("1", "Software Engineer Opening", "We need Java, Docker, Kafka, Redis.")
    result = score_job(["java", "docker"], job)
    assert result["job_skills"] == ["java", "kafka", "redis", "docker"]
    assert result["matched_skills"] == ["java", "docker"]
    assert result["missing_skills"] == ["kafka", "redis"]
    assert result["score"] == 50


def test_empty_job_skills_scores_zero_with_reason():
    job = _job("2", "Great Opportunity", "Join our amazing growing team today!")
    result = score_job(["java"], job)
    assert result["score"] == 0
    assert result["job_skills"] == []
    assert any("no detectable" in r for r in result["reasons"])


def test_empty_candidate_skills_scores_zero_with_reason():
    job = _job("3", "Software Engineer Opening", "We need Java and Docker.")
    result = score_job([], job)
    assert result["score"] == 0
    assert any("no recorded skills" in r for r in result["reasons"])


def test_full_overlap_scores_100():
    job = _job("4", "Software Engineer Opening", "Java and Docker required.")
    assert score_job(["java", "docker", "kafka"], job)["score"] == 100


def test_java_does_not_match_javascript_in_listing():
    job = _job("5", "Frontend Opening", "JavaScript and React experience needed.")
    result = score_job(["java"], job)
    assert "java" not in result["matched_skills"]
    assert result["score"] == 0


def test_missing_skills_follow_priority_order():
    job = _job("6", "Software Engineer Opening", "Python, Java and Docker needed.")
    result = score_job([], job)
    assert result["missing_skills"] == ["java", "docker", "python"]


def test_score_is_deterministic_across_calls():
    job = _job("7", "Software Engineer Opening", "Java, Docker, Kafka.")
    first = score_job(["java"], job)
    second = score_job(["java"], job)
    assert first == second


def test_inputs_are_never_mutated():
    candidate = ["java", "docker"]
    job = _job("8", "Software Engineer Opening", "Java, Docker, Kafka.")
    snapshot = (list(candidate), copy.deepcopy(job))
    score_job(candidate, job)
    rank_jobs(candidate, [job])
    assert (candidate, job) == snapshot


def test_rank_orders_by_score_then_mode_then_recency():
    low = _job("a", "Opening", "Java, Docker, Kafka, Redis.", posted_date="2026-10-01T00:00:00+00:00")
    high = _job("b", "Opening", "Java, Docker.", posted_date="2026-09-01T00:00:00+00:00")
    onsite = _job("c", "Opening", "Java, Docker.", work_mode="onsite", posted_date="2026-10-01T00:00:00+00:00")
    ranked = rank_jobs(["java", "docker"], [low, onsite, high])
    assert [e["job"]["id"] for e in ranked] == ["b", "c", "a"]


def test_rank_recency_breaks_full_ties_and_missing_dates_last():
    old = _job("a", "Opening", "Java.", posted_date="2026-09-01T00:00:00+00:00")
    new = _job("b", "Opening", "Java.", posted_date="2026-10-01T00:00:00+00:00")
    nodate = _job("c", "Opening", "Java.", posted_date=None)
    ranked = rank_jobs(["java"], [old, nodate, new])
    assert [e["job"]["id"] for e in ranked] == ["b", "a", "c"]


def test_match_result_documents_overlap_not_probability():
    job = _job("9", "Opening", "Java.")
    result = score_job(["java"], job)
    assert result["score"] == 100
    assert isinstance(result["reasons"], list) and result["reasons"]


def test_match_module_imports_stay_minimal():
    src = (Path(__file__).resolve().parent.parent / "core" / "match.py").read_text(
        encoding="utf-8"
    )
    import_lines = [
        line for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]
    blob = "\n".join(import_lines)
    for banned in ("streamlit", "sklearn", "scikit", "requests", "pypdf", "fastapi"):
        assert banned not in blob, f"core/match.py must not import {banned}"
