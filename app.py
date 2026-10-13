"""Phase 1 — Streamlit placeholder UI only.

No resume parsing, job fetching, matching, or cover letters here.
Verifies config + storage wiring and persistence across restarts.
"""

import streamlit as st

import config
import storage


st.title(config.APP_NAME)
st.caption("Phase 1: foundation — config + local JSON storage smoke test.")

st.subheader("Preferences (from config.py)")
st.write(
    {
        "primary_skills": list(config.PRIMARY_SKILLS),
        "secondary_skills": list(config.SECONDARY_SKILLS),
        "locations": list(config.LOCATIONS),
        "work_modes": list(config.WORK_MODES_PRIORITY),
        "experience": (
            f"{config.EXP_MIN_YEARS}-{config.EXP_MAX_STRICT_YEARS} yrs strict; "
            f"up to {config.EXP_MAX_CONDITIONAL_YEARS} only if explicitly "
            "eligible for 0-2"
        ),
    }
)

st.subheader("Storage check")
try:
    profile = storage.load_store("profile", default={})
    st.success(f"Storage OK — profile store: {storage.store_path('profile').name}")
    st.json(profile if profile else {"note": "empty profile (expected on first run)"})
except storage.StorageCorruptedError as exc:
    st.error(str(exc))
    st.info("Original file left untouched — fix or remove it manually, then reload.")
except storage.StorageError as exc:
    st.error(str(exc))

st.info("Phase 2+ will add resume parsing, job sources, and matching.")
