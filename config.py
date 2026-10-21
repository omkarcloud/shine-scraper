"""Configuration for the Shine Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT         port the API listens on (default 8000)
    SHINE_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                 (default: none — direct). Shine's job-search and job JSON
                 answer plain HTTP with no cookies, so you very likely don't
                 need this. Set it only if you start seeing failures at high
                 volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

SHINE_PROXY = os.environ.get("SHINE_PROXY") or None

# Names the shine package reads.
SHINE_PROXY_COUNTRY = None             # unused here: SHINE_PROXY above is the whole proxy policy
SHINE_REQUIRE_PROXY = False            # direct is fine here; set SHINE_PROXY to route every request through a proxy
SHINE_MAX_ATTEMPTS = MAX_RETRIES       # attempts per upstream call
SHINE_BATCH_WORKERS = 4                # parallel upstream calls in /jobs/batch
SHINE_BROWSER_FALLBACK = False         # plain HTTP only — no browser in this package
SHINE_BROWSER_IDLE_SECONDS = 300
SHINE_BFF_API_KEY = os.environ.get("SHINE_BFF_API_KEY") or None   # None = the key in shine/refdata.py


def shine_proxy(fallback=False):
    """The proxy for one Shine request: SHINE_PROXY, or None for direct."""
    return os.environ.get("SHINE_PROXY") or None
