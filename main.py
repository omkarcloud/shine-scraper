"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from shine import refs
from shine.companies import jobs as company_jobs
from shine.jobs import details as job_details
from shine.jobs import search as search_jobs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id or any shine.com job link
    save("job_19680754.json", job_details("19680754"))

    # 20 jobs per page; filter by experience, salary, job type, industry and more
    save("search_software_engineer_bangalore.json", search_jobs("software engineer", "Bangalore"))

    # a company name, its Shine slug or a shine.com /job-search/<company>-jobs link
    save("company_google.json", company_jobs(refs.resolve_company("Google")))
