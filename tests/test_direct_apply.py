"""Phase 9.1 direct-apply tests: pure extraction + normalizers + UI links.

No live network: extraction and normalization are pure; app link
resolution is pure. No real-data writes.
"""

from app import _valid_direct_url, resolve_apply_links
from core import jobs
from core.jobs import (
    deduplicate,
    extract_direct_apply_url,
    normalize_adzuna_item,
    normalize_arbeitnow_item,
    normalize_remoteok_item,
    normalize_remotive_item,
)
from core import tracking


def test_job_keys_contains_direct_apply_url():
    assert "direct_apply_url" in jobs.JOB_KEYS


def test_greenhouse_extracted():
    text = "Apply via https://boards.greenhouse.io/acme/jobs/12345 for details."
    assert extract_direct_apply_url(text) == "https://boards.greenhouse.io/acme/jobs/12345"


def test_lever_extracted():
    text = "See https://jobs.lever.co/example/abc-1234 now."
    assert extract_direct_apply_url(text) == "https://jobs.lever.co/example/abc-1234"


def test_ashby_extracted():
    text = "<p>Role: <a href=\"https://jobs.ashbyhq.com/org/role-id\">here</a></p>"
    assert extract_direct_apply_url(text) == "https://jobs.ashbyhq.com/org/role-id"


def test_workday_extracted():
    text = "Apply at https://example.myworkdayjobs.com/en-US/careers/job/9876 today."
    assert extract_direct_apply_url(text) == "https://example.myworkdayjobs.com/en-US/careers/job/9876"


def test_smartrecruiters_extracted():
    text = "Details: https://app.smartrecruiters.com/app/job/abc123 on SmartRecruiters."
    assert extract_direct_apply_url(text) == "https://app.smartrecruiters.com/app/job/abc123"


def test_icims_extracted():
    text = "Posting https://careers-example.icims.com/jobs/4242/job here."
    assert extract_direct_apply_url(text) == "https://careers-example.icims.com/jobs/4242/job"


def test_jobvite_extracted():
    text = "Open https://jobs.jobvite.com/acme/job/oAb12c3fw to apply."
    assert extract_direct_apply_url(text) == "https://jobs.jobvite.com/acme/job/oAb12c3fw"


def test_generic_apply_link_extracted():
    text = "Apply here: https://example.com/careers/backend-123 for more info."
    assert extract_direct_apply_url(text) == "https://example.com/careers/backend-123"


def test_plain_url_without_apply_hint_ignored():
    assert extract_direct_apply_url("See our blog at https://example.com/blog for culture.") is None


def test_bare_ats_hostname_without_url_is_none():
    assert extract_direct_apply_url("We hire via boards.greenhouse.io — search Acme.") is None
    assert extract_direct_apply_url("Find us on Lever") is None


def test_host_only_ats_url_is_none():
    assert extract_direct_apply_url("See https://boards.greenhouse.io for all jobs.") is None


def test_unsafe_schemes_ignored():
    assert extract_direct_apply_url("Apply javascript:alert(1) now") is None
    assert extract_direct_apply_url("Contact mailto:jobs@example.com to apply") is None
    assert extract_direct_apply_url("Mirror ftp://example.com/job/1 apply here") is None


def test_missing_malformed_inputs_are_none():
    assert extract_direct_apply_url(None) is None
    assert extract_direct_apply_url("") is None
    assert extract_direct_apply_url("   ") is None
    assert extract_direct_apply_url(123) is None
    assert extract_direct_apply_url("Apply here: https:// for details") is None
    assert extract_direct_apply_url("Apply here: http:///no-host/path") is None


def test_trailing_punctuation_stripped():
    assert (
        extract_direct_apply_url("Apply (https://jobs.lever.co/x/abc).")
        == "https://jobs.lever.co/x/abc"
    )
    assert (
        extract_direct_apply_url("See https://boards.greenhouse.io/a/b/1, then decide.")
        == "https://boards.greenhouse.io/a/b/1"
    )


def test_first_valid_url_wins():
    text = (
        "Culture: https://example.com/blog. "
        "Apply at https://jobs.lever.co/first/aaa then https://jobs.lever.co/second/bbb."
    )
    assert extract_direct_apply_url(text) == "https://jobs.lever.co/first/aaa"


def _arbeitnow_raw(description):
    return {
        "slug": "s-1",
        "title": "Backend Dev",
        "company_name": "Acme",
        "description": description,
        "url": "https://arbeitnow.com/jobs/s-1",
        "location": "Remote",
        "tags": [],
    }


def test_normalizers_preserve_listing_and_extract_direct():
    desc = "Stack Java. Apply via https://boards.greenhouse.io/acme/jobs/99 today."
    listing = "https://arbeitnow.com/jobs/s-1"
    job = normalize_arbeitnow_item(_arbeitnow_raw(desc))
    assert job["source_url"] == listing
    assert job["apply_url"] == listing
    assert job["direct_apply_url"] == "https://boards.greenhouse.io/acme/jobs/99"
    assert set(job) == set(jobs.JOB_KEYS)

    remoteok = normalize_remoteok_item(
        {
            "id": 7,
            "position": "Backend Dev",
            "company": "Co",
            "url": "https://remoteok.com/remote-jobs/x-7",
            "description": "Apply here: https://jobs.ashbyhq.com/org/rid now",
            "location": "Worldwide",
        }
    )
    assert remoteok["source_url"] == "https://remoteok.com/remote-jobs/x-7"
    assert remoteok["apply_url"] == "https://remoteok.com/remote-jobs/x-7"
    assert remoteok["direct_apply_url"] == "https://jobs.ashbyhq.com/org/rid"

    remotive = normalize_remotive_item(
        {
            "id": 8,
            "title": "Backend Dev",
            "company_name": "Remo",
            "url": "https://remotive.com/remote-jobs/a-8",
            "description": "<p>Apply at https://jobs.lever.co/remo/abc-1</p>",
            "candidate_required_location": "Worldwide",
            "category": "Software Development",
        }
    )
    assert remotive["source_url"] == "https://remotive.com/remote-jobs/a-8"
    assert remotive["direct_apply_url"] == "https://jobs.lever.co/remo/abc-1"

    adzuna = normalize_adzuna_item(
        {
            "id": "9",
            "title": "Java Developer",
            "company": {"display_name": "Gamma"},
            "location": {"display_name": "Bengaluru, India"},
            "description": "Walk in. No link here.",
            "redirect_url": "https://www.adzuna.in/jobs/details/9",
        }
    )
    assert adzuna["source_url"] == "https://www.adzuna.in/jobs/details/9"
    assert adzuna["apply_url"] == "https://www.adzuna.in/jobs/details/9"
    assert adzuna["direct_apply_url"] is None


def test_normalizers_default_direct_none_without_description_links():
    job = normalize_arbeitnow_item(_arbeitnow_raw("Plain Spring Boot role"))
    assert job["direct_apply_url"] is None


def test_deduplicate_does_not_merge_on_direct_url():
    base = normalize_arbeitnow_item(_arbeitnow_raw("Plain role"))
    first = dict(base, apply_url="https://a.example/1", source_url="https://a.example/1",
                 direct_apply_url="https://jobs.lever.co/shared/aaa")
    second = dict(base, id="other:2", source="other",
                  apply_url="https://b.example/2", source_url="https://b.example/2",
                  direct_apply_url="https://jobs.lever.co/shared/aaa")
    assert len(deduplicate([first, second])) == 2


def test_tracking_key_ignores_direct_apply_url():
    job = {
        "source": "s",
        "id": "s:1",
        "apply_url": "https://example.com/jobs/1",
        "source_url": "https://example.com/jobs/1",
        "direct_apply_url": "https://jobs.lever.co/s/aaa",
    }
    plain = {k: v for k, v in job.items() if k != "direct_apply_url"}
    assert tracking.tracking_key(job) == tracking.tracking_key(plain)


def test_resolve_apply_links_prefers_direct_and_handles_legacy():
    direct, listing = resolve_apply_links(
        {
            "source": "remotive",
            "apply_url": "https://remotive.com/remote-jobs/a-1",
            "source_url": "https://remotive.com/remote-jobs/a-1",
            "direct_apply_url": "https://jobs.lever.co/co/abc",
        }
    )
    assert direct == "https://jobs.lever.co/co/abc"
    assert listing == "https://remotive.com/remote-jobs/a-1"

    # Legacy cached record without the new field.
    direct, listing = resolve_apply_links(
        {"source": "s", "apply_url": "https://example.com/j", "source_url": "https://example.com/j"}
    )
    assert direct is None
    assert listing == "https://example.com/j"

    # Unsafe stored direct value falls back to listing.
    direct, listing = resolve_apply_links(
        {"source": "s", "apply_url": "https://example.com/j",
         "source_url": "https://example.com/j", "direct_apply_url": "javascript:alert(1)"}
    )
    assert direct is None
    assert listing == "https://example.com/j"

    assert _valid_direct_url("https://jobs.lever.co/co/abc") is True
    assert _valid_direct_url("javascript:alert(1)") is False
    assert _valid_direct_url(None) is False
