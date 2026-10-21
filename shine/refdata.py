"""Shine.com reference data: hosts, the site's filter vocabularies (the ids
its search API takes and the labels its facets show), the public -> site
param mapping and the embedded BFF key. Pure constants, no network.

Everything here was read off the site 2026-10-19 (the Next.js chunks under
/nova/assets/_next/static/chunks/ name every request param and facet key;
the facet labels come from a bare search's own facet lists)."""

SITE = "https://www.shine.com"
HOST = "www.shine.com"
MOBILE_API_HOST = "mapi.shine.com"       # the upstream the BFF proxies for its `next` links; serves /api/v2/search/* too
BFF_PATH = "/pages/bff"                  # the Next.js app's backend-for-frontend (x-api-key below)
# serverConfig.apiKey in the site's own client bundle (chunk 3553-*.js) — the
# BFF refuses calls without it (401). Public by construction (every visitor's
# browser sends it) but it may rotate with a site deploy; SHINE_BFF_API_KEY in
# the environment overrides it (config.SHINE_BFF_API_KEY).
BFF_API_KEY = "xk_live_Kj8nP2mV4wXc9tYq5sRzH3fA7bNdL6gTvUeWxCpM_2023"

SEARCH_PATH = "/api/v2/search/simple/"          # open JSON, no key: the job search behind /job-search/<slug>
# The search API leaves the salary label (jSal) OUT of every card unless the
# request names its fields in `fl` (the site's own pages always do). These are
# the fields parsers.job_card reads — a lean list also trims the payload by a
# quarter. (A list missing required fields answers 500, e.g. "id,jJT,jCName".)
SEARCH_FIELDS = ",".join((
    "id", "jJT", "jSlug", "jCID", "jCName", "jHF", "jLU", "cCLU", "cCW", "cCDom", "cCS", "cCH", "cFY", "cSML",
    "jTopCmp", "cCTop", "cUD", "jLoc", "jWLC", "jExp", "jSal", "jInd", "jArea", "jKwd", "jQL", "jEType", "jETn",
    "jTypeC", "jJobType", "jVanc", "jACnt", "jPack", "jPDate", "jExpDate", "early_applicant_badge", "iaj", "jPJ",
    "jHJ", "g_job_flag", "jRN", "jRE", "jRP", "jRUrl", "jJD", "jJDT",
))
SIMILAR_PATH = "/api/v2/search/similar/"        # open JSON: similar jobs for a job id
BFF_JOB_DESCRIPTION = "/api/v1/search/job-description"      # ?jobId=
BFF_JOB_SEARCH = "/api/v1/search/jobs"                      # the SSR search (q + url slug)
BFF_KEYWORD_SUGGESTIONS = "/api/v1/search/keyword-suggestions/"   # ?suggestion="<text>"
BFF_CITIES = "/api/v1/search/city/"                         # the state -> city tree (city_name is ignored upstream)
BFF_TRENDING_SEARCHES = "/api/v1/search/trending/"
BFF_TOP_SEARCHES = "/api/v1/shared/top-clicks-job-search-list"

CURRENCY = "INR"
TIMEZONE_OFFSET = "+05:30"               # the site's naive timestamps are IST
LAKH = 100_000

MAX_PAGE = 500
MAX_PAGE_SIZE = 50                       # the search API caps perpage at 50 (100 -> 50 rows)
DEFAULT_PAGE_SIZE = 20

# ---- sort ---------------------------------------------------------------------------------------
# the site's sort param: absent = relevance, 1 = freshness (anything else is a 500 upstream)
SORT_MODES = {"relevance": None, "newest": "1"}

# ---- filter vocabularies: public value -> site id ---------------------------------------------------
# experience bands (fexp)
EXPERIENCE_BANDS = {
    "0-1": "1", "1-2": "2", "3-5": "3", "6-8": "4", "9-10": "5", "11-15": "6", "15+": "7",
}
EXPERIENCE_LABELS = {"1": "< 1 Year", "2": "1 to 2 Years", "3": "3 to 5 Years", "4": "6 to 8 Years",
                     "5": "9 to 10 Years", "6": "11 to 15 Years", "7": "> 15 Years"}
EXPERIENCE_YEARS = {"1": (0, 1), "2": (1, 2), "3": (3, 5), "4": (6, 8), "5": (9, 10), "6": (11, 15), "7": (15, None)}
# annual salary bands in lakh INR (fsalary)
SALARY_BANDS = {
    "0-2": "0", "3-5": "1", "6-8": "2", "9-12": "3", "13-16": "4", "17-25": "5", "25+": "6",
}
SALARY_LABELS = {"0": "Up to 2 Lakh", "1": "3 to 5 Lakh", "2": "6 to 8 Lakh", "3": "9 to 12 Lakh",
                 "4": "13 to 16 Lakh", "5": "17 to 25 Lakh", "6": "> 25 Lakh"}
SALARY_LAKH = {"0": (0, 2), "1": (3, 5), "2": (6, 8), "3": (9, 12), "4": (13, 16), "5": (17, 25), "6": (25, None)}
# employment type (emp_type / jEType)
EMPLOYMENT_TYPES = {"regular": "1", "contractual": "2", "internship": "3", "work_from_home": "4"}
EMPLOYMENT_LABELS = {"1": "Regular", "2": "Contractual", "3": "Internship", "4": "Work from home"}
# shift / job category (shift_type / jTypeC)
SHIFT_TYPES = {"full_time": "1", "part_time": "2"}
SHIFT_LABELS = {"1": "Full time", "2": "Part time"}
# interview / job type (job_type / jJobType)
JOB_TYPES = {"regular": "1", "walk_in": "2"}
JOB_TYPE_LABELS = {"1": "Regular", "2": "Walk-in"}
# work shift (jNSTs facet; not a request filter the site exposes)
WORK_SHIFT_LABELS = {"0": "Any", "1": "Day", "2": "Morning", "3": "Night", "4": "Rotational"}
# qualification level (jQL / qualification_level)
QUALIFICATION_LABELS = {0: None, 1: "graduate", 2: "post_graduate", 3: "doctorate"}

PUBLIC_VALUE = {name: {v: k for k, v in table.items()} for name, table in (
    ("experience", EXPERIENCE_BANDS), ("salary", SALARY_BANDS), ("employment_type", EMPLOYMENT_TYPES),
    ("shift_type", SHIFT_TYPES), ("job_type", JOB_TYPES))}

# ---- facets: the search API's facet keys -> public names -----------------------------------------------
FACET_KEYS = {
    "jFLoc": "locations",
    "jFEx": "experience",
    "jFSal": "salary",
    "jFArea": "departments",
    "jIndID": "industries",
    "jCIDF": "featured_companies",
    "jCIDT": "top_companies",
    "jNSTs": "work_shifts",
    "jJobType": "job_types",
    "jEType": "employment_types",
    "jTypeC": "shift_types",
    "jETn": "employment_tenures",
}
# facets whose ids map back to a public filter value
FACET_PUBLIC = {"experience": PUBLIC_VALUE["experience"], "salary": PUBLIC_VALUE["salary"],
                "employment_types": PUBLIC_VALUE["employment_type"], "shift_types": PUBLIC_VALUE["shift_type"],
                "job_types": PUBLIC_VALUE["job_type"]}

# the WFH / hybrid pseudo-cities of the location tree
VIRTUAL_LOCATIONS = {"9999": "work_from_home", "9998": "hybrid", "242": "all_india"}

# tags the site stamps on every card we drop as noise
NOISE_TAGS = {"shinedefault"}
