"""Phase 9.2 assist-apply tests: contacts stay local, copy-only, no bot.

No live network; storage I/O is mocked or monkeypatched.
"""

from unittest.mock import patch

import pytest

from app import build_application_kit, build_profile_payload, sanitize_profile
from core import tracking


def test_contact_fields_preserved_when_valid():
    clean, warnings = sanitize_profile(
        {
            "full_name": "  Ada Lovelace  ",
            "email": "ada@example.com",
            "phone": "+91 98765 43210",
            "location": "Bengaluru, India",
            "linkedin_url": "linkedin.com/in/adalovelace",
            "portfolio_url": "https://github.com/ada",
            "headline_summary": "Backend fresher",
        }
    )
    assert warnings == []
    assert clean["full_name"] == "Ada Lovelace"
    assert clean["email"] == "ada@example.com"
    assert clean["phone"] == "+91 98765 43210"
    assert clean["linkedin_url"] == "https://linkedin.com/in/adalovelace"
    assert clean["portfolio_url"] == "https://github.com/ada"


def test_invalid_contacts_cleared_with_warnings():
    clean, warnings = sanitize_profile(
        {
            "email": "not-an-email",
            "phone": "abc",
            "linkedin_url": "javascript:alert(1)",
            "portfolio_url": "nota url with spaces",
        }
    )
    assert clean["email"] == ""
    assert clean["phone"] == ""
    assert clean["linkedin_url"] == ""
    assert clean["portfolio_url"] == ""
    assert len(warnings) == 4


def test_missing_contact_keys_silent_defaults():
    clean, warnings = sanitize_profile({"query": "java"})
    assert warnings == []
    for key in (
        "full_name", "email", "phone", "location",
        "linkedin_url", "portfolio_url", "headline_summary",
    ):
        assert clean[key] == ""


def test_free_text_truncated_to_caps():
    clean, _ = sanitize_profile({"full_name": "A" * 500, "headline_summary": "B" * 900})
    assert len(clean["full_name"]) == 100
    assert len(clean["headline_summary"]) == 500


def test_build_payload_accepts_contacts_and_rejects_bad():
    payload = build_profile_payload(
        0, 2, "java", ["java"], 1.0, ["Backend"], 0, None,
        "Ada", "ada@example.com", "+911234567890", "Bengaluru",
        "https://linkedin.com/in/ada", "https://github.com/ada", "Fresher",
    )
    assert payload["email"] == "ada@example.com"
    assert payload["full_name"] == "Ada"
    with pytest.raises(ValueError, match="contact email"):
        build_profile_payload(0, 2, "java", [], None, [], 0, None, "", "bad-email")
    with pytest.raises(ValueError, match="contact phone"):
        build_profile_payload(0, 2, "java", [], None, [], 0, None, "", "", "xyz")


def test_build_payload_backward_compatible_positional():
    payload = build_profile_payload(0, 2, "java", ["java"], 1.5, ["Backend"], 40, 7)
    assert payload["min_score"] == 40
    assert payload["email"] == ""


def test_application_kit_order_and_fallbacks():
    fields = build_application_kit(
        {"skills": [], "experience_years": None},
        {
            "full_name": "Ada", "email": "a@x.com", "phone": "",
            "location": "", "linkedin_url": "", "portfolio_url": "",
            "headline_summary": "", "skills": ["java"], "experience_years": 1.5,
        },
    )
    labels = [label for label, _ in fields]
    assert labels[:2] == ["Full name", "Email"]
    assert "Skills" in labels
    assert fields[labels.index("Skills")][1] == "java"
    assert "Experience" in labels
    assert build_application_kit(None, None) == []
    assert build_application_kit({"skills": ["x"]}, {}) == [("Skills", "x")]


def test_cover_letter_footer_uses_real_contacts_only():
    base = tracking.draft_cover_letter({"title": "Dev", "company": "Acme"}, {"skills": []})
    assert base.endswith("Sincerely,\n[Your Name]")
    with_footer = tracking.draft_cover_letter(
        {"title": "Dev", "company": "Acme"}, {"skills": []},
        {"full_name": "Ada", "email": "a@x.com", "phone": "", "location": "",
         "linkedin_url": "", "portfolio_url": ""},
    )
    assert "Ada" in with_footer
    assert "a@x.com" in with_footer
    assert "[Your Name]" not in with_footer


def test_sidebar_profile_inputs_and_save_without_network(monkeypatch):
    from streamlit.testing.v1 import AppTest

    written = {}
    monkeypatch.setattr(
        "storage.save_store", lambda name, data: written.setdefault(name, data)
    )
    with patch("core.jobs.fetch_all_jobs", side_effect=AssertionError("no fetch")):
        at = AppTest.from_file("app.py").run(timeout=30)
        assert not at.exception, at.exception
        labels = [t.label for t in at.text_input] + [t.label for t in at.text_area]
        for expected in ("Full name", "Email", "Phone", "LinkedIn URL",
                         "Portfolio / GitHub URL", "Headline summary"):
            assert expected in labels, labels
        next(t for t in at.text_input if t.label == "Full name").set_value("Ada").run(timeout=30)
        next(t for t in at.text_input if t.label == "Email").set_value("a@x.com").run(timeout=30)
        save_button = next(b for b in at.button if b.label == "Save preferences")
        save_button.click().run(timeout=30)
    assert not at.exception, at.exception
    assert written["profile"]["full_name"] == "Ada"
    assert written["profile"]["email"] == "a@x.com"
    assert any("saved locally" in str(s.value).lower() for s in at.success)
