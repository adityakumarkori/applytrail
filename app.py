"""Phase 5 — first usable Streamlit interface (local-only, no login/DB).

UI-only module: all ranking, filtering, parsing, and fetching logic
lives in core/* + storage. Network happens only inside the Fetch button
handler; everything else (including all reruns) works on in-memory or
locally cached data. Uploaded PDFs are parsed in memory and never
written to disk. Adzuna credentials are kept in a local variable for
the single request and never persisted or displayed.
"""

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

    profile = load_profile()

    # ---------------------------------------------------------- sidebar
    with st.sidebar:
        st.header("Experience preferences")
        pref_min = st.number_input(
            "Min required experience (yrs)",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            value=float(profile.get("exp_pref_min", config.EXP_MIN_YEARS)),
        )
        pref_max = st.number_input(
            "Max required experience (yrs)",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            value=float(profile.get("exp_pref_max", config.EXP_MAX_STRICT_YEARS)),
        )
        st.caption(
            "Jobs are kept only when evidence shows they fit this window. "
            "Default 0–2 keeps the strict policy; set 3–4 to retarget."
        )
        st.header("Job search")
        query = st.text_input("Keywords", value=str(profile.get("query", "java")))
        limit = st.slider("Results per source", 5, 50, 20)
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
    sort_by = st.selectbox("Sort by", views.SORT_OPTIONS, index=0)
    shown = views.sort_results(
        views.apply_local_filters(
            merged,
            role_keyword=role_keyword,
            skills=sel_skills,
            location=location,
            work_modes=sel_modes,
            sources=sel_sources,
        ),
        sort_by,
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
