"""/shine/companies/jobs — a company's openings. Shine has no employer
profile pages: its /job-search/<company>-jobs and <company>-openings pages
are keyword searches on the company name (the site itself renders them from
the same search API), so this is that search with the company echoed back —
consultancies hiring for the company appear next to the employer's own ads
(each card's company.hiring_for names who the ad is for)."""
from shine import fetch, refdata, refs
from shine import parsers as P
from shine import shared as S
from shine.jobs import search_params


def jobs(company, location=None, page=1, page_size=refdata.DEFAULT_PAGE_SIZE, sort=None, experience=None, salary=None,
         employment_type=None, include_description=False):
    """A company's open jobs (Shine's company pages are keyword searches on the
    name): job cards, facets and matching_company_count, the cards whose
    employer or client carries the name."""
    name, slug = company["name"], company["slug"]
    params = search_params(name, location, page, page_size, sort, experience, salary, employment_type=employment_type)
    raw = fetch.search(params, label=f"company jobs {name!r} p{page}")
    result = P.search_result(raw, page, page_size, include_description=include_description)
    result.pop("query", None)
    result.pop("location", None)
    matched = [j for j in result["jobs"] if _mentions(j, name)]
    return {
        "company": {
            "name": name,
            "slug": slug,
            "link": S.search_link(f"{slug}-jobs"),
            "openings_link": S.search_link(f"{slug}-openings"),
        },
        "location": location,
        "matching_company_count": len(matched),
        **result,
    }


def _mentions(job, name):
    """Does the card's employer (or the client it hires for) carry the company name?"""
    needle = refs.slugify(name) or ""
    haystack = " ".join(filter(None, [(job.get("company") or {}).get("name"), (job.get("company") or {}).get("hiring_for"),
                                      job.get("title")]))
    return bool(needle) and needle in (refs.slugify(haystack) or "")
