"""Cache TTL per /shine/* endpoint (cache.py, keyed on the validated params —
marshmallow fills the defaults, so an omitted param and its default share a
row).

Job listings churn hourly (new ads, expiries, early-applicant badges flip);
one ad changes rarely once posted; the similar-jobs rail follows the
listings; suggestions, the city tree, trending searches and the filter
reference are stable for days."""
from datetime import timedelta

SEARCH_CACHE = timedelta(hours=1)
JOB_CACHE = timedelta(hours=6)
SIMILAR_CACHE = timedelta(hours=3)
COMPANY_JOBS_CACHE = timedelta(hours=1)
SUGGEST_CACHE = timedelta(days=7)
LOCATIONS_CACHE = timedelta(days=7)
FILTERS_CACHE = timedelta(days=1)
TRENDING_CACHE = timedelta(hours=12)
