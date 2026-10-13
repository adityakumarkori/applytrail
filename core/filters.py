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
_FRESHER_REQ_RE = re.compile(
    r"\b(freshers?\s+(?:welcome|encouraged|can\s+apply|may\s+apply)"
    r"|entry[\s-]?level|no\s+experience\s+(?:required|needed)"
    r"|zero\s+experience|0\s*freshers?)\b",
    re.IGNORECASE,
)
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


def parse_job_experience(job):
    """Parse a job's REQUIRED experience (not candidate history).

    Returns min/max required years, kind, explicit_0_2 flag, and the
    matched evidence snippet (or None).
    """
    text = _job_text(job) if isinstance(job, dict) else ""
    match = _RANGE_RE.search(text)
    if match:
        return {
            "min_years": float(match.group(1)),
            "max_years": float(match.group(2)),
            "kind": "range",
            "explicit_0_2": float(match.group(1)) <= 1
            or bool(_FRESHER_REQ_RE.search(text)),
            "evidence": match.group(0).strip(),
        }
    match = _PLUS_RE.search(text)
    if match:
        return {
            "min_years": float(match.group(1)),
            "max_years": None,
            "kind": "minimum",
            "explicit_0_2": float(match.group(1)) <= 1
            or bool(_FRESHER_REQ_RE.search(text)),
            "evidence": match.group(0).strip(),
        }
    match = _EXACT_RE.search(text)
    if match:
        value = float(match.group(1))
        return {
            "min_years": value,
            "max_years": value,
            "kind": "exact",
            "explicit_0_2": value <= 1 or bool(_FRESHER_REQ_RE.search(text)),
            "evidence": match.group(0).strip(),
        }
    match = _FRESHER_REQ_RE.search(text)
    if match:
        return {
            "min_years": 0.0,
            "max_years": None,
            "kind": "fresher",
            "explicit_0_2": True,
            "evidence": match.group(0).strip(),
        }
    return {
        "min_years": None,
        "max_years": None,
        "kind": "unknown",
        "explicit_0_2": False,
        "evidence": None,
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
    """Lenient role check; returns (ok, reasons). Unknown passes through."""
    candidate = candidate or {}
    candidate_skills = {
        s for s in (candidate.get("skills") or []) if isinstance(s, str)
    }
    job_skills = set(find_skills(_job_text(job)))
    title = job.get("title") if isinstance(job, dict) and isinstance(job.get("title"), str) else ""

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
    """India-wide + remote/hybrid preference; unknown kept with a flag."""
    job = job or {}
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


def filter_jobs(jobs, candidate):
    """Split jobs into kept/rejected with reasons; inputs never mutated."""
    candidate = candidate or {}
    kept, rejected = [], []
    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        reasons, flags = [], []
        ok_exp, exp_reasons = is_eligible(job, candidate.get("experience_years"))
        ok_role, role_reasons = is_role_relevant(job, candidate)
        ok_loc, loc_reasons = is_location_relevant(job)
        reasons.extend(exp_reasons + role_reasons + loc_reasons)
        if any("kept with flag" in r or "kept for scoring" in r or "unclear — kept" in r for r in reasons):
            flags.append("needs-review")
        if ok_exp and ok_role and ok_loc:
            kept.append({"job": dict(job), "reasons": reasons, "flags": flags})
        else:
            rejected.append({"job": dict(job), "reasons": reasons, "flags": flags})
    return {"kept": kept, "rejected": rejected}
