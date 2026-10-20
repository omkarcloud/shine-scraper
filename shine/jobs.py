"""/shine/jobs/* — job search, job details, batch lookup and the similar-jobs
rail, from the open search JSON (fetch.search / fetch.similar) and the BFF
job-description (fetch.job_description, with the job-page HTML fallback)."""
from datetime import datetime, timedelta, timezone

from shine import fetch, refdata
from shine import parsers as P

MAX_BATCH = 10


def search_params(query=None, location=None, page=1, page_size=refdata.DEFAULT_PAGE_SIZE, sort=None, experience=None,
                  salary=None, min_experience=None, min_salary=None, employment_type=None, shift_type=None,
                  job_type=None, department=None, industry=None):
    """Public params -> the search API's own query (its names and ids). The
    list params arrive as the site's ids (the schema maps the public values)."""
    params = {
        "q": query,
        "loc": location,
        "page": page,
        "perpage": page_size,
        "sort": sort,
        "fexp": experience,
        "fsalary": salary,
        "minexp": min_experience,
        "minsal": min_salary,
        "emp_type": employment_type,
        "shift_type": shift_type,
        "job_type": job_type,
        "farea": department,
        "findustry": industry,
    }
    if location and all(part.strip().isdigit() for part in str(location).split(",")):
        # Shine city ids (from /shine/locations) go through `location`, names through `loc`
        params["location"] = [part.strip() for part in str(location).split(",")]
        params["loc"] = None
    return {k: v for k, v in params.items() if v not in (None, "", [])}


def _posted_after(days):
    if not days:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%SZ")


def search(query=None, location=None, page=1, page_size=refdata.DEFAULT_PAGE_SIZE, sort=None, experience=None,
           salary=None, min_experience=None, min_salary=None, employment_type=None, shift_type=None, job_type=None,
           department=None, industry=None, posted_within_days=None, include_description=False):
    """One page of job cards with the site's facets, related searches and SEO
    extras. `posted_within_days` forces the newest-first sort and drops the
    page's older cards (Shine has no date filter of its own; `count` stays
    the site's total, `filtered_out_count` says how many this page lost —
    page until it comes back with no jobs)."""
    if posted_within_days:
        sort = refdata.SORT_MODES["newest"]
    params = search_params(query, location, page, page_size, sort, experience, salary, min_experience, min_salary,
                           employment_type, shift_type, job_type, department, industry)
    raw = fetch.search(params, label=f"job search {query!r} p{page}")
    result = P.search_result(raw, page, page_size, include_description=include_description,
                             posted_after=_posted_after(posted_within_days))
    result["query"] = query
    result["location"] = location
    return result


def details(job):
    """The full job ad: description, skills, salary bounds, applicant count,
    employer profile. 404 when Shine has no such job."""
    raw = fetch.job_description(job)
    result = P.job_details(raw)
    if result is None:
        raise fetch.ShineNotFound(f"Shine has no job with the id {job}")
    return result


def similar(job, page=1, page_size=refdata.DEFAULT_PAGE_SIZE, include_description=False):
    """The "Similar Jobs" rail for a job: cards plus the attributes the match
    was built from."""
    raw = fetch.similar(job, page=page, per_page=page_size)
    return P.similar_result(raw, job, page, page_size, include_description=include_description)


def batch(jobs):
    """Up to MAX_BATCH jobs by id / link, fetched in parallel. Jobs the site
    no longer has are listed under `errors` instead of failing the call."""
    import config
    results = fetch.run_parallel([lambda j=j: details(j) for j in jobs], config.SHINE_BATCH_WORKERS)
    out, errors = [], {}
    for job_id, (status, value) in zip(jobs, results):
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.ShineNotFound):
            errors[job_id] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}
