"""Phase 1 config tests: job preferences and backend-reuse constraints."""

import config


def test_role_priority_java_first():
    assert "java" in config.PRIMARY_SKILLS
    assert "spring boot" in config.PRIMARY_SKILLS
    assert "python" in config.SECONDARY_SKILLS


def test_location_and_work_modes():
    assert "India" in config.LOCATIONS
    assert config.WORK_MODES_PRIORITY[0] == "remote"
    assert "hybrid" in config.WORK_MODES_PRIORITY


def test_experience_policy_strict_0_to_2():
    assert config.EXP_MIN_YEARS == 0
    assert config.EXP_MAX_STRICT_YEARS == 2
    assert config.EXP_MAX_CONDITIONAL_YEARS == 3


def test_sources_present_without_keys():
    for key in ("arbeitnow", "remoteok", "remotive", "adzuna"):
        assert config.SOURCES[key].startswith("https://")


def test_stores_cover_required_kinds():
    for key in ("profile", "cached_jobs", "saved_jobs", "applications"):
        assert key in config.STORES


def test_config_has_no_streamlit_or_io_imports():
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "config.py").read_text(
        encoding="utf-8"
    )
    assert "streamlit" not in src
    assert "requests" not in src
