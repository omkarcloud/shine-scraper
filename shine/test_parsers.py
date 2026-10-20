"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (shine/fixtures/*.json.gz, raw payloads captured 2026-10-19 from
www.shine.com) — no network.

    python -m pytest shine/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shine import companies, fetch, jobs, lookups, parsers as P, refdata, refs, schemas, shared as S  # noqa: E402
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
JOB = "19574086"


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def fx_text(name):
    with gzip.open(os.path.join(FX, name), "rt", encoding="utf-8") as f:
        return f.read()


# ---- refs ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "19819868", "https://www.shine.com/jobs/python-developer/meeden-labs-private-limited/19819868?jobtype=rs",
    "shine.com/jobs/x/y/19819868", "/jobs/python-developer/acme/19819868", "https://www.shine.com/jobs/job/19819868/19819868",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == "19819868"


@pytest.mark.parametrize("value", ["", "abc", "https://www.shine.com/job-search/python-jobs", "https://example.com/jobs/a/b/1"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


@pytest.mark.parametrize("value,expected", [
    ("Tech Mahindra Ltd.", {"slug": "tech-mahindra-ltd", "name": "tech mahindra ltd."}),
    ("tech-mahindra-ltd", {"slug": "tech-mahindra-ltd", "name": "tech mahindra ltd"}),
    ("tech-mahindra-ltd-openings", {"slug": "tech-mahindra-ltd", "name": "tech mahindra ltd"}),
    ("https://www.shine.com/job-search/capgemini-jobs?page=2", {"slug": "capgemini", "name": "capgemini"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://example.com/job-search/x-jobs", "https://www.shine.com/jobs/a/b/1", "a/b"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


def test_resolve_search_link():
    out = refs.resolve_search_link("https://www.shine.com/job-search/python-developer-jobs-in-bangalore-2?fexp=4&fexp=3&sort=1&minexp=5")
    assert out["query"] == "python developer" and out["location"] == "bangalore" and out["page"] == 2
    assert out["params"]["fexp"] == ["4", "3"] and out["params"]["sort"] == ["1"] and out["params"]["minexp"] == ["5"]
    assert refs.resolve_search_link("https://www.shine.com/job-search/jobs-in-pune")["location"] == "pune"
    assert refs.resolve_search_link("https://www.shine.com/job-search/simple?q=python&loc=delhi") == {
        "query": "python", "location": "delhi", "page": None, "params": {}}
    assert refs.resolve_search_link("  data   analyst ") == {"query": "data analyst", "location": None, "page": None, "params": {}}
    with pytest.raises(ValueError):
        refs.resolve_search_link("https://www.shine.com/jobs/a/b/1")


# ---- schemas -------------------------------------------------------------------------------------

def test_search_schema_maps_filters():
    data, error = load_query(schemas.JobSearchSchema, {
        "query": "python", "location": "Bangalore", "experience": "3-5,6-8", "salary": "9-12",
        "employment_type": "regular,work_from_home", "shift_type": "part_time", "job_type": "walk_in",
        "department": "1301,1001", "industry": "18", "sort": "newest", "posted_within_days": "7", "page_size": "50"})
    assert error is None
    assert data["experience"] == ["3", "4"] and data["salary"] == ["3"] and data["employment_type"] == ["1", "4"]
    assert data["shift_type"] == ["2"] and data["job_type"] == ["2"] and data["department"] == ["1301", "1001"]
    assert data["industry"] == ["18"] and data["sort"] == "1" and data["posted_within_days"] == 7 and data["page_size"] == 50


def test_search_schema_unpacks_link():
    data, error = load_query(schemas.JobSearchSchema, {
        "query": "https://www.shine.com/job-search/python-developer-jobs-in-bangalore-2?fexp=4&sort=1&emp_type=4&farea=1301"})
    assert error is None
    assert data["query"] == "python developer" and data["location"] == "bangalore" and data["page"] == 2
    assert data["experience"] == ["4"] and data["sort"] == "1" and data["employment_type"] == ["4"] and data["department"] == ["1301"]
    data, error = load_query(schemas.JobSearchSchema, {"query": "https://www.shine.com/job-search/jobs-in-pune", "location": "Delhi", "page": "3"})
    assert error is None and data["query"] is None and data["location"] == "Delhi" and data["page"] == 3
    data, error = load_query(schemas.JobSearchSchema, {"query": "https://www.shine.com/job-search/python-jobs?location=243&location=246"})
    assert error is None and data["query"] == "python" and data["location"] == "243,246"


@pytest.mark.parametrize("query", [
    {}, {"query": "x", "experience": "99"}, {"query": "x", "bogus": "1"}, {"query": "x", "page_size": "51"},
    {"query": "x", "department": "abc"}, {"query": "x", "sort": "oldest"}, {"query": "x", "page": "0"},
])
def test_search_schema_rejects(query):
    data, error = load_query(schemas.JobSearchSchema, query)
    assert data is None and error["error"].startswith("Invalid parameters")


def test_other_schemas():
    assert load_query(schemas.JobSchema, {"job": "https://www.shine.com/jobs/a/b/19819868"})[0] == {"job": "19819868"}
    assert load_query(schemas.JobBatchSchema, {"jobs": "1, https://www.shine.com/jobs/a/b/2,1"})[0] == {"jobs": ["1", "2"]}
    assert load_query(schemas.JobBatchSchema, {"jobs": ",".join(str(i) for i in range(11))})[0] is None
    data, _ = load_query(schemas.CompanyJobsSchema, {"company": "Capgemini", "experience": "0-1"})
    assert data["company"] == {"slug": "capgemini", "name": "capgemini"} and data["experience"] == ["1"]
    assert load_query(schemas.SuggestSchema, {"query": "py", "type": "Locations"})[0]["type"] == "locations"
    assert load_query(schemas.SuggestSchema, {"query": "py", "type": "cities"})[0] is None
    assert load_query(schemas.LocationsSchema, {"flat": "no"})[0] == {"query": None, "flat": False}
    assert load_query(schemas.EmptySchema, {"x": "1"})[0] is None


# ---- shared helpers --------------------------------------------------------------------------------

@pytest.mark.parametrize("label,low,high,period", [
    ("Rs 3.0  - 10 Lakh/Yr", 300000, 1000000, "yearly"),
    ("< Rs 50,000 - 3.0 Lakh/Yr", 50000, 300000, "yearly"),
    ("10 - 30 Lakh/Yr", 1000000, 3000000, "yearly"),
    ("< Rs 50,000 /Yr", None, 50000, "yearly"),
    ("> 25 Lakh/Yr", 2500000, None, "yearly"),
    ("Rs 15,000 - 25,000 /Month", 15000, 25000, "monthly"),
])
def test_salary_from_label(label, low, high, period):
    out = S.salary_from_label(label)
    assert (out["min"], out["max"], out["period"], out["currency"]) == (low, high, period, "INR")


def test_salary_from_bounds_and_hidden():
    assert S.salary_from_bounds("300000", "1000000", "Rs 3.0 - 10 Lakh/Yr")["max"] == 1000000
    assert S.salary_from_bounds(None, None, None) is None
    assert S.salary_from_bounds("0", "0", "Rs 2 - 4 Lakh/Yr")["min"] == 200000
    assert S.salary_from_label("") is None


@pytest.mark.parametrize("label,low,high", [
    ("0 to 4 Yrs", 0, 4), ("< 1 Year", 0, 1), ("> 15 Years", 15, None), ("3 to 7 Yrs", 3, 7), ("5 Yrs", 5, 5), ("", None, None),
])
def test_experience_from_label(label, low, high):
    out = S.experience_from_label(label)
    if not label:
        assert out is None
    else:
        assert (out["min_years"], out["max_years"]) == (low, high)


def test_dates_and_text():
    assert S.iso_datetime("2026-10-13T05:35:15") == "2026-10-13T00:05:15Z"
    assert S.iso_datetime("2026-10-15T13:41:43+05:30") == "2026-10-15T08:11:43Z"
    assert S.iso_datetime("2026-10-15T13:41:43Z") == "2026-10-15T13:41:43Z"
    assert S.iso_datetime("2026-10-15") == "2026-10-15" and S.iso_datetime(None) is None and S.iso_datetime("soon") is None
    assert S.html_to_text("<p>A</p><ul><li>b</li><li>c</li></ul>") == "A\n- b\n- c"
    assert S.csv_list("python,  azure,  aws,python,") == ["python", "azure", "aws"]
    assert S.snippet("word " * 100, 20).endswith("…") and S.snippet("short") == "short"
    assert S.job_link("a/b/1") == "https://www.shine.com/jobs/a/b/1" and S.job_link(None, "1") == "https://www.shine.com/jobs/job/1/1"
    assert S.flag("1") is True and S.flag(0) is False and S.flag("x") is None and S.flag(None) is None


# ---- parsers -------------------------------------------------------------------------------------------

def test_search_result():
    out = P.search_result(fx("search_python_bangalore"), 1, 20)
    assert out["query"] == "python" and out["location"] == "bangalore"
    assert out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 155, "total_count": 3089}
    assert len(out["jobs"]) == 20 and out["facets"]["locations"][0] == {"id": "243", "name": "Bangalore", "count": 3085}
    assert out["facets"]["experience"][0]["value"] in refdata.EXPERIENCE_BANDS and out["facets"]["employment_types"][0]["value"] == "regular"
    assert out["related_searches"][0]["link"] == "https://www.shine.com/job-search/django-jobs-in-bangalore"
    assert out["related_links"]["by_location"] and "Mysore" in out["related_links"]["groups"]
    assert out["breadcrumbs"][-1]["slug"] == "python-jobs-in-bangalore" and out["seo"]["canonical_link"].endswith("/python-jobs-in-bangalore")
    assert out["spelling_suggestion"] is None and out["faq"] == []
    job = out["jobs"][0]
    assert job["id"] == JOB and job["title"] == "Python Developer"
    assert job["link"] == "https://www.shine.com/jobs/python-developer/diraa-hr-services/19574086"
    assert job["company"]["id"] == 740691 and job["company"]["hiring_for"] == "Client companies" and job["company"]["logo"].startswith("https://")
    assert job["locations"] == ["Bangalore", "Coimbatore"] and job["experience"] == {"label": "0 to 4 Yrs", "min_years": 0, "max_years": 4}
    assert job["salary"] is None and job["skills"] == ["sql", "mysql", "django", "python"] and job["vacancies"] == 21
    assert job["employment_type"] == "regular" and job["shift_type"] == "full_time" and job["job_type"] == "regular" and job["is_walk_in"] is False
    assert job["posted_at"] == "2026-10-13T00:05:15Z" and job["expires_at"] == "2026-12-12T00:13:42Z"
    assert job["is_early_applicant"] is True and job["is_instant_apply"] is True and job["qualification"] == "graduate"
    assert job["description_snippet"].startswith("A Python Developer") and "description_text" not in job
    with_desc = P.search_result(fx("search_python_bangalore"), 1, 20, include_description=True)["jobs"][0]
    assert with_desc["description_html"].startswith("<p>") and with_desc["description_text"].startswith("A Python Developer")
    for salaried in (j for j in out["jobs"] if j["salary"]):
        assert salaried["salary"]["currency"] == "INR" and salaried["salary"]["max"] >= salaried["salary"]["min"]


def test_search_result_filtered_and_posted_after():
    out = P.search_result(fx("search_filtered"), 2, 5)
    assert out["pagination"]["page"] == 2 and out["pagination"]["items_per_page"] == 5 and len(out["jobs"]) == 5
    assert out["location"] == "bangalore,pune"
    future = P.search_result(fx("search_filtered"), 2, 5, posted_after="2099-01-01T00:00:00Z")
    assert future["jobs"] == [] and future["filtered_out_count"] == 5 and future["pagination"]["total_count"] == out["pagination"]["total_count"]
    assert P.search_result({}, 1, 20)["jobs"] == [] and P.search_result(None, 1, 20)["pagination"]["total_count"] == 0
    only_loc = P.search_result(fx("search_location_only"), 1, 5)
    assert only_loc["query"] is None and only_loc["location"] == "pune" and only_loc["jobs"]


def test_job_details():
    out = P.job_details(fx("job_description"))
    assert out["id"] == JOB and out["title"] == "Python Developer" and out["link"].endswith(f"/{JOB}")
    assert out["company"]["id"] == 740691 and out["company"]["is_top_company"] is False
    assert out["location_details"][0]["state"] and out["skills"] == ["sql", "mysql", "django", "python"]
    assert out["applicant_count"] == 1494 and out["description_text"] and out["description_html"]
    # this consultancy ad shows its recruiter's address; profiled companies mask theirs
    assert "@" in out["recruiter"]["email"] and out["recruiter"]["is_contact_hidden"] is False
    assert out["related_searches"]["title"] == "Python Developer" and out["related_searches"]["groups"]
    top = P.job_details(fx("job_description_top_company"))
    assert top["company"]["size"] == "10,001+ employees" and top["company"]["founded_year"] == 1967
    assert top["company"]["social_links"]["linkedin"].startswith("https://www.linkedin.com/") and top["company"]["is_top_company"] is True
    # hidden salaries carry Shine's 2-5 lakh placeholder bounds, which must not leak out
    assert top["salary"] == {"label": None, "min": None, "max": None, "currency": "INR", "period": "yearly", "is_hidden": True}
    assert out["salary"]["is_hidden"] is False
    assert top["functional_areas"] == [{"id": "1301", "name": "General / Other Software"}]
    assert "shinedefault" not in top["tags"] and top["skill_tags"]["level_four"] == ["gcp", "python", "azure", "aws"]
    assert top["is_global"] is True and top["is_boosted"] is False and top["reporting_location"] == "Delhi"
    assert top["company"]["id"] is None        # global ads share one poster account (769865), not a company id
    assert top["recruiter"]["email"] is None and top["recruiter"]["phone"] is None and top["recruiter"]["is_contact_hidden"] is True
    assert P.job_details({"results": []}) is None and P.job_details(None) is None


def test_job_page_fallback_payload():
    data = fetch.rsc_query_data(fetch.rsc_payload(fx_text("job_page.html.gz")), "job-description")
    assert data["results"][0]["id"] == JOB
    assert P.job_details(data)["title"] == "Python Developer"
    assert fetch.rsc_query_data("", "job-description") is None


def test_similar_result():
    out = P.similar_result(fx("similar"), JOB, 1, 5)
    assert out["job"]["id"] == JOB and out["job"]["locations"] == ["Coimbatore", "Bangalore"]
    assert out["job"]["salary"]["min"] == 50000 and out["job"]["salary"]["max"] == 300000
    assert len(out["jobs"]) == 5 and out["pagination"]["total_count"] == 12854 and out["pagination"]["total_pages"] == 2571
    for job in out["jobs"]:
        assert job["company"]["id"] is None if job["is_global"] else job["company"]["id"]


def test_lookups_parsers():
    sugg = P.suggestions(fx("suggestions"))
    assert sugg[0] == {"text": "python django", "type": "phrase", "skills": ["python", "django"], "job_titles": [],
                       "industries": [], "link": "https://www.shine.com/job-search/python-django-jobs"}
    assert sugg[4]["type"] == "skill" and P.suggestions(fx("suggestions"), limit=2) == sugg[:2]
    locs = P.locations(fx("cities"), "bang", limit=3)
    assert locs[0] == {"id": 243, "name": "Bangalore", "state": "Karnataka", "kind": "city", "is_top_city": True,
                       "link": "https://www.shine.com/job-search/jobs-in-bangalore"}
    assert P.locations(fx("cities"), "wfh")[0]["kind"] == "work_from_home" and P.locations(fx("cities"), "hybrid")[0]["id"] == 9998
    assert len({l["id"] for l in P.locations(fx("cities"))}) == len(P.locations(fx("cities")))
    tree = P.location_tree(fx("cities"))
    assert tree[0]["state"] == "All India" and tree[2]["cities"][0]["name"] == "Port Blair"
    trend = P.trending(fx("trending"), fx("top_searches"))
    assert trend["trending_searches"][0] == {"title": "Java", "link": "https://www.shine.com/job-search/java-jobs?q=java"}
    assert trend["top_searches"][0]["link"].startswith("https://www.shine.com/job-search/") and trend["top_searches"][0]["is_new"] is False
    filt = P.filters(fx("search_empty"))
    assert [b["value"] for b in filt["experience"]] == list(refdata.EXPERIENCE_BANDS) and filt["salary"][1]["min_lakh"] == 3
    assert filt["departments"][0]["id"] and filt["locations"][0]["count"] and filt["total_jobs"] == 138589


# ---- endpoint functions with the transport monkeypatched --------------------------------------------------

def test_endpoints_offline(monkeypatch):
    calls = []

    def fake_search(params, label=None):
        calls.append(("search", dict(params)))
        return fx("search_filtered" if params.get("fexp") else "search_python_bangalore")

    def fake_bff(path, params=None, label=None):
        calls.append(("bff", path, dict(params or {})))
        return {refdata.BFF_KEYWORD_SUGGESTIONS: fx("suggestions"), refdata.BFF_CITIES: fx("cities"),
                refdata.BFF_TRENDING_SEARCHES: fx("trending"), refdata.BFF_TOP_SEARCHES: fx("top_searches")}[path]

    monkeypatch.setattr(fetch, "search", fake_search)
    monkeypatch.setattr(fetch, "bff", fake_bff)
    monkeypatch.setattr(fetch, "similar", lambda job_id, page=1, per_page=20, label=None: fx("similar"))
    monkeypatch.setattr(fetch, "job_description", lambda job_id: fx("job_description") if job_id == JOB else (_ for _ in ()).throw(fetch.ShineNotFound("no")))
    monkeypatch.setattr(fetch, "memoized", lambda key, fn, ttl=0: fn())

    out = jobs.search(query="python", location="bangalore,pune", experience=["3", "4"], salary=["3"], employment_type=["1"],
                      sort="1", page=2, page_size=5)
    assert calls[-1] == ("search", {"q": "python", "loc": "bangalore,pune", "page": 2, "perpage": 5, "sort": "1",
                                    "fexp": ["3", "4"], "fsalary": ["3"], "emp_type": ["1"]})
    assert out["query"] == "python" and len(out["jobs"]) == 5
    jobs.search(location="243,246", page_size=3)
    assert calls[-1][1] == {"location": ["243", "246"], "page": 1, "perpage": 3}
    jobs.search(query="python", posted_within_days=3)
    assert calls[-1][1]["sort"] == "1" and "filtered_out_count" in jobs.search(query="python", posted_within_days=3)

    assert jobs.details(JOB)["id"] == JOB
    with pytest.raises(fetch.ShineNotFound):
        jobs.details("1")
    batch = jobs.batch([JOB, "1"])
    assert batch["count"] == 1 and batch["errors"] == {"1": "not found"}
    assert jobs.similar(JOB, page_size=5)["job"]["id"] == JOB

    comp = companies.jobs({"slug": "diraa-hr-services", "name": "diraa hr services"}, page_size=20)
    assert comp["company"]["link"] == "https://www.shine.com/job-search/diraa-hr-services-jobs" and comp["matching_company_count"] >= 1
    assert "query" not in comp and calls[-1][1]["q"] == "diraa hr services"

    assert lookups.suggest("pyth")["keywords"][0]["text"] == "python django"
    assert lookups.suggest("bang", type="locations", limit=1)["locations"][0]["name"] == "Bangalore"
    assert lookups.locations("hyder")["locations"][0]["id"] == 246 and lookups.locations(flat=False)["states"]
    assert lookups.trending()["trending_searches"] and lookups.filters()["employment_type"][3]["value"] == "work_from_home"


# ---- transport policy -------------------------------------------------------------------------------------------

def test_attempts_escalate_to_browser_only_when_blocked(monkeypatch):
    import config
    monkeypatch.setattr(config, "SHINE_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(config, "SHINE_BROWSER_FALLBACK", True)
    monkeypatch.setattr(config, "shine_proxy", lambda fallback=False: None)
    monkeypatch.setattr(fetch, "_session", lambda key, proxy: object())
    monkeypatch.setattr(fetch, "_drop_session", lambda key: None)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    browser_calls = []

    def browser():
        browser_calls.append(1)
        return {"results": []}

    def blocked(sess):
        raise fetch.ShineBlocked("403")
    assert fetch._attempts("x", blocked, browser) == {"results": []} and browser_calls == [1]

    def flaky(sess):
        raise fetch.ShineUpstreamError("500")
    with pytest.raises(fetch.ShineUpstreamError):
        fetch._attempts("x", flaky, browser)
    assert browser_calls == [1]            # a 5xx never reaches the browser

    def missing(sess):
        raise fetch.ShineNotFound("404")
    with pytest.raises(fetch.ShineNotFound):
        fetch._attempts("x", missing, browser)
    monkeypatch.setattr(config, "SHINE_BROWSER_FALLBACK", False)
    with pytest.raises(fetch.ShineBlocked):
        fetch._attempts("x", blocked, browser)


def test_classify():
    assert fetch._classify(200, '{"a": 1}', "x") == {"a": 1}
    with pytest.raises(fetch.ShineBlocked):
        fetch._classify(403, "", "x")
    with pytest.raises(fetch.ShineKeyRejected):
        fetch._classify(401, '{"message": "Unauthorized"}', "x")
    with pytest.raises(fetch.ShineNotFound):
        fetch._classify(404, "", "x")
    with pytest.raises(fetch.ShineNotFound):
        fetch._classify(200, "<html><title>Error Page</title></html>", "x")
    with pytest.raises(fetch.ShineBlocked):
        fetch._classify(200, "<html><body>Access Denied</body></html>", "x")
    with pytest.raises(fetch.ShineBadRequest):
        fetch._classify(400, "bad", "x")
    assert fetch._classify(200, "<p>hi</p>", "x", json_body=False) == "<p>hi</p>"
