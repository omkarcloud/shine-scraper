"""Live endpoint smoke tests: one call per /shine/* route against a running
service, with example values proven to return data (2026-10-19). The
listing tooling (derive_facts.py) reads each route's FIRST call from this
file's AST as its working example, so the values stay literals.

Skipped unless SHINE_BASE points at a running service:

    SCRAPERS_PORT=6097 ONLY_SCRAPER=shine python run.py
    SHINE_BASE=http://127.0.0.1:6097 python -m pytest shine/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("SHINE_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set SHINE_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/shine/jobs/search", query="software engineer", location="Bangalore")
    assert body["count"] > 1000 and len(body["jobs"]) == 20
    assert any(j["salary"] and j["salary"]["max"] for j in body["jobs"])      # cards carry salary (fl)
    body = call("/shine/jobs/search", query="python", location="Bangalore")
    assert body["count"] > 100 and len(body["jobs"]) == 20 and body["next"] and body["total_pages"] > 5
    job = body["jobs"][0]
    assert job["id"].isdigit() and job["title"] and job["link"].startswith("https://www.shine.com/jobs/")
    assert job["company"]["name"] and job["experience"]["label"] and job["posted_at"] and job["description_snippet"]
    assert "Bangalore" in body["facets"]["locations"][0]["name"] and body["facets"]["experience"][0]["value"]
    assert body["related_searches"] and body["seo"]["canonical_link"]
    page2 = call("/shine/jobs/search", query="python", location="Bangalore", page=2)
    assert page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/shine/jobs/search", query="python", experience="3-5,6-8", salary="9-12", employment_type="regular",
                sort="newest", page_size=5, include_description="true")
    assert len(body["jobs"]) == 5 and body["jobs"][0]["description_text"] and body["jobs"][0]["description_html"]
    assert body["jobs"][0]["posted_at"] >= body["jobs"][-1]["posted_at"]
    body = call("/shine/jobs/search", query="sales", job_type="walk_in", page_size=3)
    assert body["jobs"] and all(j["is_walk_in"] for j in body["jobs"])
    body = call("/shine/jobs/search", query="developer", employment_type="work_from_home", page_size=3)
    assert body["jobs"] and all(j["employment_type"] == "work_from_home" for j in body["jobs"])
    body = call("/shine/jobs/search", query="https://www.shine.com/job-search/python-developer-jobs-in-bangalore-2?fexp=4")
    assert body["current_page"] == 2 and body["jobs"] and body["location"] == "bangalore"
    body = call("/shine/jobs/search", query="python", posted_within_days=3, page_size=10)
    assert body["filtered_out_count"] is not None and all(j["posted_at"] for j in body["jobs"])
    body = call("/shine/jobs/search", location="243", page_size=3)
    assert body["count"] > 1000 and body["jobs"]
    assert status("/shine/jobs/search") == 400
    assert status("/shine/jobs/search", query="x", experience="99") == 400
    assert status("/shine/jobs/search", query="x", bogus=1) == 400


def test_job_details():
    # Google, expires 2026-12-01 (pick a fresh id from /shine/companies/jobs?company=Google after that)
    body = call("/shine/jobs/details", job="19680754")
    assert body["id"] == "19680754" and body["description_text"] and body["description_html"] and body["link"]
    assert body["company"]["is_top_company"] is True and body["company"]["size"] and body["salary"]["is_hidden"] is True
    assert body["salary"]["min"] is None
    listing = call("/shine/jobs/search", query="python", location="Bangalore", page_size=1)
    job_id = listing["jobs"][0]["id"]
    body = call("/shine/jobs/details", job=f"https://www.shine.com/jobs/x/y/{job_id}")
    assert body["id"] == job_id and body["description_text"] and body["description_html"] and body["link"]
    assert body["company"]["name"] and body["experience"]["label"] and body["skills"] and body["posted_at"] and body["expires_at"]
    assert body["applicant_count"] is not None and body["recruiter"]["is_contact_hidden"] in (True, False, None)
    assert status("/shine/jobs/details", job="1") == 404
    assert status("/shine/jobs/details", job="abc") == 400


def test_job_batch_and_similar():
    body = call("/shine/jobs/batch", jobs="19680754,19702695,19731708")
    assert body["count"] == 3 and body["errors"] is None
    body = call("/shine/jobs/similar", job="19680754")
    assert body["count"] > 100 and len(body["jobs"]) == 20 and body["job"]["title"]
    listing = call("/shine/jobs/search", query="accountant", page_size=3)
    ids = sorted({j["id"] for j in listing["jobs"]})
    body = call("/shine/jobs/batch", jobs=",".join(ids + ["1"]))
    assert body["count"] == len(ids) and body["errors"] == {"1": "not found"}
    body = call("/shine/jobs/similar", job=ids[0], page_size=5)
    assert body["count"] > 5 and len(body["jobs"]) == 5 and body["job"]["id"] == ids[0] and body["next"]


def test_company_jobs():
    body = call("/shine/companies/jobs", company="Google")
    assert body["count"] > 20 and len(body["jobs"]) == 20 and body["matching_company_count"] >= 5
    body = call("/shine/companies/jobs", company="Capgemini", page_size=5)
    assert body["count"] > 20 and len(body["jobs"]) == 5 and body["matching_company_count"] >= 1
    assert body["company"] == {"name": "capgemini", "slug": "capgemini", "link": "https://www.shine.com/job-search/capgemini-jobs",
                               "openings_link": "https://www.shine.com/job-search/capgemini-openings"}
    body = call("/shine/companies/jobs", company="https://www.shine.com/job-search/capgemini-openings", location="Pune", page_size=3)
    assert body["jobs"] and body["location"] == "Pune"
    assert status("/shine/companies/jobs", company="https://example.com/x") == 400


def test_lookups():
    body = call("/shine/suggest", query="data sci")
    assert body["keywords"][0]["text"] and body["keywords"][0]["link"] and body["count"] >= 3
    body = call("/shine/suggest", query="pyth")
    assert body["keywords"][0]["text"].lower().startswith("pyth") and body["keywords"][0]["link"]
    body = call("/shine/suggest", query="bang", type="locations", limit=3)
    assert body["locations"][0] == {"id": 243, "name": "Bangalore", "state": "Karnataka", "kind": "city", "is_top_city": True,
                                    "link": "https://www.shine.com/job-search/jobs-in-bangalore"}
    body = call("/shine/locations", query="hyder")
    assert body["locations"][0]["id"] == 246
    body = call("/shine/locations", flat="false")
    assert body["count"] > 5000 and body["states"][0]["state"] == "All India"
    body = call("/shine/filters")
    assert len(body["experience"]) == 7 and len(body["salary"]) == 7 and body["departments"] and body["industries"]
    body = call("/shine/trending")
    assert body["trending_searches"] and body["top_searches"][0]["link"].startswith("https://www.shine.com/")
    assert status("/shine/suggest", query="x", type="cities") == 400
