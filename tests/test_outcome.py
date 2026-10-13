"""Phase 8.3 outcome tests: honest fetch messaging from result data only."""

from app import describe_fetch_outcome


def _result(jobs=(), errors=(), attempted=("a", "b"), counts=None, configured=True):
    return {
        "jobs": list(jobs),
        "errors": list(errors),
        "sources_attempted": list(attempted),
        "source_counts": dict(counts) if counts is not None else {},
        "adzuna_configured": configured,
        "fetched_at": "t",
    }


def _job(job_id="x"):
    return {"id": job_id, "title": "T"}


def test_all_success_names_sources_without_failure_terms():
    outcome = describe_fetch_outcome(
        _result(jobs=[_job("1"), _job("2")], counts={"a": 2, "b": 1})
    )
    assert "a" in outcome["success"] and "b" in outcome["success"]
    assert outcome["sources_failed"] == []
    assert outcome["zero_sources"] == []
    assert outcome["adzuna_skipped"] is False


def test_partial_success_never_claims_failed_sources():
    outcome = describe_fetch_outcome(
        _result(
            jobs=[_job("1")],
            errors=[{"source": "b", "error": "boom"}],
            counts={"a": 1},
        )
    )
    assert "from a." in outcome["success"]
    assert outcome["sources_ok"] == ["a"]
    assert outcome["sources_failed"] == ["b"]


def test_all_failed_says_so_plainly():
    outcome = describe_fetch_outcome(
        _result(
            errors=[{"source": "a", "error": "x"}, {"source": "b", "error": "y"}],
            counts={},
        )
    )
    assert "No jobs fetched" in outcome["success"]
    assert outcome["sources_ok"] == []


def test_zero_result_sources_listed_only_when_known():
    outcome = describe_fetch_outcome(
        _result(jobs=[_job()], counts={"a": 1, "b": 0})
    )
    assert outcome["zero_sources"] == ["b"]
    legacy = describe_fetch_outcome(
        {"jobs": [_job()], "errors": [], "sources_attempted": ["a", "b"]}
    )
    assert legacy["zero_sources"] == []  # no counts: no guessing


def test_unconfigured_adzuna_skipped_not_failed_or_empty():
    outcome = describe_fetch_outcome(
        _result(
            jobs=[_job()],
            attempted=("a", "adzuna"),
            counts={"a": 1, "adzuna": 0},
            configured=False,
        )
    )
    assert outcome["adzuna_skipped"] is True
    assert "adzuna" not in outcome["success"]
    assert outcome["zero_sources"] == []


def test_configured_adzuna_zero_counts_as_empty():
    outcome = describe_fetch_outcome(
        _result(
            attempted=("adzuna",),
            counts={"adzuna": 0},
            configured=True,
        )
    )
    assert outcome["zero_sources"] == ["adzuna"]
    assert outcome["adzuna_skipped"] is False


def test_dedup_note_only_when_counts_exceed_jobs():
    outcome = describe_fetch_outcome(
        _result(jobs=[_job("1")], counts={"a": 1, "b": 1})
    )
    assert "uplicate" in outcome["success"]
    plain = describe_fetch_outcome(
        _result(jobs=[_job("1"), _job("2")], counts={"a": 1, "b": 1})
    )
    assert "uplicate" not in plain["success"]
