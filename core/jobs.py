"""Phase 3 — free job-source adapters and normalized aggregation.

Dependencies: stdlib + `requests` + `config` only. No Streamlit, sklearn,
matching, caching, or UI, so the module stays reusable from a future backend.

Providers (all GET, JSON, polite single-shot calls with timeouts):
- Arbeitnow: free, no key, Europe-weighted, no server-side search
  (query is filtered client-side).
- RemoteOK: free, no key, requires a `User-Agent` header; first payload
  element is a legal notice (skipped); remote-only feed.
- Remotive: free, no key, supports `search`/`limit` params; max ~4
  fetches/day per provider guidance (caller policy, not enforced here).
- Adzuna: optional; needs free `app_id`/`app_key` (explicit args or
  `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` env vars). Missing credentials
  return [] and never break other sources. Credentials are never
  logged or included in error messages.

Attribution: every normalized job keeps its provider name in `source`
and the original listing page in `source_url` — the future UI must
display both (required by RemoteOK/Remotive terms). A separate
optional `direct_apply_url` holds a real company application URL only
when one can be reliably extracted from the already-fetched
description; it is None otherwise and never overwrites `source_url`.

Never fabricate: items missing both title and URL are skipped (None);
unknown fields become None/"unknown", never invented values.
"""

import os
import re
import urllib.parse
from datetime import datetime, timezone

import requests

import config

DEFAULT_LIMIT = 20
USER_AGENT = "JobStar-local-personal/1.0"

JOB_KEYS = (
    "id",
    "title",
    "company",
    "location",
    "work_mode",
    "description",
    "source",
    "source_url",
    "apply_url",
    "direct_apply_url",
    "posted_date",
    "fetched_at",
)


class SourceError(Exception):
    """Transport or response-validation failure for one job source."""


# ATS hosts treated as direct company application pages when a full
# HTTP(S) URL is present in an already-fetched description. Suffix
# match so regional subdomains keep working. A bare hostname with no
# URL is never enough (extraction returns None in that case).
_ATS_SUFFIXES = (
    "boards.greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
)

_URL_RE = re.compile(r"https?://[^\s\"'<>\)\]\[]+")
_APPLY_HINT_RE = re.compile(r"apply", re.IGNORECASE)


def _clean_url_candidate(raw):
    """Trim trailing punctuation/HTML artifacts; unescape &amp;."""
    text = (raw or "").replace("&amp;", "&").strip()
    # Strip trailing sentence/HTML/markdown punctuation, not URL internals.
    while text and text[-1] in ".,;:!?)]}'\"":
        text = text[:-1]
    # Strip a stray opening wrap left by "(<url>" style text.
    while text and text[0] in "(<[":
        text = text[1:]
    return text


def _valid_http_url(url):
    """True when url is a usable absolute HTTP(S) URL with a dotted host."""
    if not isinstance(url, str):
        return False
    text = url.strip()
    if not text:
        return False
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        return False
    if not parts.path and not parts.query:
        # Host-only URLs (e.g. "https://boards.greenhouse.io") carry no
        # job-specific target; still a real URL but not a direct apply link.
        # Keep them out to avoid overstating "direct application" proof.
        return False
    if re.search(r"\s", text):
        return False
    return True


def _is_ats_url(url):
    """True when a validated URL sits on a supported ATS host."""
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ATS_SUFFIXES)


def extract_direct_apply_url(description):
    """Extract one direct company application URL from description text.

    Pure, stdlib-only, never fetches. Scans already-fetched
    descriptions for the first HTTP(S) URL that is either on a
    supported ATS host (Greenhouse, Lever, Ashby, Workday,
    SmartRecruiters, iCIMS, Jobvite) or explicitly framed as an apply
    link (the ~60 chars before it mention "apply"). Malformed, unsafe
    (non-http(s)), hostless, or ambiguous text returns None. Never
    invents links and never treats a bare ATS hostname as a URL.
    """
    if not isinstance(description, str) or not description.strip():
        return None
    for match in _URL_RE.finditer(description):
        candidate = _clean_url_candidate(match.group(0))
        if not _valid_http_url(candidate):
            continue
        if _is_ats_url(candidate):
            return candidate
        window_start = max(0, match.start() - 60)
        if _APPLY_HINT_RE.search(description[window_start:match.start()]):
            return candidate
    return None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _sanitize(message, secrets):
    """Redact secrets from error text, including URL-encoded forms.

    Request libraries percent-encode query params, so an error string
    may carry ``quote``/``quote_plus`` spellings of a key instead of the
    raw value. All spellings are replaced, longest first, so a short
    secret can never corrupt (and thereby preserve part of) a longer
    encoded form. Pure stdlib, never raises.
    """
    text = str(message)
    variants = set()
    for secret in secrets:
        if not secret:
            continue
        variants.add(secret)
        try:
            variants.add(urllib.parse.quote(secret, safe=""))
            variants.add(urllib.parse.quote_plus(secret))
        except Exception:
            pass
    for variant in sorted(variants, key=len, reverse=True):
        if variant:
            text = text.replace(variant, "***")
    return text


def _get_json(url, params=None, timeout=None, label="source"):
    """GET JSON with timeout; raise SourceError on any failure."""
    timeout = config.REQUEST_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            if getattr(response, "status_code", None) == 429:
                raise SourceError(
                    f"{label} rate limited (HTTP 429 — too many requests; "
                    "wait a while before fetching again)"
                ) from exc
            raise SourceError(f"{label} request failed: {exc}") from exc
        return response.json()
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(f"{label} request failed: {exc}") from exc


def _iso_from_unix(value):
    try:
        if isinstance(value, bool):
            return None
        stamp = float(value)
        return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _iso_from_any(value):
    """Best-effort timestamp -> ISO string, else None (never invented)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _iso_from_unix(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.fullmatch(r"\d{9,12}", text):
            return _iso_from_unix(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def deduce_work_mode(*texts, remote_flag=None):
    """Infer remote|hybrid|onsite|unknown from free text (+ optional flag)."""
    blob = " ".join(t for t in texts if isinstance(t, str)).lower()
    if re.search(r"\bhybrid\b", blob):
        return "hybrid"
    if (
        re.search(r"\bremote\b|work from home|\bwfh\b|worldwide", blob)
        or remote_flag is True
    ):
        return "remote"
    if re.search(r"\bon[\s-]?site\b|\boffice\b|onsite", blob):
        return "onsite"
    return "unknown"


def _matches_query(parts, query):
    query = (query or "").strip().lower()
    if not query:
        return True
    blob = " ".join(str(p or "") for p in parts).lower()
    return query in blob


def _base_job(source, external_id, title, url):
    """Return None when both title and URL are missing (never fabricate)."""
    title = (title or "").strip() if isinstance(title, str) else ""
    url = (url or "").strip() if isinstance(url, str) else ""
    if not title and not url:
        return None
    return {
        "id": f"{source}:{external_id}" if external_id else f"{source}:{url or title}",
        "title": title or None,
        "source": source,
        "source_url": url or None,
        "apply_url": url or None,
        "direct_apply_url": None,
    }


def normalize_arbeitnow_item(raw, now=None):
    """Normalize one Arbeitnow `data` entry; None when unusable."""
    if not isinstance(raw, dict):
        return None
    base = _base_job("arbeitnow", raw.get("slug"), raw.get("title"), raw.get("url"))
    if base is None:
        return None
    now = now or _now_iso()
    location = raw.get("location") or None
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    remote_flag = raw.get("remote") if isinstance(raw.get("remote"), bool) else None
    return {
        **base,
        "company": raw.get("company_name") or None,
        "location": location,
        "work_mode": deduce_work_mode(
            location or "", description, " ".join(map(str, tags)), remote_flag=remote_flag
        ),
        "description": description,
        "direct_apply_url": extract_direct_apply_url(description),
        "posted_date": _iso_from_any(raw.get("created_at")),
        "fetched_at": now,
    }


def normalize_remoteok_item(raw, now=None):
    """Normalize one RemoteOK entry; None for legal notice / unusable rows."""
    if not isinstance(raw, dict):
        return None
    title = raw.get("position") or raw.get("title")
    url = raw.get("url") or raw.get("apply_url")
    base = _base_job("remoteok", raw.get("id") or raw.get("slug"), title, url)
    if base is None:
        return None
    now = now or _now_iso()
    tags = raw.get("tags") if isinstance(raw.get("tags"), list) else []
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    location = raw.get("location") or None
    posted = _iso_from_any(raw.get("date"))
    if posted is None:
        posted = _iso_from_any(raw.get("epoch"))
    return {
        **base,
        "company": raw.get("company") or None,
        "location": location,
        "work_mode": deduce_work_mode(
            location or "", description, " ".join(map(str, tags)), remote_flag=True
        ),
        "description": description,
        "direct_apply_url": extract_direct_apply_url(description),
        "posted_date": posted,
        "fetched_at": now,
    }


def normalize_remotive_item(raw, now=None):
    """Normalize one Remotive `jobs` entry; None when unusable."""
    if not isinstance(raw, dict):
        return None
    base = _base_job("remotive", raw.get("id"), raw.get("title"), raw.get("url"))
    if base is None:
        return None
    now = now or _now_iso()
    location = raw.get("candidate_required_location") or None
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    category = raw.get("category") or ""
    return {
        **base,
        "company": raw.get("company_name") or None,
        "location": location,
        "work_mode": deduce_work_mode(location or "", description, category),
        "description": description,
        "direct_apply_url": extract_direct_apply_url(description),
        "posted_date": _iso_from_any(raw.get("publication_date")),
        "fetched_at": now,
    }


def normalize_adzuna_item(raw, now=None):
    """Normalize one Adzuna `results` entry; None when unusable."""
    if not isinstance(raw, dict):
        return None
    company = raw.get("company")
    company_name = company.get("display_name") if isinstance(company, dict) else None
    location = raw.get("location")
    location_name = location.get("display_name") if isinstance(location, dict) else None
    url = raw.get("redirect_url") or raw.get("url")
    base = _base_job("adzuna", raw.get("id"), raw.get("title"), url)
    if base is None:
        return None
    now = now or _now_iso()
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    return {
        **base,
        "company": company_name,
        "location": location_name,
        "work_mode": deduce_work_mode(location_name or "", description),
        "description": description,
        "direct_apply_url": extract_direct_apply_url(description),
        "posted_date": _iso_from_any(raw.get("created")),
        "fetched_at": now,
    }


def fetch_arbeitnow(query="", limit=DEFAULT_LIMIT, timeout=None):
    """Fetch Arbeitnow feed; query filtered client-side (no server search)."""
    payload = _get_json(config.SOURCES["arbeitnow"], timeout=timeout, label="arbeitnow")
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise SourceError("arbeitnow: unexpected response shape (missing 'data' list)")
    now = _now_iso()
    jobs = []
    for raw in items:
        if not _matches_query(
            [
                raw.get("title") if isinstance(raw, dict) else "",
                raw.get("company_name") if isinstance(raw, dict) else "",
                raw.get("location") if isinstance(raw, dict) else "",
                " ".join(map(str, raw.get("tags", [])))
                if isinstance(raw, dict) and isinstance(raw.get("tags"), list)
                else "",
            ],
            query,
        ):
            continue
        job = normalize_arbeitnow_item(raw, now=now)
        if job is not None:
            jobs.append(job)
        if limit is not None and len(jobs) >= limit:
            break
    return jobs


def fetch_remoteok(query="", limit=DEFAULT_LIMIT, timeout=None):
    """Fetch RemoteOK feed (~100 recent, 24h delayed); query filtered locally."""
    payload = _get_json(config.SOURCES["remoteok"], timeout=timeout, label="remoteok")
    if not isinstance(payload, list):
        raise SourceError("remoteok: unexpected response shape (expected JSON list)")
    now = _now_iso()
    jobs = []
    for raw in payload:
        job = normalize_remoteok_item(raw, now=now)
        if job is None:
            continue  # skips the index-0 legal notice and bad rows
        tags = raw.get("tags") if isinstance(raw, dict) and isinstance(raw.get("tags"), list) else []
        if not _matches_query(
            [job["title"], job["company"], job["location"], " ".join(map(str, tags))],
            query,
        ):
            continue
        jobs.append(job)
        if limit is not None and len(jobs) >= limit:
            break
    return jobs


def fetch_remotive(query="", limit=DEFAULT_LIMIT, timeout=None):
    """Fetch Remotive feed using server-side `search`/`limit` params."""
    params = {}
    if (query or "").strip():
        params["search"] = query.strip()
    if limit is not None:
        params["limit"] = limit
    payload = _get_json(
        config.SOURCES["remotive"], params=params, timeout=timeout, label="remotive"
    )
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise SourceError("remotive: unexpected response shape (missing 'jobs' list)")
    now = _now_iso()
    jobs = []
    for raw in items:
        job = normalize_remotive_item(raw, now=now)
        if job is not None:
            jobs.append(job)
        if limit is not None and len(jobs) >= limit:
            break
    return jobs


def _adzuna_credentials(app_id, app_key):
    resolved_id = (app_id or os.getenv("ADZUNA_APP_ID") or "").strip()
    resolved_key = (app_key or os.getenv("ADZUNA_APP_KEY") or "").strip()
    if not resolved_id or not resolved_key:
        return None, None
    return resolved_id, resolved_key


def fetch_adzuna(
    query="",
    location="India",
    limit=DEFAULT_LIMIT,
    timeout=None,
    app_id=None,
    app_key=None,
    country="in",
):
    """Fetch Adzuna India listings; [] when credentials are absent.

    Credentials resolve from explicit args first, then ADZUNA_APP_ID /
    ADZUNA_APP_KEY env vars. They are sent as query params per Adzuna's
    API contract and never appear in logs or error messages.
    """
    resolved_id, resolved_key = _adzuna_credentials(app_id, app_key)
    if not resolved_id or not resolved_key:
        return []
    params = {
        "app_id": resolved_id,
        "app_key": resolved_key,
        "results_per_page": DEFAULT_LIMIT if limit is None else limit,
    }
    if (query or "").strip():
        params["what"] = query.strip()
    if (location or "").strip():
        params["where"] = location.strip()
    base = config.SOURCES["adzuna"].rstrip("/")
    if base.endswith("/search/1"):
        url = base
    elif base.endswith("/search"):
        url = base + "/1"
    else:
        url = f"{base}/{country}/search/1"
    try:
        payload = _get_json(url, params=params, timeout=timeout, label="adzuna")
    except SourceError as exc:
        raise SourceError(_sanitize(exc, (resolved_id, resolved_key))) from exc
    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise SourceError("adzuna: unexpected response shape (missing 'results' list)")
    now = _now_iso()
    jobs = []
    for raw in items:
        try:
            job = normalize_adzuna_item(raw, now=now)
        except Exception as exc:
            raise SourceError(
                _sanitize(f"adzuna: bad job entry: {exc}", (resolved_id, resolved_key))
            ) from exc
        if job is not None:
            jobs.append(job)
        if limit is not None and len(jobs) >= limit:
            break
    return jobs


def deduplicate(jobs):
    """Drop duplicates by apply_url (fallback: source:id), keeping first."""
    seen = set()
    unique = []
    for job in jobs:
        url = (job.get("apply_url") or "").strip().lower()
        key = url if url else f"{job.get('source')}:{job.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def fetch_all_jobs(
    query="",
    limit_per_source=DEFAULT_LIMIT,
    timeout=None,
    adzuna_app_id=None,
    adzuna_app_key=None,
    adzuna_country="in",
    adzuna_location="India",
):
    """Aggregate all sources; per-source failures are recorded, not raised.

    Adds ``source_counts`` (jobs returned per successful source) and
    ``adzuna_configured`` so callers can tell zero results apart from
    failure and from a missing Adzuna key. Counts are pre-deduplication;
    ``jobs`` remains deduplicated.
    """
    fetched_at = _now_iso()
    jobs, errors = [], []
    attempted = ["arbeitnow", "remoteok", "remotive", "adzuna"]
    counts = {}
    adzuna_id, adzuna_key = _adzuna_credentials(adzuna_app_id, adzuna_app_key)

    try:
        found = fetch_arbeitnow(query, limit_per_source, timeout)
        jobs.extend(found)
        counts["arbeitnow"] = len(found)
    except Exception as exc:
        errors.append({"source": "arbeitnow", "error": str(exc)})

    try:
        found = fetch_remoteok(query, limit_per_source, timeout)
        jobs.extend(found)
        counts["remoteok"] = len(found)
    except Exception as exc:
        errors.append({"source": "remoteok", "error": str(exc)})

    try:
        found = fetch_remotive(query, limit_per_source, timeout)
        jobs.extend(found)
        counts["remotive"] = len(found)
    except Exception as exc:
        errors.append({"source": "remotive", "error": str(exc)})

    try:
        found = fetch_adzuna(
            query,
            location=adzuna_location,
            limit=limit_per_source,
            timeout=timeout,
            app_id=adzuna_app_id,
            app_key=adzuna_app_key,
            country=adzuna_country,
        )
        jobs.extend(found)
        counts["adzuna"] = len(found)
    except Exception as exc:
        errors.append({"source": "adzuna", "error": str(exc)})

    return {
        "jobs": deduplicate(jobs),
        "errors": errors,
        "sources_attempted": attempted,
        "source_counts": counts,
        "adzuna_configured": bool(adzuna_id and adzuna_key),
        "fetched_at": fetched_at,
    }
