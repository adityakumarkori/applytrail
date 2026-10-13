"""Phase 3 job-source tests: mocked HTTP only, no live network."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from core import jobs
from core.jobs import (
    SourceError,
    deduplicate,
    deduce_work_mode,
    fetch_adzuna,
    fetch_all_jobs,
    fetch_arbeitnow,
    fetch_remoteok,
    fetch_remotive,
    normalize_adzuna_item,
    normalize_arbeitnow_item,
    normalize_remoteok_item,
    normalize_remotive_item,
)


def _response(json_data, status=200):
    mock = Mock()
    mock.status_code = status
    if status >= 400:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status} Server Error for mocked url"
        )
    else:
        mock.raise_for_status.return_value = None
    mock.json.return_value = json_data
    return mock


ARBEITNOW_PAYLOAD = {
    "data": [
        {
            "slug": "java-dev-1",
            "company_name": "Acme",
            "title": "Java Backend Developer",
            "description": "Spring Boot microservices role",
            "remote": True,
            "url": "https://arbeitnow.com/jobs/java-dev-1",
            "tags": ["java", "backend"],
            "job_types": ["full-time"],
            "location": "Berlin",
            "created_at": 1790812506,
        },
        {
            "slug": "py-dev-2",
            "company_name": "Beta",
            "title": "Python Developer",
            "description": "Django role",
            "remote": False,
            "url": "https://arbeitnow.com/jobs/py-dev-2",
            "tags": ["python"],
            "job_types": [],
            "location": "Munich",
            "created_at": 1790812506,
        },
    ]
}

REMOTEOK_PAYLOAD = [
    {"legal": "notice row, not a job"},
    {
        "id": 123,
        "position": "Senior Backend Engineer",
        "company": "Example Co",
        "tags": ["backend", "java"],
        "location": "Worldwide",
        "url": "https://remoteok.com/remote-jobs/abc-123",
        "description": "Remote Java role",
        "epoch": 1787040007,
    },
]

REMOTIVE_PAYLOAD = {
    "job-count": 1,
    "jobs": [
        {
            "id": 456,
            "url": "https://remotive.com/remote-jobs/software-dev/backend-456",
            "title": "Backend Developer",
            "company_name": "Remo Inc",
            "category": "Software Development",
            "job_type": "full_time",
            "publication_date": "2020-02-15T10:23:26",
            "candidate_required_location": "Worldwide",
            "salary": "$40k - $50k",
            "description": "<p>Remote backend role</p>",
        }
    ],
}

ADZUNA_PAYLOAD = {
    "results": [
        {
            "id": "789",
            "title": "Java Developer",
            "company": {"display_name": "Gamma Ltd"},
            "location": {"display_name": "Bengaluru, India"},
            "description": "Hybrid Java role in Bengaluru",
            "redirect_url": "https://www.adzuna.in/jobs/details/789",
            "created": "2026-09-01T10:00:00Z",
        }
    ]
}


def test_arbeitnow_success_filters_client_side_and_schema():
    with patch("core.jobs.requests.get", return_value=_response(ARBEITNOW_PAYLOAD)):
        found = fetch_arbeitnow("java", limit=20)
    assert len(found) == 1
    job = found[0]
    assert set(job) == set(jobs.JOB_KEYS)
    assert job["source"] == "arbeitnow"
    assert job["apply_url"] == job["source_url"] == "https://arbeitnow.com/jobs/java-dev-1"
    assert job["work_mode"] == "remote"
    assert job["posted_date"] is not None


def test_arbeitnow_malformed_payload_raises():
    with patch("core.jobs.requests.get", return_value=_response({"foo": 1})):
        with pytest.raises(SourceError):
            fetch_arbeitnow("java")


def test_remoteok_skips_legal_notice_and_sends_user_agent():
    with patch("core.jobs.requests.get", return_value=_response(REMOTEOK_PAYLOAD)) as fake:
        found = fetch_remoteok("", limit=20)
    _, kwargs = fake.call_args
    assert "JobStar" in kwargs["headers"]["User-Agent"]
    assert len(found) == 1
    assert found[0]["title"] == "Senior Backend Engineer"
    assert found[0]["work_mode"] == "remote"
    assert "2026" in (found[0]["posted_date"] or "")


def test_remoteok_http_error_raises():
    with patch("core.jobs.requests.get", return_value=_response({}, status=500)):
        with pytest.raises(SourceError):
            fetch_remoteok("java")


def test_remotive_sends_search_limit_and_maps_fields():
    with patch("core.jobs.requests.get", return_value=_response(REMOTIVE_PAYLOAD)) as fake:
        found = fetch_remotive("backend", limit=5)
    _, kwargs = fake.call_args
    assert kwargs["params"]["search"] == "backend"
    assert kwargs["params"]["limit"] == 5
    assert len(found) == 1
    job = found[0]
    assert job["company"] == "Remo Inc"
    assert job["work_mode"] == "remote"
    assert "<p>" in job["description"]  # HTML preserved, not stripped in Phase 3


def test_remotive_timeout_is_source_error():
    with patch(
        "core.jobs.requests.get",
        side_effect=requests.exceptions.ConnectTimeout("mocked timeout"),
    ):
        with pytest.raises(SourceError):
            fetch_remotive("java")


def test_adzuna_without_keys_returns_empty_without_http(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with patch("core.jobs.requests.get") as fake:
        assert fetch_adzuna("java") == []
        fake.assert_not_called()


def test_adzuna_env_fallback_and_mapping(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "env-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "env-key")
    with patch("core.jobs.requests.get", return_value=_response(ADZUNA_PAYLOAD)) as fake:
        found = fetch_adzuna("java", location="India", limit=10)
    _, kwargs = fake.call_args
    assert kwargs["params"]["app_id"] == "env-id"
    assert kwargs["params"]["what"] == "java"
    assert kwargs["params"]["where"] == "India"
    assert found[0]["apply_url"] == "https://www.adzuna.in/jobs/details/789"
    assert found[0]["company"] == "Gamma Ltd"
    assert found[0]["work_mode"] == "hybrid"


def test_adzuna_error_never_exposes_credentials(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "SECRET-ID-1")
    monkeypatch.setenv("ADZUNA_APP_KEY", "SECRET-KEY-2")
    with patch(
        "core.jobs.requests.get",
        side_effect=requests.exceptions.HTTPError(
            "403 for url with app_key=SECRET-KEY-2 and app_id=SECRET-ID-1"
        ),
    ):
        with pytest.raises(SourceError) as excinfo:
            fetch_adzuna("java")
    assert "SECRET-ID-1" not in str(excinfo.value)
    assert "SECRET-KEY-2" not in str(excinfo.value)


def test_adzuna_error_redacts_url_encoded_credentials(monkeypatch):
    import urllib.parse

    # Short app_id '1' also guards replacement order: redacting it first
    # must not corrupt (and thereby preserve part of) the longer key.
    raw_id, raw_key = "1", "s3cr+t/key=1"
    monkeypatch.setenv("ADZUNA_APP_ID", raw_id)
    monkeypatch.setenv("ADZUNA_APP_KEY", raw_key)
    encoded_url = (
        "https://api.adzuna.com/v1/api/jobs/in/search/1?app_id="
        + urllib.parse.quote(raw_id, safe="")
        + "&app_key="
        + urllib.parse.quote(raw_key, safe="")
    )
    with patch(
        "core.jobs.requests.get",
        side_effect=requests.exceptions.HTTPError(f"403 for url: {encoded_url}"),
    ):
        with pytest.raises(SourceError) as excinfo:
            fetch_adzuna("java")
    message = str(excinfo.value)
    for leaked in (
        raw_id,
        raw_key,
        urllib.parse.quote(raw_id, safe=""),
        urllib.parse.quote(raw_key, safe=""),
        urllib.parse.quote_plus(raw_id),
        urllib.parse.quote_plus(raw_key),
    ):
        assert leaked not in message, f"credential form leaked: {leaked!r}"
    assert "403" in message  # useful diagnostics preserved


def test_deduplicate_by_apply_url():
    first = normalize_arbeitnow_item(ARBEITNOW_PAYLOAD["data"][0])
    duplicate = dict(first, source="remoteok", id="remoteok:other")
    assert len(deduplicate([first, duplicate])) == 1


def test_work_mode_hybrid_wins_over_remote_flag():
    assert deduce_work_mode("Hybrid remote role", remote_flag=True) == "hybrid"
    assert deduce_work_mode("Remote worldwide", remote_flag=True) == "remote"
    assert deduce_work_mode("Onsite office role") == "onsite"
    assert deduce_work_mode("Some text") == "unknown"


def test_normalize_skips_items_missing_title_and_url():
    assert normalize_arbeitnow_item({"slug": "x"}) is None
    assert normalize_remoteok_item({"id": 1}) is None
    assert normalize_remotive_item({"id": 2}) is None
    assert normalize_adzuna_item({"id": "3"}) is None


def test_fetch_all_partial_failure_keeps_other_sources(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)

    def fake_get(url, **kwargs):
        if "arbeitnow" in url:
            raise requests.exceptions.ConnectTimeout("mocked arbeitnow down")
        if "remoteok" in url:
            return _response(REMOTEOK_PAYLOAD)
        if "remotive" in url:
            return _response(REMOTIVE_PAYLOAD)
        raise AssertionError(f"unexpected url {url}")

    with patch("core.jobs.requests.get", side_effect=fake_get):
        result = fetch_all_jobs("backend", limit_per_source=20)
    assert {j["source"] for j in result["jobs"]} == {"remoteok", "remotive"}
    assert [e["source"] for e in result["errors"]] == ["arbeitnow"]
    assert result["sources_attempted"] == ["arbeitnow", "remoteok", "remotive", "adzuna"]


def test_jobs_module_imports_stay_minimal():
    src = (Path(__file__).resolve().parent.parent / "core" / "jobs.py").read_text(
        encoding="utf-8"
    )
    import_lines = [
        line
        for line in src.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    blob = "\n".join(import_lines)
    assert "requests" in blob
    for banned in ("streamlit", "sklearn", "scikit", "pypdf", "fastapi"):
        assert banned not in blob, f"core/jobs.py must not import {banned}"
