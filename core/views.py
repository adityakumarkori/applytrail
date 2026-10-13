"""Phase 5 — pure view-model helpers for the Streamlit UI.

Stdlib only. No Streamlit, network, or file I/O: every function here
operates on already-fetched data, so local filtering/sorting can never
trigger a network request. Safe to unit-test without a browser.
"""

from datetime import datetime, timezone

SORT_OPTIONS = ("Match score", "Newest first", "Company A–Z")

# Supported recency windows (days). None means no recency restriction.
RECENCY_OPTIONS = (None, 7, 14, 30)

# Skill-match modes for the local skill filter.
SKILL_MATCH_MODES = ("any", "all")


def attach_filter_info(ranked, filtered):
    """Merge filter reasons/flags into ranked entries by job id.

    ``ranked`` is [{job, match}] (from match.rank_jobs);
    ``filtered`` is {"kept": [{job, reasons, flags}], ...} (from
    filters.filter_jobs). Returns new [{job, match, reasons, flags}]
    entries; inputs are never mutated.
    """
    info = {}
    for entry in (filtered or {}).get("kept", []):
        job = entry.get("job", {})
        info[str(job.get("id"))] = {
            "reasons": list(entry.get("reasons", [])),
            "flags": list(entry.get("flags", [])),
        }
    merged = []
    for entry in ranked or []:
        job = entry.get("job", {})
        extra = info.get(str(job.get("id")), {"reasons": [], "flags": []})
        merged.append(
            {
                "job": dict(job),
                "match": dict(entry.get("match", {})),
                "reasons": list(extra["reasons"]),
                "flags": list(extra["flags"]),
            }
        )
    return merged


def _entry_text(entry, *fields):
    job = entry.get("job", {})
    return " ".join(
        str(job.get(field) or "") for field in fields
    )


def match_roles(job, target_roles):
    """Check a job title against free-text target roles (pure).

    Roles are normalized (trimmed, case-insensitive); an empty role
    list means no restriction. A job matches when any role appears as
    a substring of its title. Missing or non-string titles never match.
    Role matching never overrides experience eligibility — it only
    narrows already-filtered results.
    """
    roles = [
        role.strip().lower()
        for role in (target_roles or [])
        if isinstance(role, str) and role.strip()
    ]
    if not roles:
        return True
    if not isinstance(job, dict):
        return False
    title = job.get("title")
    if not isinstance(title, str) or not title.strip():
        return False
    lowered = title.lower()
    return any(role in lowered for role in roles)


def posted_age_days(posted_date):
    """Age of an ISO posting date in days, or None when unknown.

    Missing, empty, or unparsable dates return None and are never
    treated as recent. Naive timestamps are assumed UTC. Never raises
    on bad input and never invents a date.
    """
    if not isinstance(posted_date, str) or not posted_date.strip():
        return None
    try:
        moment = datetime.fromisoformat(posted_date.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() / 86400.0


def apply_local_filters(
    entries,
    role_keyword="",
    skills=(),
    location="",
    work_modes=(),
    sources=(),
    min_score=0,
    posted_within_days=None,
    skill_match="any",
    target_roles=(),
):
    """Filter merged entries without refetching; returns a new list.

    Empty selections mean "all". Skill selection keeps jobs requiring
    at least one selected skill ("any") or every selected skill
    ("all"); unknown modes fall back to "any". ``min_score`` is an
    inclusive 0-100 threshold on the skill-overlap score.
    ``posted_within_days`` keeps jobs posted at most that many days
    ago; missing or invalid dates are never recent and are excluded
    while the filter is active. ``target_roles`` narrows by job title
    via :func:`match_roles`. Matching is case-insensitive substring
    (role/location) or membership (modes/sources).
    """
    keyword = (role_keyword or "").strip().lower()
    wanted_skills = {s for s in (skills or []) if isinstance(s, str)}
    wanted_location = (location or "").strip().lower()
    wanted_modes = {m for m in (work_modes or []) if isinstance(m, str)}
    wanted_sources = {s for s in (sources or []) if isinstance(s, str)}
    try:
        threshold = float(min_score)
    except (TypeError, ValueError):
        threshold = 0.0
    match_all = skill_match == "all"

    kept = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        job = entry.get("job", {})
        match = entry.get("match", {})
        if keyword and keyword not in _entry_text(
            entry, "title", "company", "description"
        ).lower():
            continue
        job_skills = set(match.get("job_skills", []))
        if wanted_skills:
            if match_all:
                if not wanted_skills <= job_skills:
                    continue
            elif not (wanted_skills & job_skills):
                continue
        if wanted_location and wanted_location not in str(
            job.get("location") or ""
        ).lower():
            continue
        if wanted_modes and job.get("work_mode") not in wanted_modes:
            continue
        if wanted_sources and job.get("source") not in wanted_sources:
            continue
        try:
            score = float(match.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        if score < threshold:
            continue
        if posted_within_days is not None:
            age = posted_age_days(job.get("posted_date"))
            if age is None or age > posted_within_days:
                continue
        if not match_roles(job, target_roles):
            continue
        kept.append(entry)
    return kept


def sort_results(entries, sort_by="Match score"):
    """Re-sort merged entries locally; returns a new list."""
    items = list(entries or [])
    if sort_by == "Newest first":
        dated = [
            e
            for e in items
            if isinstance(e.get("job", {}).get("posted_date"), str)
            and e["job"]["posted_date"]
        ]
        undated = [
            e
            for e in items
            if not (
                isinstance(e.get("job", {}).get("posted_date"), str)
                and e["job"]["posted_date"]
            )
        ]
        dated.sort(key=lambda e: e["job"]["posted_date"], reverse=True)
        return dated + undated
    if sort_by == "Company A–Z":
        return sorted(
            items,
            key=lambda e: (
                str(e.get("job", {}).get("company") or "~").lower(),
                str(e.get("job", {}).get("title") or "").lower(),
            ),
        )
    return items  # "Match score": keep rank_jobs order
