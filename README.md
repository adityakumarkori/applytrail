# JobStar — local-only Job Finder (MVP)

Personal, free, offline-first job matcher. Upload a resume PDF, fetch
jobs from free sources, and browse explainable skill-overlap matches
with real application links. No login, database, Docker, or paid APIs.

## Setup

```powershell
cd D:\Aditya\Projects\JobStar
pip install -r requirements.txt
```

Dependencies (unchanged): `streamlit`, `requests`, `pypdf`, `pytest`.
No API keys are required. An optional free Adzuna key (see
https://developer.adzuna.com) unlocks India listings; without it the
other sources still work.

## Run

```powershell
streamlit run app.py
```

Then open http://localhost:8501 and:

1. Upload your resume PDF (parsed in memory; editable skills shown).
2. Set experience preferences (default 0–2 years; editable, e.g. 3–4).
3. Click **Fetch / refresh jobs** (the only network action).
4. Filter/sort the fetched results locally and open Apply links.

Fetched jobs are cached to `data/` (git-ignored). Adzuna keys can be
entered in the sidebar or via `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`
environment variables; they are never stored or displayed.

## Tests

```powershell
python -m pytest -q
```

All HTTP-dependent tests use mocked responses; the suite makes no live
network calls.
