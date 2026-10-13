"""Phase 5 — pure view-model helpers for the Streamlit UI.

Stdlib only. No Streamlit, network, or file I/O: every function here
operates on already-fetched data, so local filtering/sorting can never
trigger a network request. Safe to unit-test without a browser.
"""

SORT_OPTIONS = ("Match score", "Newest first", "Company A–Z")


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


def apply_local_filters(
    entries,
    role_keyword="",
    skills=(),
    location="",
    work_modes=(),
    sources=(),
):
    """Filter merged entries without refetching; returns a new list.

    Empty selections mean "all". Skill selection keeps jobs requiring
    at least one selected skill. Matching is case-insensitive
    substring (role/location) or membership (modes/sources).
    """
    keyword = (role_keyword or "").strip().lower()
    wanted_skills = {s for s in (skills or []) if isinstance(s, str)}
    wanted_location = (location or "").strip().lower()
    wanted_modes = {m for m in (work_modes or []) if isinstance(m, str)}
    wanted_sources = {s for s in (sources or []) if isinstance(s, str)}

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
        if wanted_skills and not (
            wanted_skills & set(match.get("job_skills", []))
        ):
            continue
        if wanted_location and wanted_location not in str(
            job.get("location") or ""
        ).lower():
            continue
        if wanted_modes and job.get("work_mode") not in wanted_modes:
            continue
        if wanted_sources and job.get("source") not in wanted_sources:
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
