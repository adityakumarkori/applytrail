"""Phase 8.4 hardening tests: AppTest render, FS errors, evidence parity.

No real user data is touched (all storage calls patched) and no live
network calls are made (fetch raises if ever invoked).
"""

import os
from unittest.mock import patch

import pytest

import config
import storage


def _isolate(monkeypatch, stores=None):
    """Patch storage I/O to an in-memory backing (no real files)."""
    backing = dict(stores or {})

    def fake_load(name, default):
        return backing.get(name, default)

    def fake_save(name, data):
        backing[name] = data
        return name

    monkeypatch.setattr("storage.save_store", fake_save)
    monkeypatch.setattr("storage.load_store", fake_load)
    return backing


def _run_app_guarded():
    from streamlit.testing.v1 import AppTest

    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        at = AppTest.from_file("app.py").run()
    assert not at.exception, at.exception
    return at


def test_fresh_install_renders_without_preference_warnings(monkeypatch):
    _isolate(monkeypatch)
    at = _run_app_guarded()
    assert at.title[0].value == config.APP_NAME
    restored = [
        warning.value
        for warning in at.warning
        if "invalid" in str(warning.value) or "restored" in str(warning.value)
    ]
    assert restored == []


def test_malformed_profile_renders_with_warnings_not_crash(monkeypatch):
    _isolate(
        monkeypatch,
        stores={
            "profile": {
                "exp_pref_min": -5,
                "exp_pref_max": "lots",
                "query": 123,
                "skills": ["java", "cobol"],
                "experience_years": "x",
            }
        },
    )
    at = _run_app_guarded()
    assert at.title[0].value == config.APP_NAME
    assert any("restored" in str(warning.value) for warning in at.warning)


def test_atomic_replace_failure_propagates_and_cleans_tmp(monkeypatch, tmp_path):
    target = tmp_path / "store.json"
    target.write_text('{"kept": true}', encoding="utf-8")

    def boom(src, dst):
        raise PermissionError("read-only destination (simulated)")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(PermissionError):
        storage.save_json(target, {"new": True})
    assert list(tmp_path.glob("store.json.*")) == []  # tmp cleaned up
    with open(target, "rb") as handle:
        assert handle.read() == b'{"kept": true}'  # original intact


def test_unreadable_file_surfaces_as_storage_error(monkeypatch, tmp_path):
    target = tmp_path / "store.json"
    target.write_text('{"a": 1}', encoding="utf-8")

    def boom(self, *args, **kwargs):
        raise PermissionError("read denied (simulated)")

    monkeypatch.setattr("pathlib.Path.read_text", boom)
    with pytest.raises(storage.StorageError):
        storage.load_json(target, {})
    with open(target, "rb") as handle:
        assert handle.read() == b'{"a": 1}'  # file itself untouched


def test_permission_error_on_both_stores_named(monkeypatch):
    from app import save_tracking_state

    def boom(name, data):
        raise PermissionError("denied (simulated)")

    monkeypatch.setattr("storage.save_store", boom)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        ok, errors = save_tracking_state({"version": 1, "jobs": {}}, {"version": 1})
    assert ok is False
    assert len(errors) == 2
    assert any("saved jobs" in error for error in errors)
    assert any("applications" in error for error in errors)


def test_explicit_0_2_is_prefs_independent_documented():
    from core.filters import is_eligible, parse_job_experience

    def job(text):
        return {"title": "T", "description": text}

    # The field is 0-2-relative by construction and takes no prefs.
    assert parse_job_experience(job("0-3 years"))["explicit_0_2"] is True
    assert parse_job_experience(job("2-3 years"))["explicit_0_2"] is False
    # Default 0-2 policy consumes it: 0-3 accept, 2-3 reject.
    assert is_eligible(job("0-3 years"), 1.5)[0] is True
    assert is_eligible(job("2-3 years"), 2.5)[0] is False
    # Custom 0-5 band generalizes: max within band, low minimum accepted.
    assert is_eligible(job("0-5 years"), 1.0, 0, 5)[0] is True
    assert is_eligible(job("4-6 years"), 4.5, 0, 5)[0] is False
    # Custom 4-5 band: explicit flag still 0-2-relative, eligibility decides.
    assert parse_job_experience(job("4-5 years"))["explicit_0_2"] is False
    assert is_eligible(job("4-5 years"), 4.5, 4, 5)[0] is True
    assert is_eligible(job("4-5 years"), None, 4, 5)[0] is False  # unknown stays out
    # Flag True never overrides the candidate minimum or unclear rules.
    assert is_eligible(job("1-2 years"), 0.0)[0] is False
    assert is_eligible(job("Freshers welcome, 3+ years"), 0.0)[0] is False
    assert is_eligible(job("Join our amazing team"), 1.0)[0] is False


def test_persistence_failure_paths_still_honest(monkeypatch):
    from app import save_tracking_state

    calls = []

    def fake_save(name, data):
        calls.append(name)
        if name == "applications":
            raise OSError("disk full (simulated)")

    monkeypatch.setattr("storage.save_store", fake_save)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        ok, errors = save_tracking_state({"version": 1, "jobs": {}}, {})
    assert ok is False
    assert calls == ["saved_jobs", "applications"]
    assert any("applications" in error for error in errors)

    def buggy_save(name, data):
        raise RuntimeError("programming error (simulated)")

    monkeypatch.setattr("storage.save_store", buggy_save)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        with pytest.raises(RuntimeError):
            save_tracking_state({}, {})
