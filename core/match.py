"""Phase 4 — explainable skill-overlap matching and deterministic ranking.

Dependencies: stdlib + `config` + `core.skills` only. No I/O, network,
Streamlit, or sklearn, so the module stays reusable from a future backend.

Score definition (locked): skill overlap, NOT hiring probability::

    score = round(100 * |matched detectable job skills|
                  / |total detectable job skills|)

A score of 0 with no detectable job skills means "no measurable skill
signal", not "bad fit" — filters and rank position carry that context.
Inputs are never mutated.
"""

import config
from core.skills import find_skills, order_by_priority

_PRIMARY_SET = frozenset(config.PRIMARY_SKILLS)
_MODE_RANK = {mode: rank for rank, mode in enumerate(config.WORK_MODES_PRIORITY)}


def extract_job_skills(job):
    """Detect canonical skills in a job's title + description."""
    if not isinstance(job, dict):
        return []
    title = job.get("title") if isinstance(job.get("title"), str) else ""
    description = (
        job.get("description") if isinstance(job.get("description"), str) else ""
    )
    return find_skills(f"{title}\n{description}")


def _mode_rank(job):
    return _MODE_RANK.get(job.get("work_mode"), len(_MODE_RANK))


def score_job(candidate_skills, job):
    """Score one job against candidate skills; explainable, non-mutating."""
    candidate = {s for s in (candidate_skills or []) if isinstance(s, str)}
    job_skills = extract_job_skills(job)
    job_set = set(job_skills)
    matched = order_by_priority(s for s in job_set if s in candidate)
    missing = order_by_priority(s for s in job_set if s not in candidate)
    primary_hits = len([s for s in matched if s in _PRIMARY_SET])

    reasons = []
    if not job_skills:
        score = 0
        reasons.append(
            "no detectable skill requirements in this listing — "
            "score 0 reflects missing signal, not fit; ranked on filters only"
        )
    else:
        score = round(100 * len(matched) / len(job_skills))
        reasons.append(
            f"matched {len(matched)}/{len(job_skills)} required skills"
            + (f": {', '.join(matched)}" if matched else "")
        )
        if missing:
            reasons.append(f"missing: {', '.join(missing)}")
        if primary_hits:
            reasons.append(f"primary-skill hits: {primary_hits}")
    if not candidate:
        reasons.append("candidate has no recorded skills — score reflects job side only")

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "job_skills": list(job_skills),
        "primary_hits": primary_hits,
        "reasons": reasons,
    }


def rank_jobs(candidate_skills, jobs):
    """Attach match results and sort deterministically; inputs untouched.

    Order: score desc, primary hits desc, matched count desc, work-mode
    preference (remote > hybrid > onsite > unknown), posted recency
    (newest first, missing last), id asc. Python's sort is stable, so
    id and recency pre-passes settle ties deterministically.
    """
    scored = [
        {"job": dict(job), "match": score_job(candidate_skills, job)}
        for job in (jobs or [])
        if isinstance(job, dict)
    ]
    dated = [
        e
        for e in scored
        if isinstance(e["job"].get("posted_date"), str) and e["job"]["posted_date"]
    ]
    undated = [
        e
        for e in scored
        if not (
            isinstance(e["job"].get("posted_date"), str) and e["job"]["posted_date"]
        )
    ]
    dated.sort(key=lambda e: str(e["job"].get("id") or ""))
    dated.sort(key=lambda e: e["job"]["posted_date"], reverse=True)
    undated.sort(key=lambda e: str(e["job"].get("id") or ""))
    ordered = dated + undated
    ordered.sort(
        key=lambda e: (
            -e["match"]["score"],
            -e["match"]["primary_hits"],
            -len(e["match"]["matched_skills"]),
            _mode_rank(e["job"]),
        )
    )
    return ordered
