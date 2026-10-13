"""Phase 4 — strict eligibility, role, and location filtering.

Dependencies: stdlib + `config` only. No I/O, network, Streamlit, or
sklearn, so the module stays reusable from a future backend.

Strict experience policy (locked, mirrors `config.py`):
- Accept explicitly eligible 0-1 / 0-2-year roles.
- Accept 0-3 ONLY with explicit evidence that 0-2-year candidates
  are eligible (fresher-welcome phrase or a range starting at 0/1).
- Reject minimum requirements above two years; reject open-ended
  seniority beyond the band (max > 3).
- Exclude unclear requirements by default.
- Candidate `None` experience never becomes zero: it passes only
  jobs explicitly welcoming zero-year candidates, else rejected.
- Job requirements and candidate history are parsed and reported
  separately; evidence snippets are preserved in reasons.
"""

import re

import config
from core.skills import JAVA_ROLE_SKILLS, PYTHON_ROLE_SKILLS, find_skills

_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:\+)?\s*"
    r"(years?|yrs?|yr|yoe)\b",
    re.IGNORECASE,
)
_PLUS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+\s*(years?|yrs?|yr|yoe)\b", re.IGNORECASE
)
_EXACT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(years?|yrs?|yr|yoe)\b", re.IGNORECASE
)
_FRESHER_STRONG_RE = re.compile(
    r"\b(freshers?\s+(?:welcome|encouraged|can\s+apply|may\s+apply)"
    r"|no\s+experience\s+(?:required|needed)"
    r"|zero\s+experience|0\s*freshers?)\b",
    re.IGNORECASE,
)
# NOTE: a bare "entry level" phrase is deliberately NOT treated as
# eligibility evidence. It is ambiguous on its own and must never
# override an explicit numeric minimum such as "2-3 years". Only the
# unambiguous _FRESHER_STRONG_RE wording above (or a range starting
# at 0/1) counts as explicit 0-2-year eligibility, and only when it
# does not conflict with the listing's stated minimum.
_NON_TECH_TITLE_RE = re.compile(
    r"\b(sales|marketing|accountant|hr\s|human resources|recruiter|"
    r"content writer|graphic designer|telecaller|delivery\s+(?:boy|partner))\b",
    re.IGNORECASE,
)

# A small gazetteer of Indian cities; matching is substring-based and
# conservative (word boundaries) to avoid false hits like "Patna" in text.
INDIA_CITIES = (
    "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad", "chennai",
    "kolkata", "pune", "ahmedabad", "jaipur", "kochi", "cochin", "noida",
    "gurgaon", "gurugram", "indore", "nagpur", "lucknow", "kanpur",
    "surat", "bhopal", "patna", "chandigarh", "mysore", "mysuru",
    "coimbatore", "thiruvananthapuram", "vijayawada", "guwahati", "bhubaneswar",
)


def _job_text(job):
    title = job.get("title") if isinstance(job.get("title"), str) else ""
    description = (
        job.get("description") if isinstance(job.get("description"), str) else ""
    )
    return f"{title}\n{description}"


def _strong_fresher_evidence(text):
    """Return the unambiguous fresher-welcome snippet, or None."""
    match = _FRESHER_STRONG_RE.search(text)
    return match.group(0).strip() if match else None


def parse_job_experience(job):
    """Parse a job's REQUIRED experience (not candidate history).

    Returns min/max required years, kind, explicit_0_2 flag, the
    matched evidence snippet (or None), plus conflict data: when
    unambiguous fresher-welcome wording contradicts a stated numeric
    minimum above one year, ``conflict`` is True and the job must be
    rejected conservatively regardless of other signals.
    """
    text = _job_text(job) if isinstance(job, dict) else ""
    strong = _strong_fresher_evidence(text)
    match = _RANGE_RE.search(text)
    if match:
        lower = float(match.group(1))
        return {
            "min_years": lower,
            "max_years": float(match.group(2)),
            "kind": "range",
            "explicit_0_2": lower <= 1,
            "evidence": match.group(0).strip(),
            "conflict": strong is not None and lower > 1,
            "conflict_evidence": strong,
        }
    match = _PLUS_RE.search(text)
    if match:
        lower = float(match.group(1))
        return {
            "min_years": lower,
            "max_years": None,
            "kind": "minimum",
            "explicit_0_2": lower <= 1,
            "evidence": match.group(0).strip(),
            "conflict": strong is not None and lower > 1,
            "conflict_evidence": strong,
        }
    match = _EXACT_RE.search(text)
    if match:
        value = float(match.group(1))
        return {
            "min_years": value,
            "max_years": value,
            "kind": "exact",
            "explicit_0_2": value <= 1,
            "evidence": match.group(0).strip(),
            "conflict": strong is not None and value > 1,
            "conflict_evidence": strong,
        }
    if strong is not None:
        return {
            "min_years": 0.0,
            "max_years": None,
            "kind": "fresher",
            "explicit_0_2": True,
            "evidence": strong,
            "conflict": False,
            "conflict_evidence": None,
        }
    return {
        "min_years": None,
        "max_years": None,
        "kind": "unknown",
        "explicit_0_2": False,
        "evidence": None,
        "conflict": False,
        "conflict_evidence": None,
    }


def is_eligible(job, candidate_years):
    """Apply the strict experience policy; returns (ok, reasons)."""
    req = parse_job_experience(job)
    evidence = f" (evidence: {req['evidence']!r})" if req["evidence"] else ""
    strict_max = config.EXP_MAX_STRICT_YEARS
    band_max = config.EXP_MAX_CONDITIONAL_YEARS

    if req["min_years"] is None:
        return False, [
            "experience requirement unclear — excluded by default" + evidence
        ]
    if req.get("conflict"):
        return False, [
            "conflicting requirements: fresher-welcome wording "
            f"({req['conflict_evidence']!r}) contradicts stated minimum "
            f"({req['evidence']!r}) — excluded conservatively"
        ]
    if req["min_years"] > strict_max:
        return False, [
            f"requires minimum {req['min_years']:g} years "
            f"(above {strict_max}-year strict cap)" + evidence
        ]
    if req["max_years"] is not None and req["max_years"] > band_max:
        return False, [
            f"requires up to {req['max_years']:g} years "
            f"(above {band_max}-year band)" + evidence
        ]
    if (
        req["max_years"] is not None
        and req["max_years"] > strict_max
        and not req["explicit_0_2"]
    ):
        return False, [
            f"up to {req['max_years']:g} years with no explicit "
            "0–2-year eligibility" + evidence
        ]
    if candidate_years is None:
        if req["min_years"] == 0 or req["kind"] == "fresher":
            return True, [
                "candidate experience unknown but role explicitly "
                "welcomes zero-year candidates" + evidence
            ]
        return False, [
            "candidate experience unknown and role does not explicitly "
            "welcome freshers — excluded, never assumed zero" + evidence
        ]
    if candidate_years < req["min_years"]:
        return False, [
            f"candidate {candidate_years:g} yrs below required minimum "
            f"{req['min_years']:g} yrs" + evidence
        ]
    return True, [
        f"candidate {candidate_years:g} yrs meets required minimum "
        f"{req['min_years']:g} yrs" + evidence
    ]


def is_role_relevant(job, candidate):
    """Lenient role check; returns (ok, reasons). Unknown passes through.

    Invalid job records (None, non-dict) are rejected conservatively
    instead of raising.
    """
    if not isinstance(job, dict):
        return False, ["invalid job record — excluded from role matching"]
    candidate = candidate or {}
    candidate_skills = {
        s for s in (candidate.get("skills") or []) if isinstance(s, str)
    }
    job_skills = set(find_skills(_job_text(job)))
    title = job.get("title") if isinstance(job.get("title"), str) else ""

    if _NON_TECH_TITLE_RE.search(title):
        return False, [f"title {title!r} reads as non-technical for a backend profile"]
    if candidate_skills & job_skills:
        shared = sorted(candidate_skills & job_skills)
        return True, [f"shares skills: {', '.join(shared)}"]
    java_hits = len(job_skills & set(JAVA_ROLE_SKILLS))
    py_hits = len(job_skills & set(PYTHON_ROLE_SKILLS))
    hint = (candidate.get("role_hint") or "")
    if "java/spring" in hint and java_hits:
        return True, ["job matches candidate java/spring direction"]
    if "python/fastapi" in hint and py_hits:
        return True, ["job matches candidate python/fastapi direction"]
    if not job_skills:
        return True, ["role signal unclear — kept for scoring"]
    return True, ["no shared skills but no clear mismatch — kept for scoring"]


def _mentions_india(*texts):
    blob = " ".join(t for t in texts if isinstance(t, str)).lower()
    if re.search(r"(?<!\w)indian?(?!\w)", blob):
        return True
    return any(
        re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", blob)
        for city in INDIA_CITIES
    )


def is_location_relevant(job):
    """India-wide + remote/hybrid preference; unknown kept with a flag.

    Invalid job records (None, non-dict) are rejected conservatively
    instead of raising.
    """
    if not isinstance(job, dict):
        return False, ["invalid job record — excluded from location scope"]
    mode = job.get("work_mode")
    location = job.get("location") if isinstance(job.get("location"), str) else ""
    description = (
        job.get("description") if isinstance(job.get("description"), str) else ""
    )
    if mode in ("remote", "hybrid"):
        return True, [f"work mode {mode} matches remote/hybrid preference"]
    if _mentions_india(location, description):
        return True, ["mentions India — kept for India-wide search"]
    if mode == "onsite" and (location or "").strip():
        return False, [
            f"onsite role outside India ({location.strip()}) — excluded"
        ]
    return True, ["location unclear — kept with flag for manual review"]


def _location_unclear(job):
    """Structured counterpart of the kept-with-flag location branch."""
    mode = job.get("work_mode")
    location = job.get("location") if isinstance(job.get("location"), str) else ""
    description = (
        job.get("description") if isinstance(job.get("description"), str) else ""
    )
    return (
        mode not in ("remote", "hybrid")
        and not _mentions_india(location, description)
        and not (mode == "onsite" and location.strip())
    )


def filter_jobs(jobs, candidate):
    """Split jobs into kept/rejected with reasons; inputs never mutated.

    The ``needs-review`` flag is derived from structured decision data
    (skill overlap and location classification), not by matching the
    human-readable reason text, so rewording reasons cannot break it.
    """
    candidate = candidate or {}
    candidate_skills = {
        s for s in (candidate.get("skills") or []) if isinstance(s, str)
    }
    kept, rejected = [], []
    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        ok_exp, exp_reasons = is_eligible(job, candidate.get("experience_years"))
        ok_role, role_reasons = is_role_relevant(job, candidate)
        ok_loc, loc_reasons = is_location_relevant(job)
        reasons = exp_reasons + role_reasons + loc_reasons
        flags = []
        if not (candidate_skills & set(find_skills(_job_text(job)))):
            flags.append("needs-review")
        elif _location_unclear(job):
            flags.append("needs-review")
        if ok_exp and ok_role and ok_loc:
            kept.append({"job": dict(job), "reasons": reasons, "flags": flags})
        else:
            rejected.append({"job": dict(job), "reasons": reasons, "flags": flags})
    return {"kept": kept, "rejected": rejected}
