"""Shine input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  job       19819868 | https://www.shine.com/jobs/python-developer/meeden-labs/19819868?jobtype=rs
            | shine.com/jobs/x/y/19819868 | /jobs/python-developer/acme/19819868   -> "19819868"
  company   tech-mahindra-ltd | tech-mahindra-ltd-jobs | https://www.shine.com/job-search/tech-mahindra-ltd-openings
            | Tech Mahindra Ltd (a name)                 -> {"slug": "tech-mahindra-ltd", "name": "tech mahindra ltd"}
  search    (any Shine search page link) https://www.shine.com/job-search/python-jobs-in-bangalore?fexp=4
            -> {"slug": "python-jobs-in-bangalore", "query": "python", "location": "bangalore", "params": {...}}
  location  free text ("Bangalore", "bangalore, pune") or a Shine city id ("243") -> as typed
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

_SHINE_HOST_RE = re.compile(r"(?:^|\.)shine\.com$")
_SLUG_BAD = re.compile(r"[/?#\\<>\"]")
_COMPANY_SUFFIX = re.compile(r"-(jobs|openings|vacancies|careers)$")


def parse_url(value):
    """-> (path, query dict) when value looks like a Shine link or host path,
    None when it is plain text. Raises ValueError for another site."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if not _SHINE_HOST_RE.search(head):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not _SHINE_HOST_RE.search(host):
        raise ValueError("Must be a shine.com link.")
    return unquote(parsed.path), {k: v for k, v in parse_qs(parsed.query).items()}


# ---- jobs ---------------------------------------------------------------------------------

JOB_HINT = ("Must be a Shine job id (digits, e.g. 19819868) or a job link "
            "(https://www.shine.com/jobs/python-developer/acme-ltd/19819868).")


def resolve_job(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return raw
    try:
        url = parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    if not url and raw.startswith("/jobs/"):
        url = (raw, {})
    if not url:
        raise ValueError(JOB_HINT)
    path, query = url
    match = re.search(r"/jobs/(?:[^/]+/){1,2}(\d+)(?:/|$)", path)
    if match:
        return match.group(1)
    for name in ("jobid", "jobId", "id"):
        for candidate in query.get(name, []):
            if candidate.strip().isdigit():
                return candidate.strip()
    raise ValueError(JOB_HINT)


# ---- companies ----------------------------------------------------------------------------

COMPANY_HINT = ("Must be a company name (Tech Mahindra Ltd), its Shine slug (tech-mahindra-ltd) or a "
                "shine.com /job-search/<company>-jobs link.")


def slugify(value):
    """'Tech Mahindra Ltd.' -> 'tech-mahindra-ltd' (the site's own slug shape)."""
    out = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return out or None


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    try:
        url = parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        match = re.search(r"/job-search/([^/?#]+)", url[0])
        if not match:
            raise ValueError("Links must be company search pages (/job-search/<company>-jobs).")
        raw = match.group(1)
    if _SLUG_BAD.search(raw) or len(raw) > 150:
        raise ValueError(COMPANY_HINT)
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", raw):
        slug = _COMPANY_SUFFIX.sub("", raw)
        if not slug:
            raise ValueError(COMPANY_HINT)
        return {"slug": slug, "name": slug.replace("-", " ")}
    name = " ".join(raw.split())
    slug = slugify(name)
    if not slug:
        raise ValueError(COMPANY_HINT)
    return {"slug": slug, "name": name.lower()}


# ---- search pages --------------------------------------------------------------------------

_SEARCH_SLUG = re.compile(r"^(?:(?P<query>.+?)-)?jobs(?:-in-(?P<location>.+?))?(?:-(?P<page>\d+))?$")


def parse_search_slug(slug):
    """'python-developer-jobs-in-bangalore-2' -> ('python developer', 'bangalore', 2);
    'jobs-in-pune' -> (None, 'pune', None); 'tech-mahindra-ltd-openings' -> ('tech mahindra ltd openings', None, None)."""
    slug = (slug or "").strip("/").lower()
    match = _SEARCH_SLUG.match(slug)
    if not match:
        return (slug.replace("-", " ") or None), None, None
    query = (match.group("query") or "").replace("-", " ") or None
    location = (match.group("location") or "").replace("-", " ") or None
    page = int(match.group("page")) if match.group("page") else None
    return query, location, page


def resolve_search_link(value):
    """A /job-search/<slug> link (with the site's own filter params) -> the
    search inputs it encodes. Plain text is returned as a query."""
    raw = (value or "").strip()
    url = parse_url(raw)
    if not url:
        return {"query": " ".join(raw.split()) or None, "location": None, "page": None, "params": {}}
    path, query = url
    match = re.search(r"/job-search/(?:simple/?$|([^/?#]+))", path)
    if not match:
        raise ValueError("Must be a shine.com /job-search/ link.")
    slug = match.group(1)
    term, location, page = parse_search_slug(slug) if slug else (None, None, None)
    first = {k: v[0] for k, v in query.items() if v}
    term = first.get("q") or term
    location = first.get("loc") or location
    try:
        page = int(first["page"]) if first.get("page") else page
    except ValueError:
        pass
    params = {k: query[k] for k in ("fexp", "fsalary", "farea", "findustry", "emp_type", "shift_type",
                                     "job_type", "minexp", "minsal", "sort", "location") if k in query}
    return {"query": term, "location": location, "page": page, "params": params}


# ---- locations -----------------------------------------------------------------------------

def resolve_location(value):
    """Free text as typed in the site's location box (comma-separated cities
    allowed), or Shine city ids; -> as given, whitespace-collapsed."""
    raw = " ".join((value or "").split())
    if not raw:
        return None
    if len(raw) > 200:
        raise ValueError("Location must be at most 200 characters.")
    return raw
