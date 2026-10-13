"""Phase 7 tracking tests: keys, records, validation, letters. No network."""

import copy
from pathlib import Path

import pytest

from core import tracking
from core.tracking import (
    clean_application_store,
    clean_saved_store,
    draft_cover_letter,
    ensure_snapshot,
    new_application_store,
    new_saved_store,
    normalize_url,
    remove_application,
    remove_job,
    save_job,
    set_applied_date,
    set_cover_letter,
    set_notes,
    set_status,
    tracking_key,
    validate_application,
    validate_saved_record,
)


def _job(**overrides):
    job = {
        "id": "remotive:1",
        "title": "Java Developer",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "remote",
        "description": "Java role",
        "source": "remotive",
        "source_url": "https://remotive.com/remote-jobs/a-1",
        "apply_url": "https://remotive.com/remote-jobs/a-1",
        "posted_date": None,
        "fetched_at": "t",
    }
    job.update(overrides)
    return job


def test_key_prefers_apply_url_and_normalizes_host():
    assert (
        tracking_key(_job(apply_url="HTTPS://Example.COM:443/a?x=1#frag"))
        == "https://example.com:443/a?x=1"
    )


def test_key_preserves_path_and_query_case():
    assert (
        tracking_key(_job(apply_url="https://x.com/Jobs/ABC?Id=42", source_url=None))
        == "https://x.com/Jobs/ABC?Id=42"
    )


def test_key_falls_back_to_source_id_only_when_both_valid():
    job = _job(apply_url=None, source_url="  ", id="s:9", source="s")
    assert tracking_key(job) == "s:s:9"
    assert tracking_key(_job(apply_url=None, source_url=None, id="", source="s")) is None
    assert tracking_key(_job(apply_url=None, source_url=None, id="1", source="")) is None
    assert tracking_key(_job(apply_url="notaurl", source_url="x", id="", source="")) is None
    assert tracking_key(None) is None
    assert tracking_key("junk") is None


def test_save_dedupes_and_never_mutates():
    saved = new_saved_store()
    snapshot = (_job(), {"score": 80})
    first = save_job(saved, *snapshot)
    second = save_job(first, *snapshot)
    assert saved == new_saved_store()
    assert len(first["jobs"]) == 1 == len(second["jobs"])
    assert list(second["jobs"])[0] == tracking_key(_job())
    assert second["jobs"][tracking_key(_job())]["match"] == {"score": 80}


def test_save_rejects_identity_less_jobs():
    with pytest.raises(ValueError):
        save_job(new_saved_store(), {"title": "No links or ids"})


def test_remove_is_noop_when_absent():
    saved = save_job(new_saved_store(), _job())
    key = tracking_key(_job())
    assert remove_job(saved, "missing") == saved
    assert remove_job(saved, key) == new_saved_store()


def test_ensure_snapshot_saves_once_then_reuses():
    saved, key = ensure_snapshot(new_saved_store(), _job())
    assert key == tracking_key(_job())
    same, _ = ensure_snapshot(saved, _job())
    assert same == saved
    with pytest.raises(ValueError):
        ensure_snapshot(new_saved_store(), {"title": "anonymous"})


def test_status_date_notes_validation_and_boundaries():
    apps = new_application_store()
    with pytest.raises(ValueError):
        set_status(apps, "k", "Hired")
    apps = set_status(apps, "k", "Interview")
    assert apps["applications"]["k"]["status"] == "Interview"
    apps = set_applied_date(apps, "k", "2026-10-14")
    assert apps["applications"]["k"]["applied_date"] == "2026-10-14"
    apps = set_applied_date(apps, "k", "")
    assert apps["applications"]["k"]["applied_date"] is None
    with pytest.raises(ValueError):
        set_applied_date(apps, "k", "14/10/2026")
    with pytest.raises(ValueError):
        set_applied_date(apps, "k", 42)
    apps = set_notes(apps, "k", "x" * 2000)
    assert len(apps["applications"]["k"]["notes"]) == 2000
    with pytest.raises(ValueError):
        set_notes(apps, "k", "x" * 2001)
    with pytest.raises(ValueError):
        set_notes(apps, "k", None)
    apps = set_cover_letter(apps, "k", "Dear Hiring Manager, ...")
    assert apps["applications"]["k"]["cover_letter"].startswith("Dear")
    with pytest.raises(ValueError):
        set_cover_letter(apps, "k", "x" * 8001)
    with pytest.raises(ValueError):
        set_status(apps, "", "Applied")
    assert remove_application(apps, "k") == new_application_store()


def test_record_validation_and_clean_helpers():
    good = save_job(new_saved_store(), _job())["jobs"][tracking_key(_job())]
    assert validate_saved_record(good) is True
    assert validate_saved_record({"job": {"title": "anonymous"}}) is False
    assert validate_saved_record(None) is False
    raw = {"version": 1, "jobs": {"a": good, "b": {"job": {}}, "c": None}}
    kept, skipped = clean_saved_store(raw)
    assert list(kept) == ["a"] and skipped == 2
    assert clean_saved_store(None) == ({}, 0)
    assert clean_saved_store({"version": 1, "jobs": []})[1] == 1
    good_app = set_status(new_application_store(), "k", "Applied")["applications"]["k"]
    assert validate_application(good_app) is True
    assert validate_application({**good_app, "status": "Hired"}) is False
    assert validate_application({**good_app, "applied_date": "yesterday"}) is False
    assert validate_application({**good_app, "notes": 5}) is False
    raw_apps = {"version": 1, "applications": {"k": good_app, "bad": {"status": "?"}}}
    kept, skipped = clean_application_store(raw_apps)
    assert list(kept) == ["k"] and skipped == 1


def test_inputs_are_never_mutated():
    job = _job()
    apps = new_application_store()
    snapshot = (copy.deepcopy(job), copy.deepcopy(apps))
    save_job(new_saved_store(), job)
    set_status(apps, "k", "Applied")
    set_notes(apps, "k", "note")
    set_applied_date(apps, "k", "2026-01-01")
    assert (job, apps) == snapshot


def test_letter_honesty_rules():
    full = draft_cover_letter(
        _job(), {"skills": ["java"], "experience_years": 1.5}
    )
    assert "Java Developer" in full and "Acme" in full
    assert "1.5 years" in full and "java" in full
    assert "[Your Name]" in full
    unknown_exp = draft_cover_letter(
        _job(), {"skills": ["java"], "experience_years": None}
    )
    assert "years of" not in unknown_exp
    bare = draft_cover_letter({}, {})
    assert "this role" in bare and "years of" not in bare
    assert "Kubernetes" not in draft_cover_letter(_job(), {"skills": ["java"]})
    for token in ("fresher", "expert", "10 years", "led a team", "I built"):
        assert token not in full


def test_tracking_module_has_no_banned_imports():
    src = (Path(__file__).resolve().parent.parent / "core" / "tracking.py").read_text(
        encoding="utf-8"
    )
    imports = [
        line for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]
    blob = "\n".join(imports)
    for banned in ("streamlit", "requests", "sklearn", "scikit", "pypdf", "fastapi"):
        assert banned not in blob


def test_save_tracking_state_reports_partial_failure(monkeypatch):
    import storage
    from unittest.mock import patch

    from app import load_applications, load_saved_jobs, save_tracking_state, widget_key

    calls = []

    def fake_save(name, data):
        calls.append(name)
        if name == "applications":
            raise storage.StorageError("disk full (simulated)")
        return name

    monkeypatch.setattr("storage.save_store", fake_save)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        ok, errors = save_tracking_state(
            {"version": 1, "jobs": {}}, {"version": 1, "applications": {}}
        )
    assert ok is False
    assert any("applications" in error for error in errors)
    assert calls[0] == "saved_jobs"  # first write attempted before the failure


def test_save_tracking_state_full_success_without_network(monkeypatch):
    from unittest.mock import patch

    import storage

    monkeypatch.setattr("storage.save_store", lambda name, data: name)
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        from app import save_tracking_state

        ok, errors = save_tracking_state(
            {"version": 1, "jobs": {}}, {"version": 1, "applications": {}}
        )
    assert (ok, errors) == (True, [])


def test_load_helpers_survive_corrupted_stores(monkeypatch):
    import storage

    from app import load_applications, load_saved_jobs

    def boom(name, default):
        raise storage.StorageCorruptedError(name, "bad json")

    monkeypatch.setattr("storage.load_store", boom)
    jobs, _, warning = load_saved_jobs()
    assert jobs == {} and warning
    apps, _, warning = load_applications()
    assert apps == {} and warning


def test_widget_keys_unique_and_safe():
    from app import widget_key

    keys = {
        widget_key("HTTPS://x.com/A?b=1", "save", 0),
        widget_key("https://x.com/a?b=1", "save", 0),
        widget_key("https://x.com/a?b=1", "save", 1),
        widget_key(None, "save", 2),
    }
    assert len(keys) == 4
    assert all(set(key) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.") for key in keys)
