"""Phase 2 skills tests: 60-skill dictionary, aliases, priority order."""

from pathlib import Path

from core import skills


def test_vocabulary_has_60_unique_canonical_skills():
    assert len(skills.SKILL_CANONICAL) == 60
    assert len(set(skills.SKILL_CANONICAL)) == 60


def test_java_spring_prioritized_before_python():
    rank = {name: i for i, name in enumerate(skills.SKILL_CANONICAL)}
    assert rank["java"] < rank["python"]
    assert rank["spring boot"] < rank["fastapi"]
    assert rank["spring boot"] < rank["python"]


def test_alias_springboot_maps_to_spring_boot():
    assert "spring boot" in skills.find_skills("Experienced with SpringBoot and maven.")


def test_alias_python3_maps_to_python():
    assert "python" in skills.find_skills("Built tools with Python3 and git.")


def test_ambiguous_py_alone_is_not_python():
    found = skills.find_skills("I love py and apples.")
    assert "python" not in found


def test_java_does_not_match_javascript():
    found = skills.find_skills("Frontend work with JavaScript and HTML.")
    assert "javascript" in found
    assert "java" not in found


def test_java_and_javascript_both_detected_when_both_present():
    found = skills.find_skills("Java backend plus JavaScript frontend.")
    assert "java" in found
    assert "javascript" in found


def test_priority_order_java_before_python():
    found = skills.find_skills("Python scripting and Java Spring Boot microservices.")
    assert found.index("java") < found.index("python")
    assert found.index("spring boot") < found.index("python")


def test_evidence_counts_canonical_and_aliases():
    evidence = skills.skill_evidence("Spring Boot and springboot services.")
    assert evidence.get("spring boot", 0) >= 2


def test_empty_text_yields_no_skills():
    assert skills.find_skills("") == []
    assert skills.skill_evidence("   ") == {}


def test_core_modules_have_no_heavy_or_ui_imports():
    import re

    for module in ("skills.py", "resume.py"):
        src = (Path(__file__).resolve().parent.parent / "core" / module).read_text(
            encoding="utf-8"
        )
        imports = [
            line
            for line in src.splitlines()
            if re.match(r"\s*(import|from)\s+", line)
        ]
        blob = "\n".join(imports)
        for banned in ("streamlit", "sklearn", "scikit", "requests", "fastapi"):
            assert banned not in blob, f"{module} must not import {banned}"
