"""Phase 7 — saved jobs & application tracking helpers.

Stdlib + local core modules only. No Streamlit, network, or file I/O:
all helpers operate on plain dicts, so saving, validation, and drafting
are unit-testable without a browser. Persistence itself stays in
``storage.save_store`` / ``storage.load_store`` (atomic JSON).

Identity rule: a job is keyed by its genuine application URL
(scheme/host lowercased, path/query case preserved, fragment dropped),
falling back to ``source:id`` only when both are valid non-empty
strings. Records without enough identity are rejected, never invented.
Identical URLs therefore deduplicate across sources (documented).
"""

import math
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from core.skills import find_skills

STATUSES = ("Saved", "Applied", "Interview", "Rejected", "Offer")
NOTES_MAX = 2000
LETTER_MAX = 8000
STORES_VERSION = 1


def normalize_url(url):
    """Normalize a listing URL for stable identity, or None if unusable.

    Lowercases scheme and hostname only; path and query keep their
    case; fragments are dropped. Requires an http(s) URL with a host.
    Never raises on bad input.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    try:
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
        )
    except ValueError:
        return None


def tracking_key(job):
    """Stable identity for a job dict, or None when insufficient.

    Prefers the normalized application URL (``apply_url``, then
    ``source_url``); falls back to ``source:id`` only when both are
    valid non-empty strings. Inputs are never mutated.
    """
    if not isinstance(job, dict):
        return None
    for field in ("apply_url", "source_url"):
        normalized = normalize_url(job.get(field))
        if normalized is not None:
            return normalized
    source = job.get("source")
    external_id = job.get("id")
    if (
        isinstance(source, str)
        and source.strip()
        and isinstance(external_id, str)
        and external_id.strip()
    ):
        return f"{source.strip()}:{external_id.strip()}"
    return None


def new_saved_store():
    """Empty saved-jobs document."""
    return {"version": STORES_VERSION, "jobs": {}}


def new_application_store():
    """Empty applications document."""
    return {"version": STORES_VERSION, "applications": {}}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_job(saved, job, match=None):
    """Save a job snapshot under its tracking key. Returns a new dict.

    Re-saving the same key overwrites (dedupe by construction) and
    refreshes ``saved_at``. Raises ValueError when the job lacks
    enough identity. Never mutates inputs.
    """
    key = tracking_key(job)
    if key is None:
        raise ValueError("cannot save a job without a stable link or source id")
    jobs = dict(saved or {}).get("jobs")
    updated = dict(jobs) if isinstance(jobs, dict) else {}
    snapshot = dict(job)
    updated[key] = {
        "job": snapshot,
        "saved_at": _now_iso(),
        "match": dict(match)
        if isinstance(match, dict)
        else (None if match is None else dict(match)),
    }
    return {"version": STORES_VERSION, "jobs": updated}


def remove_job(saved, key):
    """Remove one saved snapshot. Returns a new dict; no-op when absent."""
    jobs = dict((saved or {}).get("jobs", {}))
    jobs.pop(key, None)
    return {"version": STORES_VERSION, "jobs": jobs}


def remove_application(applications, key):
    """Remove one application record. Returns a new dict; no-op when absent."""
    records = dict((applications or {}).get("applications", {}))
    records.pop(key, None)
    return {"version": STORES_VERSION, "applications": records}


def ensure_snapshot(saved, job, match=None):
    """Return (saved_store, key), saving the snapshot when absent.

    Used when a status change targets a job with no snapshot yet, so an
    application record never points at nothing. Raises ValueError when
    the job lacks enough identity.
    """
    key = tracking_key(job)
    if key is None:
        raise ValueError("cannot track a job without a stable link or source id")
    jobs = (saved or {}).get("jobs")
    if isinstance(jobs, dict) and key in jobs:
        return saved, key
    return save_job(saved if isinstance(saved, dict) else new_saved_store(), job, match), key


def _upsert(applications, key):
    """Return (records_dict, record) for key, creating defaults when absent."""
    if not isinstance(key, str) or not key:
        raise ValueError("application key must be a non-empty string")
    records = dict((applications or {}).get("applications", {}))
    record = dict(records.get(key, {}))
    record.setdefault("status", "Saved")
    record.setdefault("applied_date", None)
    record.setdefault("notes", "")
    record.setdefault("cover_letter", "")
    record.setdefault("updated_at", _now_iso())
    return records, record


def set_status(applications, key, status):
    """Set an application status. Returns a new document (upsert)."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    records, record = _upsert(applications, key)
    record["status"] = status
    record["updated_at"] = _now_iso()
    records[key] = record
    return {"version": STORES_VERSION, "applications": records}


def set_applied_date(applications, key, value):
    """Set the application date (ISO YYYY-MM-DD) or clear it with None/"".

    Returns a new document (upsert). Raises ValueError on invalid dates.
    """
    records, record = _upsert(applications, key)
    if value is None or (isinstance(value, str) and not value.strip()):
        record["applied_date"] = None
    elif isinstance(value, date):
        record["applied_date"] = value.isoformat()
    elif isinstance(value, str):
        try:
            record["applied_date"] = date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise ValueError(
                f"applied date must use YYYY-MM-DD format, got {value!r}"
            ) from None
    else:
        raise ValueError(
            f"applied date must use YYYY-MM-DD format, got {value!r}"
        )
    record["updated_at"] = _now_iso()
    records[key] = record
    return {"version": STORES_VERSION, "applications": records}


def set_notes(applications, key, notes):
    """Set personal notes (str, max 2000 chars). Returns a new document."""
    if not isinstance(notes, str):
        raise ValueError("notes must be a string")
    if len(notes) > NOTES_MAX:
        raise ValueError(f"notes must be at most {NOTES_MAX} characters")
    records, record = _upsert(applications, key)
    record["notes"] = notes
    record["updated_at"] = _now_iso()
    records[key] = record
    return {"version": STORES_VERSION, "applications": records}


def set_cover_letter(applications, key, text):
    """Store an edited cover-letter draft (str, max 8000 chars)."""
    if not isinstance(text, str):
        raise ValueError("cover letter must be a string")
    if len(text) > LETTER_MAX:
        raise ValueError(f"cover letter must be at most {LETTER_MAX} characters")
    records, record = _upsert(applications, key)
    record["cover_letter"] = text
    record["updated_at"] = _now_iso()
    records[key] = record
    return {"version": STORES_VERSION, "applications": records}


def validate_saved_record(record):
    """True when a stored saved-job record is usable (key recomputable)."""
    if not isinstance(record, dict):
        return False
    job = record.get("job")
    return isinstance(job, dict) and tracking_key(job) is not None


def validate_application(record):
    """True when a stored application record is usable."""
    if not isinstance(record, dict):
        return False
    if record.get("status") not in STATUSES:
        return False
    applied = record.get("applied_date")
    if applied is not None:
        if not isinstance(applied, str):
            return False
        try:
            date.fromisoformat(applied)
        except ValueError:
            return False
    if not isinstance(record.get("notes", ""), str):
        return False
    if not isinstance(record.get("cover_letter", ""), str):
        return False
    return True


def clean_saved_store(raw):
    """Split a loaded saved-jobs document into (jobs, skipped_count)."""
    jobs = raw.get("jobs") if isinstance(raw, dict) else None
    if not isinstance(jobs, dict):
        return {}, 1 if raw not in (None, {}, {"version": STORES_VERSION, "jobs": {}}) else 0
    kept, skipped = {}, 0
    for key, record in jobs.items():
        if validate_saved_record(record):
            kept[key] = record
        else:
            skipped += 1
    return kept, skipped


def clean_application_store(raw):
    """Split a loaded applications document into (records, skipped_count)."""
    records = raw.get("applications") if isinstance(raw, dict) else None
    if not isinstance(records, dict):
        return {}, 1 if raw not in (None, {}, {"version": STORES_VERSION, "applications": {}}) else 0
    kept, skipped = {}, 0
    for key, record in records.items():
        if validate_application(record):
            kept[key] = record
        else:
            skipped += 1
    return kept, skipped


def draft_cover_letter(job, candidate, profile=None):
    """Draft a concise cover letter from actual profile + job data only.

    Uses the real title/company/location when available (neutral
    placeholders otherwise), skills genuinely shared with the listing,
    and experience only when the candidate value is a valid number.
    An optional sanitized application profile appends a real contact
    footer (name + contact lines) — never invented. Never invents
    qualifications, achievements, or history.
    """
    job = job if isinstance(job, dict) else {}
    candidate = candidate if isinstance(candidate, dict) else {}
    title = job.get("title") if isinstance(job.get("title"), str) else ""
    title = title.strip()
    company = job.get("company") if isinstance(job.get("company"), str) else ""
    company = company.strip()
    location = job.get("location") if isinstance(job.get("location"), str) else ""
    location = location.strip()

    candidate_skills = {
        s for s in (candidate.get("skills") or []) if isinstance(s, str)
    }
    text_bits = [
        title,
        job.get("description") if isinstance(job.get("description"), str) else "",
    ]
    shared = sorted(
        {s for s in find_skills(" ".join(text_bits)) if s in candidate_skills}
    )

    years = candidate.get("experience_years")
    years_valid = (
        isinstance(years, (int, float))
        and not isinstance(years, bool)
        and math.isfinite(float(years))
        and float(years) >= 0
    )

    paragraphs = ["Dear Hiring Manager,"]
    opening = f"I am applying for the {title} role" if title else "I am applying for this role"
    if company:
        opening += f" at {company}"
    opening += "."
    if location:
        opening += f" I am excited about the opportunity in {location}."
    paragraphs.append(opening)
    if shared:
        listed = ", ".join(shared[:6])
        paragraphs.append(
            f"The role lists {listed} among its requirements, "
            f"which matches my background in {listed}."
        )
    elif candidate_skills:
        listed = ", ".join(sorted(candidate_skills)[:5])
        paragraphs.append(f"My background includes {listed}.")
    if years_valid:
        paragraphs.append(f"I have {float(years):g} years of relevant experience.")
    paragraphs += ["Thank you for your consideration."]
    footer = []
    profile = profile if isinstance(profile, dict) else {}
    name = profile.get("full_name") if isinstance(profile.get("full_name"), str) else ""
    if name and name.strip():
        footer.append(name.strip())
    for key in ("email", "phone", "location", "linkedin_url", "portfolio_url"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            footer.append(value.strip())
    paragraphs.append("Sincerely,\n" + ("\n".join(footer) if footer else "[Your Name]"))
    return "\n\n".join(paragraphs)
