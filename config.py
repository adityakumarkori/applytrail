"""Phase 1 — central constants for the local Job Finder MVP.

Stdlib only. No Streamlit, network, or file I/O here so the module stays
reusable from a future backend.
"""

APP_NAME = "Job Finder (local MVP)"

# Role priority: Java / Spring Boot / backend first, Python / FastAPI second.
PRIMARY_SKILLS = ("java", "spring boot", "spring", "backend")
SECONDARY_SKILLS = ("python", "fastapi")

# Search scope: India-wide, remote and hybrid first.
LOCATIONS = ("India",)
WORK_MODES_PRIORITY = ("remote", "hybrid", "onsite")

# Strict experience policy (years):
# - Accept 0-2 by default.
# - Accept 0-3 ONLY when the listing explicitly confirms eligibility
#   for candidates with 0-2 years.
# - Exclude anything requiring > 2 years or with unclear eligibility.
EXP_MIN_YEARS = 0
EXP_MAX_STRICT_YEARS = 2
EXP_MAX_CONDITIONAL_YEARS = 3

# Free job sources (no mandatory keys; Adzuna key always optional).
SOURCES = {
    "arbeitnow": "https://arbeitnow.com/api/job-board-api",
    "remoteok": "https://remoteok.com/api",
    "remotive": "https://remotive.com/api/remote-jobs",
    "adzuna": "https://api.adzuna.com/v1/api/jobs/in/search/1",
}
REQUEST_TIMEOUT_SECONDS = 15

# Local JSON stores (relative to project root).
DATA_DIR = "data"
STORES = {
    "profile": "profile.json",
    "cached_jobs": "jobs.json",
    "saved_jobs": "saved_jobs.json",
    "applications": "applications.json",
}
