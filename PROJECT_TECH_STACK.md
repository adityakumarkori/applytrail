# Job Finder – Tech Stack & Project Idea

## 1. Idea in 5 Lines
1. User uploads resume PDF locally.
2. App extracts skills, experience, target role offline for free.
3. App fetches jobs from free job APIs matching those skills.
4. App ranks jobs by match % and shows skill gaps + Apply link + cover letter.
5. User clicks Apply and submits manually. No paid API, no server, no database.

## 2. Problem We Solve
- Job seekers waste time on Naukri / Indeed / LinkedIn with irrelevant jobs.
- Official career pages (Greenhouse, Workday, etc.) are scattered.
- No free, small, local tool that reads *my* resume and filters jobs for *my* skills.

## 3. Scope – What We WILL Do
- Resume upload (PDF) + skill extraction (offline).
- Skill editing + target role + location filter.
- Free job fetch + match % ranking.
- Job cards: title, company, location, match %, missing skills, Apply link.
- Profile save (name, email, phone) for fast copy-paste into forms.
- Auto cover-letter text generation.
- Save / Applied tracking in local JSON.
- Runs 100% local, 100% free.

## 4. Scope – What We WILL NOT Do (Why)
- No full auto-submit bot on Naukri / Indeed / LinkedIn / Workday.
- Reason: login + OTP, CAPTCHA / Cloudflare, no official free API, account ban risk, breaks weekly.
- We do **assist-apply**: pre-fill + 1-click open, user presses Submit. Smooth + safe.

## 5. Tech Stack – Now (MVP)
- **Language:** Python 3.10+
- **UI:** Streamlit (1 file, no frontend build)
- **Resume parse:** pypdf + regex + 60-skill dictionary (offline, free)
- **Job fetch:** requests
  - Arbeitnow API – free, no key – `https://arbeitnow.com/api/job-board-api`
  - RemoteOK API – free, no key – `https://remoteok.com/api`
  - Remotive API – free, no key
  - Adzuna API – free 1000 calls/month, needs free key – required for India jobs
- **Matching:** scikit-learn (TF-IDF / keyword overlap)
- **Storage:** local JSON – `data/profile.json`, `data/jobs.json` – no DB
- **Run:** no Docker, no hosting

```
pip install streamlit requests pypdf scikit-learn
streamlit run app.py
```
- Frontend: http://localhost:8501

## 6. Why Not React / Next.js Now
- Streamlit = fastest MVP, 5 files, <300 lines, Python only.
- React (Vite) + Tailwind = beautiful UI but needs Node, 15+ files, API proxy – overkill to validate idea.
- Next.js = heavier (SSR/server), no benefit for local tool.
- Decision: Build Streamlit now. If it works, switch frontend to React later.

## 7. React-Ready Rule (Important)
Keep logic decoupled from UI so switch is easy:
- `app.py` = UI only, no job logic inside.
- `resume.py`, `jobs.py`, `match.py` = pure functions, reusable.
- Later: keep those 3 files, add `main.py (FastAPI)` + `frontend/ (Vite React)` – zero logic rewrite.

## 8. File Structure
```
HACK/
  app.py
  resume.py        # parse_resume(pdf_path) -> {skills, exp, role}
  jobs.py          # fetch_jobs(keywords, location) -> [jobs]
  match.py         # score(resume_skills, job_desc) -> % + gaps
  requirements.txt
  data/
    profile.json
    jobs.json
  uploads/
```

## 9. App Flow
1. Sidebar: Profile form + target role/location + Adzuna key (optional).
2. Upload resume -> show extracted skills as editable chips.
3. Click Find Jobs -> fetch + rank.
4. Job cards sorted by match % with Apply / Save / Copy Cover Letter.
5. Restart app -> profile + saved jobs persist.

## 10. Backend Logic (No Code Yet)
- `POST /upload-resume` concept: parse PDF -> return skills.
- `GET /jobs?skill=python&location=india` concept: aggregate APIs.
- `POST /match` concept: rank list.
- In Streamlit these are direct function calls, not HTTP. Same functions become FastAPI endpoints later.

## 11. Future – React + Deploy
- Frontend: Vercel / Netlify free – Vite React + Tailwind.
- Backend: Render / Railway free – FastAPI wrapping same 3 files.
- Change only `VITE_API_URL` from `localhost:8000` to deployed URL.
- Optional Phase 2: tiny Chrome extension to autofill Naukri/Indeed forms from `profile.json`.

## 12. Verification Checklist
- [ ] Upload PDF -> skills appear in <5 sec.
- [ ] Search `python + india` -> 20+ results with %.
- [ ] Apply opens real company URL.
- [ ] Restart -> profile persists.
- [ ] No paid API, no error without Adzuna key (remote jobs still work).

## 13. What We Need Next
1. Target role + location (e.g. Python fresher, India).
2. `python --version` + `pip --version` output.
3. Sample resume PDF to test parsing.
4. Approval to start build in `app.py` -> `resume.py` -> `jobs.py` -> `match.py` order.
