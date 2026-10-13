"""Phase 5 — first usable Streamlit interface (local-only, no login/DB).

UI-only module: all ranking, filtering, parsing, and fetching logic
lives in core/* + storage. Network happens only inside the Fetch button
handler; everything else (including all reruns) works on in-memory or
locally cached data. Uploaded PDFs are parsed in memory and never
written to disk. Adzuna credentials are kept in a local variable for
the single request and never persisted or displayed.
"""

import math

import streamlit as st

import config
import storage
from core import filters as job_filters
from core import jobs as job_sources
from core import match as matcher
from core import resume as resume_parser
from core import views
from core.skills import SKILL_CANONICAL

_SCORE_HELP = (
    "Skill overlap: share of this listing's detectable skills found in "
    "your profile. It is not a hiring probability."
)

_PREF_MIN_DEFAULT = float(config.EXP_MIN_YEARS)
_PREF_MAX_DEFAULT = float(config.EXP_MAX_STRICT_YEARS)
_PREF_LOWER_BOUND = 0.0
_PREF_UPPER_BOUND = 20.0
_MIN_SCORE_DEFAULT = 0
_POSTED_WITHIN_OPTIONS = ("Any time", "Last 7 days", "Last 14 days", "Last 30 days")
_POSTED_WITHIN_DAYS = {
    "Any time": None,
    "Last 7 days": 7,
    "Last 14 days": 14,
    "Last 30 days": 30,
}


def _coerce_pref(value, default):
    """Coerce one preference to a finite in-range float, else default.

    Returns (number, was_valid). Bools, non-numbers, NaN/inf, and
    out-of-range values are invalid. Never raises, never echoes values.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default, False
    number = float(value)
    if (
        not math.isfinite(number)
        or number < _PREF_LOWER_BOUND
        or number > _PREF_UPPER_BOUND
    ):
        return default, False
    return number, True


def sanitize_profile(profile):
    """Validate a loaded profile without raising on malformed input.

    Returns (clean_profile, warnings). Invalid preference fields are
    restored to the documented 0–2-year defaults; valid fields are
    preserved. Unknown candidate experience stays None (never zero).
    Nothing is written back — saving happens only on explicit fetch.
    """
    clean = {
        "exp_pref_min": _PREF_MIN_DEFAULT,
        "exp_pref_max": _PREF_MAX_DEFAULT,
        "query": "java",
        "skills": [],
        "experience_years": None,
        "target_roles": [],
        "min_score": _MIN_SCORE_DEFAULT,
        "posted_within": None,
    }
    if not isinstance(profile, dict):
        return clean, ["Saved profile was unreadable — restored safe defaults."]
    warnings = []
    lo, lo_ok = _coerce_pref(profile.get("exp_pref_min"), _PREF_MIN_DEFAULT)
    hi, hi_ok = _coerce_pref(profile.get("exp_pref_max"), _PREF_MAX_DEFAULT)
    if not lo_ok:
        warnings.append(
            "Saved minimum experience was invalid — restored to "
            f"{_PREF_MIN_DEFAULT:g} years."
        )
    if not hi_ok:
        warnings.append(
            "Saved maximum experience was invalid — restored to "
            f"{_PREF_MAX_DEFAULT:g} years."
        )
    if lo_ok and hi_ok and lo > hi:
        lo, hi = _PREF_MIN_DEFAULT, _PREF_MAX_DEFAULT
        warnings.append(
            "Saved experience range was invalid (min above max) — "
            "restored to defaults."
        )
    clean["exp_pref_min"], clean["exp_pref_max"] = lo, hi
    if isinstance(profile.get("query"), str) and profile["query"].strip():
        clean["query"] = profile["query"]
    raw_skills = profile.get("skills")
    if isinstance(raw_skills, list):
        known = [s for s in raw_skills if s in SKILL_CANONICAL]
        if len(known) != len(raw_skills):
            warnings.append(
                "Saved skills contained unknown entries — kept recognized ones."
            )
        clean["skills"] = known
    years = profile.get("experience_years")
    if (
        isinstance(years, (int, float))
        and not isinstance(years, bool)
        and math.isfinite(float(years))
        and 0.0 <= float(years) <= 30.0
    ):
        clean["experience_years"] = float(years)
    raw_roles = profile.get("target_roles")
    if isinstance(raw_roles, list):
        roles = [r.strip() for r in raw_roles if isinstance(r, str) and r.strip()]
        if len(roles) != len(raw_roles):
            warnings.append(
                "Saved target roles contained empty entries — kept recognized ones."
            )
        clean["target_roles"] = roles
    elif "target_roles" in profile:
        warnings.append("Saved target roles were invalid — restored to no restriction.")
    score = profile.get("min_score")
    if (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
        and 0.0 <= float(score) <= 100.0
    ):
        clean["min_score"] = int(score)
    elif "min_score" in profile:
        warnings.append("Saved minimum score was invalid — restored to 0.")
    recency = profile.get("posted_within")
    if recency is None or (
        isinstance(recency, int) and not isinstance(recency, bool) and recency in (7, 14, 30)
    ):
        clean["posted_within"] = recency
    elif "posted_within" in profile:
        warnings.append("Saved recency preference was invalid — restored to Any time.")
    return clean, warnings


def parse_target_roles(text):
    """Split comma-separated role input into normalized role names (pure)."""
    if not isinstance(text, str):
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def build_profile_payload(
    pref_min,
    pref_max,
    query,
    skills,
    experience_years,
    target_roles,
    min_score,
    posted_within,
):
    """Validate a full preferences payload; raises ValueError on invalid.

    Pure: performs no I/O. Accepted values mirror the sidebar widgets,
    so a payload built from them validates unless the range is inverted.
    """
    problems = []
    lo, lo_ok = _coerce_pref(pref_min, _PREF_MIN_DEFAULT)
    hi, hi_ok = _coerce_pref(pref_max, _PREF_MAX_DEFAULT)
    if not lo_ok or not hi_ok:
        problems.append("experience preferences must be numbers from 0 to 20")
    elif lo > hi:
        problems.append("minimum experience must not exceed maximum experience")
    clean_query = query if isinstance(query, str) and query.strip() else "java"
    clean_skills = (
        [s for s in skills if s in SKILL_CANONICAL]
        if isinstance(skills, list)
        else []
    )
    if (
        experience_years is not None
        and not (
            isinstance(experience_years, (int, float))
            and not isinstance(experience_years, bool)
            and math.isfinite(float(experience_years))
            and 0.0 <= float(experience_years) <= 30.0
        )
    ):
        problems.append("candidate experience must be empty or 0–30 years")
    clean_roles = parse_target_roles(",".join(target_roles)) if isinstance(
        target_roles, list
    ) else parse_target_roles(target_roles)
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
        problems.append("minimum score must be a number from 0 to 100")
        clean_score = _MIN_SCORE_DEFAULT
    else:
        clean_score = int(min_score)
        if not math.isfinite(float(min_score)) or not 0 <= clean_score <= 100:
            problems.append("minimum score must be a number from 0 to 100")
            clean_score = _MIN_SCORE_DEFAULT
    if posted_within not in (None, 7, 14, 30):
        problems.append("recency preference must be Any time or 7/14/30 days")
        clean_within = None
    else:
        clean_within = posted_within
    if problems:
        raise ValueError("; ".join(problems))
    return {
        "exp_pref_min": lo,
        "exp_pref_max": hi,
        "query": clean_query,
        "skills": clean_skills,
        "experience_years": (
            None if experience_years is None else float(experience_years)
        ),
        "target_roles": clean_roles,
        "min_score": clean_score,
        "posted_within": clean_within,
    }


def save_preferences(payload):
    """Persist a validated payload atomically. Pure I/O, no network."""
    return storage.save_store("profile", payload)


# ---------------------------------------------------------------- pure pipeline
def build_results(raw_jobs, candidate, pref_min, pref_max):
    """Filter + rank + attach reasons/flags. Pure: no network, no I/O."""
    filtered = job_filters.filter_jobs(raw_jobs, candidate, pref_min, pref_max)
    ranked = matcher.rank_jobs(
        candidate.get("skills", []), [entry["job"] for entry in filtered["kept"]]
    )
    return views.attach_filter_info(ranked, filtered), filtered["rejected"]


def load_cached_jobs():
    """Return previously cached jobs (or []) without any network call."""
    try:
        cached = storage.load_store("cached_jobs", default={})
    except storage.StorageError:
        return [], None
    if not isinstance(cached, dict) or not isinstance(cached.get("jobs"), list):
        return [], None
    return cached["jobs"], cached.get("fetched_at")


def load_profile():
    """Return saved preferences (or {}) without raising on storage issues."""
    try:
        profile = storage.load_store("profile", default={})
    except storage.StorageError:
        return {}
    return profile if isinstance(profile, dict) else {}


# ---------------------------------------------------------------- UI pieces
def _candidate_from_resume(parsed, edited_skills):
    return {
        "skills": list(edited_skills),
        "experience_years": parsed["experience_years"],
        "experience_confidence": parsed["experience_confidence"],
        "role_hint": parsed["role_hint"],
    }


def _candidate_from_manual(skills, exp_mode, exp_years):
    years = 0.0 if exp_mode == "Fresher / entry level" else exp_years
    if exp_mode.startswith("Unknown"):
        years = None
    return {
        "skills": list(skills),
        "experience_years": years,
        "experience_confidence": (
            "explicit" if years is not None else "unknown"
        ),
        "role_hint": None,
    }


def _render_card(entry):
    job, match = entry["job"], entry["match"]
    title = job.get("title") or "Untitled role"
    company = job.get("company")
    header = title if not company else f"{title} — {company}"
    st.subheader(header)
    meta = " · ".join(
        part
        for part in (
            job.get("location"),
            job.get("work_mode"),
            f"Match {match.get('score', 0)}% (skill overlap)",
            job.get("posted_date"),
            f"via {job.get('source')}",
        )
        if part
    )
    if meta:
        st.caption(meta)
    matched = match.get("matched_skills") or []
    missing = match.get("missing_skills") or []
    st.write(f"**Matched:** {', '.join(matched) if matched else '—'}")
    st.write(f"**Missing:** {', '.join(missing) if missing else '—'}")
    url = job.get("apply_url") or job.get("source_url")
    if url:
        st.link_button("Apply (original listing)", url)
    else:
        st.caption("No application link was provided by this source.")
    with st.expander("Why this matches"):
        for reason in entry.get("reasons", []) or match.get("reasons", []):
            st.write(f"- {reason}")
        if "needs-review" in entry.get("flags", []):
            st.warning("Flagged for manual review (unclear location or role signal).")


def main():
    st.set_page_config(page_title=config.APP_NAME, layout="wide")
    st.title(config.APP_NAME)
    st.caption(
        "Local-only job matcher. Scores measure skill overlap with each "
        "listing — not hiring probability."
    )

    profile, profile_warnings = sanitize_profile(load_profile())
    for warning in profile_warnings:
        st.warning(warning)

    # ---------------------------------------------------------- sidebar
    with st.sidebar:
        st.header("Experience preferences")
        pref_min = st.number_input(
            "Min required experience (yrs)",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            value=profile["exp_pref_min"],
        )
        pref_max = st.number_input(
            "Max required experience (yrs)",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            value=profile["exp_pref_max"],
        )
        st.caption(
            "Jobs are kept only when evidence shows they fit this window. "
            "Default 0–2 keeps the strict policy; set 3–4 to retarget."
        )
        st.header("Job search")
        query = st.text_input("Keywords", value=profile["query"])
        limit = st.slider("Results per source", 5, 50, 20)
        st.header("Role & result preferences")
        roles_text = st.text_input(
            "Target roles (comma-separated, optional)",
            value=", ".join(profile["target_roles"]),
        )
        min_score = st.slider("Minimum match score", 0, 100, int(profile["min_score"]))
        recency_label = st.selectbox(
            "Posted within",
            _POSTED_WITHIN_OPTIONS,
            index=_POSTED_WITHIN_OPTIONS.index(
                next(
                    (
                        label
                        for label, days in _POSTED_WITHIN_DAYS.items()
                        if days == profile["posted_within"]
                    ),
                    "Any time",
                )
            ),
        )
        save_clicked = st.button("Save preferences")
        with st.expander("Adzuna key (optional)"):
            st.caption(
                "Only needed for India listings. The app works without it. "
                "Keys are used for one request and never stored."
            )
            adzuna_id = st.text_input("App ID", value="", type="password")
            adzuna_key = st.text_input("App key", value="", type="password")
        fetch_clicked = st.button("Fetch / refresh jobs", type="primary")

    if pref_min > pref_max:
        st.error("Min experience must not exceed max experience.")
        return

    # ---------------------------------------------------------- resume
    st.header("1. Resume")
    upload = st.file_uploader("Upload resume (PDF, parsed in memory)", type=["pdf"])
    parsed = st.session_state.get("parsed_resume")
    if upload is not None and (
        parsed is None or parsed.get("source") != upload.name
    ):
        try:
            with st.spinner("Parsing resume…"):
                parsed = resume_parser.parse_pdf_bytes(upload.getvalue(), upload.name)
            st.session_state["parsed_resume"] = parsed
            st.success(f"Parsed {len(parsed['skills'])} skills from {upload.name}.")
        except resume_parser.EncryptedResumeError:
            st.error(
                "This PDF is password-protected and cannot be read. "
                "Nothing was saved; use the manual profile below instead."
            )
            parsed = None
        except resume_parser.ResumeParseError as exc:
            st.error(f"Could not read this PDF ({exc}). Nothing was saved.")
            parsed = None

    use_manual = st.checkbox(
        "Enter profile manually instead of resume", value=parsed is None
    )
    if parsed is not None and not use_manual:
        edited = st.multiselect(
            "Skills (editable)",
            options=list(SKILL_CANONICAL),
            default=[s for s in parsed["skills"] if s in SKILL_CANONICAL],
        )
        years = parsed["experience_years"]
        if years is None:
            st.warning(
                "Resume experience is unknown — it is NOT treated as zero. "
                "Eligibility stays conservative until you confirm it below."
            )
        else:
            st.write(
                f"Experience: **{years:g} yrs** "
                f"({parsed['experience_confidence']}"
                + (
                    f", evidence: {parsed['experience_text']!r}"
                    if parsed["experience_text"]
                    else ""
                )
                + ")"
            )
        for warning in parsed["warnings"]:
            st.warning(warning)
        if parsed["role_hint"]:
            st.write(
                f"Detected direction: **{parsed['role_hint']}** "
                "(from resume skills; used leniently in role filtering)."
            )
        else:
            st.caption(
                "No clear role direction detected in the resume — "
                "role filtering stays lenient."
            )
        candidate = _candidate_from_resume(parsed, edited)
    else:
        manual_skills = st.multiselect(
            "Skills", options=list(SKILL_CANONICAL), default=[]
        )
        exp_mode = st.radio(
            "Experience",
            ["Unknown (recommended if unsure)", "Fresher / entry level", "Exact years"],
        )
        exp_years = st.number_input(
            "Years", min_value=0.0, max_value=30.0, step=0.5, value=0.0
        )
        if exp_mode.startswith("Unknown"):
            st.info("Unknown experience is never treated as zero.")
        candidate = _candidate_from_manual(manual_skills, exp_mode, exp_years)

    if save_clicked:
        try:
            payload = build_profile_payload(
                pref_min,
                pref_max,
                query,
                candidate["skills"],
                candidate["experience_years"],
                parse_target_roles(roles_text),
                min_score,
                _POSTED_WITHIN_DAYS[recency_label],
            )
            save_preferences(payload)
            st.success("Preferences saved locally (no jobs fetched).")
        except ValueError as exc:
            st.error(f"Preferences not saved: {exc}")
        except storage.StorageError as exc:
            st.error(f"Preferences not saved: {exc}")

    # ---------------------------------------------------------- fetch
    st.header("2. Jobs")
    if fetch_clicked:
        try:
            with st.spinner("Fetching from free job sources…"):
                fetched = job_sources.fetch_all_jobs(
                    query=query,
                    limit_per_source=limit,
                    adzuna_app_id=adzuna_id or None,
                    adzuna_app_key=adzuna_key or None,
                )
            st.session_state["raw_jobs"] = fetched["jobs"]
            st.session_state["fetch_errors"] = fetched["errors"]
            st.session_state["fetched_at"] = fetched["fetched_at"]
            try:
                storage.save_store(
                    "cached_jobs",
                    {
                        "fetched_at": fetched["fetched_at"],
                        "query": query,
                        "jobs": fetched["jobs"],
                    },
                )
                storage.save_store(
                    "profile",
                    {
                        "exp_pref_min": pref_min,
                        "exp_pref_max": pref_max,
                        "query": query,
                        "skills": candidate["skills"],
                        "experience_years": candidate["experience_years"],
                        "target_roles": parse_target_roles(roles_text),
                        "min_score": min_score,
                        "posted_within": _POSTED_WITHIN_DAYS[recency_label],
                    },
                )
            except storage.StorageError as exc:
                st.warning(f"Fetched jobs shown, but local cache failed: {exc}")
            st.success(
                f"Fetched {len(fetched['jobs'])} jobs "
                f"({', '.join(fetched['sources_attempted'])})."
            )
        except Exception as exc:  # last-resort guard; adapters raise SourceError
            st.error(f"Job fetch failed: {exc}")

    if "raw_jobs" not in st.session_state:
        cached_jobs, cached_at = load_cached_jobs()
        if cached_jobs:
            st.session_state["raw_jobs"] = cached_jobs
            st.session_state["fetch_errors"] = []
            st.session_state["fetched_at"] = cached_at
            st.info(f"Showing {len(cached_jobs)} cached jobs from {cached_at}.")
    for source, message in [
        (e.get("source"), e.get("error")) for e in st.session_state.get("fetch_errors", [])
    ]:
        st.warning(f"{source} unavailable: {message}")

    raw_jobs = st.session_state.get("raw_jobs", [])
    if not raw_jobs:
        st.info("No jobs yet — use “Fetch / refresh jobs” in the sidebar.")
        return

    merged, rejected = build_results(raw_jobs, candidate, pref_min, pref_max)

    # ---------------------------------------------------------- local filters
    st.header("3. Filter & sort (no refetch)")
    col1, col2 = st.columns(2)
    role_keyword = col1.text_input("Role keyword")
    location = col2.text_input("Location contains")
    modes = sorted({j.get("work_mode") or "unknown" for j in raw_jobs})
    sources = sorted({str(j.get("source")) for j in raw_jobs})
    col3, col4, col5 = st.columns(3)
    sel_modes = col3.multiselect("Work mode", modes, default=modes)
    sel_sources = col4.multiselect("Source", sources, default=sources)
    sel_skills = col5.multiselect(
        "Require job skill", list(SKILL_CANONICAL), default=[]
    )
    skill_match = st.radio("Skill filter mode", ("Any", "All"), horizontal=True)
    recency_days = _POSTED_WITHIN_DAYS[recency_label]
    sort_by = st.selectbox("Sort by", views.SORT_OPTIONS, index=0)
    shown = views.sort_results(
        views.apply_local_filters(
            merged,
            role_keyword=role_keyword,
            skills=sel_skills,
            location=location,
            work_modes=sel_modes,
            sources=sel_sources,
            min_score=min_score,
            posted_within_days=recency_days,
            skill_match=skill_match.lower(),
            target_roles=parse_target_roles(roles_text),
        ),
        sort_by,
    )
    if recency_days is not None:
        st.caption(
            "Recency filter active: jobs with unknown or invalid posting "
            "dates are excluded (their dates cannot be verified)."
        )
    if not shown and merged:
        st.info("No jobs match these filters — loosen the criteria.")
        return

    # ---------------------------------------------------------- results
    st.header(f"4. Results ({len(shown)} shown)")
    st.caption(_SCORE_HELP)
    eligible = [e for e in shown if "needs-review" not in e.get("flags", [])]
    review = [e for e in shown if "needs-review" in e.get("flags", [])]
    st.subheader(f"Eligible ({len(eligible)})")
    for entry in eligible:
        _render_card(entry)
    if review:
        st.subheader(f"Needs review ({len(review)})")
        st.caption("Kept, but location or role signal was unclear — check manually.")
        for entry in review:
            _render_card(entry)
    if rejected:
        with st.expander(f"Excluded jobs ({len(rejected)}) with reasons"):
            for entry in rejected:
                job = entry["job"]
                st.write(f"**{job.get('title') or 'Untitled'}** — {job.get('company') or '?'}")
                for reason in entry["reasons"]:
                    st.write(f"- {reason}")


if __name__ == "__main__":
    main()
