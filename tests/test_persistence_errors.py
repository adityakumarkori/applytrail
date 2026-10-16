"""Phase 8.1 persistence-error tests: OSError/TypeError handled per store.

All storage I/O is faked or monkeypatched; no real files are touched
and no network calls are made.
"""

import json
from unittest.mock import patch

import pytest

import storage
from app import save_fetch_cache


def _profile():
    return {
        "exp_pref_min": 0.0,
        "exp_pref_max": 2.0,
        "query": "java",
        "skills": ["java"],
        "experience_years": 1.5,
        "target_roles": [],
        "min_score": 0,
        "posted_within": None,
    }


def test_fetch_cache_oserror_first_store_second_still_attempted(monkeypatch):
    calls = []

    def fake_save(name, data):
        calls.append(name)
        if name == "cached_jobs":
            raise OSError("disk full (simulated)")

    monkeypatch.setattr("storage.save_store", fake_save)
    errors = save_fetch_cache("java", [], "t", _profile())
    assert len(errors) == 1
    assert "cached jobs" in errors[0]
    assert calls == ["cached_jobs", "profile"]


def test_fetch_cache_oserror_second_store_first_persisted(monkeypatch):
    written = {}

    def fake_save(name, data):
        if name == "profile":
            raise OSError("read-only filesystem (simulated)")
        written[name] = data

    monkeypatch.setattr("storage.save_store", fake_save)
    errors = save_fetch_cache("java", [{"id": "x"}], "t", _profile())
    assert len(errors) == 1
    assert "profile" in errors[0]
    assert written["cached_jobs"]["jobs"] == [{"id": "x"}]


def test_fetch_cache_genuine_typeerror_reported(monkeypatch):
    def real_json_save(name, data):
        json.dumps(data)  # raises TypeError for sets and friends

    monkeypatch.setattr("storage.save_store", real_json_save)
    errors = save_fetch_cache("java", [{1, 2}], "t", _profile())
    assert len(errors) == 1
    assert "cached jobs" in errors[0]


def test_fetch_cache_success_writes_both(monkeypatch):
    written = {}
    monkeypatch.setattr(
        "storage.save_store", lambda name, data: written.setdefault(name, data)
    )
    assert save_fetch_cache("java", [1], "t", _profile()) == []
    assert set(written) == {"cached_jobs", "profile"}


def test_fetch_cache_unexpected_errors_propagate(monkeypatch):
    def buggy_save(name, data):
        raise RuntimeError("programming error (simulated)")

    monkeypatch.setattr("storage.save_store", buggy_save)
    with pytest.raises(RuntimeError):
        save_fetch_cache("java", [], "t", _profile())


def test_toggle_saved_oserror_and_typeerror_without_rerun(monkeypatch):
    from app import _toggle_saved

    monkeypatch.setattr("app.st.rerun", lambda: (_ for _ in ()).throw(AssertionError("rerun")))
    job = {
        "id": "s:1",
        "title": "T",
        "source": "s",
        "apply_url": "https://example.com/1",
    }
    for failure in (OSError("disk full (simulated)"), TypeError("bad payload")):
        monkeypatch.setattr(
            "storage.save_store",
            lambda name, data: (_ for _ in ()).throw(failure),
        )
        _toggle_saved("https://example.com/1", True, job, None)  # error shown, no raise


def test_toggle_saved_valueerror_preserved_and_writes_nothing(monkeypatch):
    from app import _toggle_saved

    monkeypatch.setattr("app.st.rerun", lambda: (_ for _ in ()).throw(AssertionError("rerun")))
    calls = []
    monkeypatch.setattr(
        "storage.save_store", lambda name, data: calls.append(name)
    )
    _toggle_saved("k", True, {"title": "anonymous"}, None)  # no stable identity
    assert calls == []


def test_toggle_saved_success_reruns(monkeypatch):
    from app import _toggle_saved

    written = {}
    reruns = []
    monkeypatch.setattr(
        "storage.save_store", lambda name, data: written.setdefault(name, data)
    )
    monkeypatch.setattr("app.st.rerun", lambda: reruns.append(True))
    job = {
        "id": "s:1",
        "title": "T",
        "source": "s",
        "apply_url": "https://example.com/1",
    }
    _toggle_saved("https://example.com/1", True, job, {"score": 10})
    assert reruns == [True]
    assert list(written["saved_jobs"]["jobs"]) == ["https://example.com/1"]


def test_save_preferences_oserror_shown_in_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def boom(name, data):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("storage.save_store", boom)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        at = AppTest.from_file("app.py").run(timeout=30)
        assert not at.exception, at.exception
        save_button = next(b for b in at.button if b.label == "Save preferences")
        save_button.click().run(timeout=30)
    assert not at.exception, at.exception
    assert any("not saved" in str(error.value) for error in at.error)


def test_save_preferences_success_without_network(monkeypatch):
    from streamlit.testing.v1 import AppTest

    written = {}
    monkeypatch.setattr(
        "storage.save_store", lambda name, data: written.setdefault(name, data)
    )
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        at = AppTest.from_file("app.py").run(timeout=30)
        assert not at.exception, at.exception
        save_button = next(b for b in at.button if b.label == "Save preferences")
        save_button.click().run(timeout=30)
    assert not at.exception, at.exception
    assert written["profile"]["exp_pref_min"] == 0.0
    assert any("saved locally" in str(s.value).lower() for s in at.success)


def test_fetch_handler_cache_typeerror_still_shows_jobs(monkeypatch):
    from streamlit.testing.v1 import AppTest

    fetched = {
        "jobs": [
            {
                "id": "a",
                "title": "Java Dev",
                "company": "Acme",
                "location": "Remote",
                "work_mode": "remote",
                "description": "0-2 years Java",
                "source": "remotive",
                "source_url": "https://example.com/a",
                "apply_url": "https://example.com/a",
                "posted_date": None,
                "fetched_at": "t",
            }
        ],
        "errors": [],
        "sources_attempted": ["remotive"],
        "fetched_at": "t",
    }

    def boom(name, data):
        raise TypeError("unserializable payload (simulated)")

    monkeypatch.setattr("storage.save_store", boom)
    with patch("core.jobs.fetch_all_jobs", return_value=fetched):
        at = AppTest.from_file("app.py").run(timeout=30)
        assert not at.exception, at.exception
        fetch_button = next(b for b in at.button if b.label == "Fetch / refresh jobs")
        fetch_button.click().run(timeout=30)
    assert not at.exception, at.exception
    assert any("cache failed" in str(w.value) for w in at.warning)
    assert any("Fetched 1 jobs" in str(s.value) for s in at.success)
