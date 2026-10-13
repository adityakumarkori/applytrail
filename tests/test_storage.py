"""Phase 1 storage tests: atomic writes, missing/corrupted handling."""

import json

import pytest

import storage


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "profile.json"
    data = {"name": "Test", "skills": ["java", "spring boot"]}
    storage.save_json(path, data)
    assert storage.load_json(path, default={}) == data


def test_load_missing_returns_default_without_creating(tmp_path):
    path = tmp_path / "does-not-exist.json"
    assert storage.load_json(path, default={"a": 1}) == {"a": 1}
    assert not path.exists()


def test_load_corrupted_raises_and_preserves_file(tmp_path):
    path = tmp_path / "bad.json"
    raw = "{not valid json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(storage.StorageCorruptedError):
        storage.load_json(path, default={})
    # Original bytes must be untouched — never silently overwritten.
    assert path.read_text(encoding="utf-8") == raw


def test_load_empty_file_counts_as_corrupted(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(storage.StorageCorruptedError):
        storage.load_json(path, default={})


def test_save_is_atomic_no_tmp_leftovers(tmp_path):
    path = tmp_path / "jobs.json"
    storage.save_json(path, {"jobs": []})
    leftovers = list(tmp_path.glob("jobs.json.*.tmp"))
    assert leftovers == []
    assert json.loads(path.read_text(encoding="utf-8")) == {"jobs": []}


def test_unknown_store_name_rejected():
    with pytest.raises(storage.StorageError):
        storage.store_path("no-such-store")
