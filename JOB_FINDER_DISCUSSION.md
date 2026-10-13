# Job Finder - Discussion Summary

Date: 2026-10-13
Location: `D:\Aditya\Linux\HACK`

## 1. User Requirement
Build a job finder that:
- Reads resume + skills
- Finds matching jobs
- Automatically fills application details
- Covers official company career pages + portals like Naukri, Indeed, etc.
- 100% free, small size, works smoothly

## 2. Conclusion
Yes, we can build it free and lean, but **NOT as full auto-apply bot**.

**Possible (free + smooth):**
- Upload PDF resume -> extract skills, experience, role
- Auto-search jobs matching skills
- Show match % + skill gaps + direct Apply link
- Autofill helper: name, email, phone, skills, cover letter pre-filled, user clicks Submit
- Local applied/saved tracking

**Not possible smooth + free:**
- 100% auto-submit on Naukri / Indeed / LinkedIn / Workday / Greenhouse
- Reasons: login + OTP, CAPTCHA / Cloudflare, no official free API, ToS ban risk, breaks weekly, needs paid proxies/solvers

Recommended approach: **matcher + assist-apply**, not bot-apply.

## 3. Proposed Lean Plan
Stack: Python + Streamlit, local only, no hosting / DB cost.

Files (~3-4, <300 lines):
- `app.py` - UI + upload + results
- `profile.json` - user details for autofill
- `jobs.json` - cache
- `cover_letter.txt` - generated

Flow:
1. Upload resume PDF -> `pypdf + regex` skill extraction (offline, free)
2. Fetch jobs from free APIs -> keyword / TF-IDF match score
3. Show matched jobs + Apply link + generated cover letter
4. Autofill via profile JSON + Chrome snippet (Phase 2: tiny extension)

Free job sources:
- Arbeitnow API - free, no key, direct ATS jobs
- RemoteOK API - free, no key
- Remotive API - free, no key
- Adzuna API - free 1000 calls/month, needs free key, required for India jobs

Run:
```
pip install streamlit requests pypdf scikit-learn
streamlit run app.py
```

## 4. Pending Decisions (User)
1. Target roles + location? e.g. Fresher Python in India / Remote frontend?
2. Accept assist-apply (recommended) or insist on full auto-apply bot?
3. Tech: a) Python+Streamlit b) HTML/JS only c) Chrome extension?
4. Resume format? PDF? Share skills list for matching dictionary?
