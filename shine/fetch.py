"""Shine.com transport: plain curl_cffi, no browser in the normal path,
validated 2026-10-19 from a direct egress with no cookies.

Surfaces (all on www.shine.com):

  search(params)        /api/v2/search/simple/ — the open JSON behind every
                        /job-search/<slug> page: 20-50 cards per call with
                        the full HTML description, every filter the site has
                        (fexp / fsalary / farea / findustry / emp_type /
                        shift_type / job_type / minexp / minsal / sort),
                        facets with counts, related searches, breadcrumbs,
                        Q&A. No key, no cookies. mapi.shine.com serves the
                        same path (the BFF's own `next` links point there).
  similar(job_id, …)    /api/v2/search/similar/ — the "Similar Jobs" rail.
  bff(path, params)     /pages/bff/api/v1/… — the Next.js app's
                        backend-for-frontend: job-description (the 97-field
                        job object), the SSR job search (q + url slug, the
                        company pages), keyword suggestions, the city tree,
                        trending and top searches. Needs the x-api-key the
                        site's own bundle carries (refdata.BFF_API_KEY,
                        config.SHINE_BFF_API_KEY overrides); a 401 means it
                        rotated.
  job_page(job_id)      /jobs/x/y/<id> HTML — the job page resolves on the id
                        alone; its React Server Components payload embeds the
                        same job-description object (react-query dehydrated
                        state). Used only when the BFF key is refused, so a
                        key rotation degrades to one HTML fetch instead of an
                        outage.

Anti-bot: Akamai fronts the site but answered every plain request without a
challenge (robots.txt disallows /api/* for crawlers, nothing enforces it).
Egress: every session rides a sticky exit from config.shine_proxy() (the
hosted service: an India residential exit, config.SHINE_PROXY_COUNTRY);
with config.SHINE_REQUIRE_PROXY set there is no direct mode — no
proxy, no call. A thread keeps its exit until a call fails; a retry runs on
a fresh exit, and when EVERY curl attempt was blocked one headful patchright
Chrome (also on an exit) warms on the homepage and replays the URL as an
in-page fetch — the upwork/indeed escalation — gated by
config.SHINE_BROWSER_FALLBACK.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  ShineUpstreamError  transport failure / 5xx / unexpected body  — retryable
  ShineBlocked        challenge / 403 / 429 / HTML where JSON was due — retryable on a new exit
  ShineBadRequest     the site rejected the params               — never retried
  ShineNotFound       no such job                                — never retried
  ShineKeyRejected    the BFF refused the x-api-key (401)        — the HTML fallback trigger
"""
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from shine import refdata

IMPERSONATE = "chrome"
TIMEOUT = (10, 40)            # (connect, read)
BLOCK_STATUSES = (403, 429, 503)
CHALLENGE_MARKERS = ("access denied", "reference #", "akamai", "just a moment", "cf-chl", "attention required")
JSON_HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9",
                "referer": refdata.SITE + "/"}
HTML_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9"}


class ShineUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class ShineBlocked(ShineUpstreamError, Blocked):
    """Challenge / 403 / 429 / an HTML page where JSON was due — retryable on a fresh exit."""


class ShineBadRequest(BadRequest):
    """The site rejected the params — never retried."""


class ShineNotFound(NotFound):
    """No such job — never retried."""


class ShineKeyRejected(ShineUpstreamError):
    """The BFF refused our x-api-key (401): it rotated with a site deploy."""


def bff_api_key():
    return getattr(config, "SHINE_BFF_API_KEY", None) or refdata.BFF_API_KEY


def dump_debug(name, text):
    """Write a raw response to $SHINE_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("SHINE_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()


def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store


def _exit(fallback=False):
    """The proxy exit for a NEW session. With config.SHINE_REQUIRE_PROXY set
    (the hosted service) there is no direct mode: no proxy means the call
    fails rather than reaching Shine from the server's own IP."""
    proxy = config.shine_proxy(fallback=fallback)
    if not proxy and getattr(config, "SHINE_REQUIRE_PROXY", False):
        raise ShineUpstreamError("no Shine proxy configured (Shine is never contacted from the server's IP)")
    return proxy


def _session(key, proxy_factory):
    """The thread's session for `key`, built on first use with the exit
    proxy_factory() returns — so a thread keeps one sticky exit until a
    failure drops the session."""
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        proxy = proxy_factory()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def is_challenged(status, text):
    head = (text or "")[:4000].lower()
    return status in BLOCK_STATUSES and any(m in head for m in CHALLENGE_MARKERS)


def _classify(status, text, label, json_body=True):
    """Raise the failure a response represents, else return its JSON (or text)."""
    text = text or ""
    if is_challenged(status, text):
        dump_debug("challenged", text)
        raise ShineBlocked(f"anti-bot challenge (HTTP {status}) on {label}")
    if status in (403, 429):
        raise ShineBlocked(f"HTTP {status} on {label}")
    if status == 401:
        raise ShineKeyRejected(f"Shine's BFF refused the api key on {label} (HTTP 401): the key has rotated — "
                               "re-read serverConfig.apiKey from the site's client bundle and set SHINE_BFF_API_KEY")
    if status in (404, 410):
        raise ShineNotFound(f"Shine has no page for {label}")
    if status == 400:
        raise ShineBadRequest(f"Shine rejected the request on {label}: {text[:200]}")
    if status >= 500:
        raise ShineUpstreamError(f"HTTP {status} on {label}")
    if status != 200:
        raise ShineUpstreamError(f"HTTP {status} on {label}")
    if not json_body:
        return text
    try:
        return json.loads(text)
    except ValueError:
        dump_debug("non_json", text)
        if "<html" in text[:2000].lower():
            # the site answers an HTML "Error Page" (200 or 404) for unknown
            # API paths and an Akamai page for refused clients
            if "error page" in text[:200000].lower():
                raise ShineNotFound(f"Shine has no API answer for {label}")
            raise ShineBlocked(f"HTML page where JSON was due on {label}")
        raise ShineUpstreamError(f"non-JSON answer on {label}")


def _attempts(label, send, browser=None):
    """Run send(session) under the retry policy: ShineUpstreamError (incl.
    Blocked) retries on a fresh exit up to config.SHINE_MAX_ATTEMPTS times;
    BadRequest / NotFound / KeyRejected surface at once. When every attempt
    was BLOCKED and a `browser` callable is given, it runs last (the headful
    patchright escalation)."""
    attempts = max(1, int(config.SHINE_MAX_ATTEMPTS))
    last = None
    blocked_only = True
    for attempt in range(1, attempts + 1):
        # attempt 1 reuses the thread's sticky session; a retry builds a fresh
        # one on a fresh exit (the failed session is dropped below)
        key = "primary" if attempt == 1 else f"retry-{attempt}"
        if attempt > 1:
            _drop_session(key)      # an earlier call's retry session would reuse its old exit
        try:
            sess = _session(key, lambda: _exit(fallback=attempt > 1))
            return send(sess)
        except (ShineBadRequest, ShineNotFound, ShineKeyRejected):
            raise
        except ShineBlocked as e:
            last = e
        except ShineUpstreamError as e:
            last, blocked_only = e, False
        except Exception as e:
            last, blocked_only = ShineUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}"), False
        _drop_session(key)
        print(f"shine: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.5 * attempt)
    if blocked_only and browser is not None and config.SHINE_BROWSER_FALLBACK:
        print(f"shine: every curl attempt on {label} was blocked; trying the browser")
        try:
            return browser()
        except (ShineBadRequest, ShineNotFound, ShineKeyRejected):
            raise
        except ShineUpstreamError as e:
            last = e
        except Exception as e:
            last = ShineUpstreamError(f"browser fetch failed on {label}: {type(e).__name__}: {e}")
    raise last


# ---- browser fallback (headful patchright, in-page fetch) ---------------------------------------------------

class _Browser:
    """One headful patchright Chrome, opened on demand when every curl attempt
    was blocked, warmed on the homepage (Akamai cookies), reused while busy and
    closed after config.SHINE_BROWSER_IDLE_SECONDS unused."""

    def __init__(self):
        self.lock = threading.Lock()
        self.driver = None
        self.last_used = 0.0
        self.closer = None

    def _open(self):
        from chrome_manager import create_scope
        from patchright_driver import PatchrightDriver
        with create_scope():
            driver = PatchrightDriver(proxy_url=_exit(fallback=True), headless=False,
                                      geoip_timezone=True)
        try:
            driver.nav(refdata.SITE + "/", referer="https://www.google.com/", mode="blocked")
        except Exception:
            driver.close()
            raise
        return driver

    def _close_if_idle(self):
        while True:
            time.sleep(30)
            with self.lock:
                if self.driver is None:
                    self.closer = None
                    return
                if time.time() - self.last_used > config.SHINE_BROWSER_IDLE_SECONDS:
                    self._drop()
                    self.closer = None
                    return

    def _drop(self):
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:
                pass
        self.driver = None

    def _ensure(self):
        if self.driver is None:
            self.driver = self._open()
        if self.closer is None:
            self.closer = threading.Thread(target=self._close_if_idle, daemon=True)
            self.closer.start()
        self.last_used = time.time()

    def get(self, url, headers, label, json_body=True):
        with self.lock:
            self._ensure()
            try:
                res = self.driver.get(url, headers=headers)
            except Exception:
                self._drop()
                raise
            status = int(getattr(res, "status_code", 0) or 0)
            if not status:
                self._drop()
                raise ShineUpstreamError(f"browser fetch failed on {label}: {getattr(res, 'error', None)}")
            if status in BLOCK_STATUSES:
                self._drop()
        return _classify(status, res.text or "", label, json_body=json_body)


_browser = _Browser()


# ---- requests ------------------------------------------------------------------------------------

def _url(path, params=None, host=refdata.HOST):
    query = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    return f"https://{host}{path}" + (("?" + urlencode(query, doseq=True)) if query else "")


def get_json(path, params=None, label=None, headers=None, expect=None):
    """GET a JSON surface on www.shine.com -> its payload (dict). `expect`
    is a key the payload must carry, else the answer counts as unexpected."""
    url = _url(path, params)
    label = label or path
    headers = dict(JSON_HEADERS, **(headers or {}))

    def check(body, raw):
        if not isinstance(body, dict) or (expect and expect not in body):
            dump_debug("unexpected", raw)
            raise ShineUpstreamError(f"unexpected payload on {label}")
        return body

    def send(sess):
        resp = sess.get(url, headers=headers, timeout=TIMEOUT)
        return check(_classify(resp.status_code, resp.text, label), resp.text)

    def browser():
        body = _browser.get(url, headers, label)
        return check(body, json.dumps(body))
    return _attempts(label, send, browser)


def get_html(path, label=None):
    """GET an HTML page -> its text."""
    url = _url(path)
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=HTML_HEADERS, timeout=TIMEOUT)
        return _classify(resp.status_code, resp.text, label, json_body=False)

    def browser():
        return _browser.get(url, HTML_HEADERS, label, json_body=False)
    return _attempts(label, send, browser)


# ---- surfaces ----------------------------------------------------------------------------------------

def search(params, label="job search"):
    """The open search JSON. `params` are the site's own names; `fl` (the
    card fields, refdata.SEARCH_FIELDS) is added so cards carry the salary."""
    params = dict(params or {})
    params.setdefault("fl", refdata.SEARCH_FIELDS)
    return get_json(refdata.SEARCH_PATH, params, label=label, expect="results")


def similar(job_id, page=1, per_page=20, label=None):
    return get_json(refdata.SIMILAR_PATH, {"jobid": job_id, "page": page, "perpage": per_page},
                    label=label or f"similar jobs for {job_id}", expect="results")


def bff(path, params=None, label=None):
    """A BFF call with the site's x-api-key -> the `data` member (the BFF
    wraps every answer as {data, message, statusCode})."""
    body = get_json(refdata.BFF_PATH + path, params, label=label or path, headers={"x-api-key": bff_api_key()})
    if body.get("code") == "BAD_REQUEST":
        raise ShineBadRequest(f"Shine rejected the request on {label or path}: {body.get('message')}")
    if "data" not in body:
        raise ShineUpstreamError(f"BFF answer without data on {label or path}")
    return body["data"]


def job_description(job_id):
    """The 97-field job object from the BFF, or (key rotated) from the job
    page's embedded React Server Components payload."""
    label = f"job {job_id}"
    try:
        data = bff(refdata.BFF_JOB_DESCRIPTION, {"jobId": job_id}, label=label)
    except ShineKeyRejected as e:
        print(f"shine: {e}; falling back to the job page HTML")
        return job_page_description(job_id)
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        raise ShineNotFound(f"Shine has no job with the id {job_id}")
    return data


_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)


def rsc_payload(html):
    """The React Server Components flight text a Next.js app-router page
    embeds as self.__next_f.push([1, "..."]) chunks, joined and unescaped."""
    parts = []
    for chunk in _RSC_CHUNK_RE.findall(html or ""):
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(parts)


def rsc_query_data(flight, query_key):
    """The react-query dehydrated `data` whose queryKey starts with `query_key`
    (e.g. "job-description"), or None."""
    marker = f'"queryKey":["{query_key}"'
    at = flight.find(marker)
    if at < 0:
        return None
    start = flight.rfind('"queries":[', 0, at)
    if start < 0:
        return None
    try:
        queries, _ = json.JSONDecoder().raw_decode(flight[flight.find("[", start):])
    except ValueError:
        return None
    for query in queries if isinstance(queries, list) else []:
        key = query.get("queryKey") if isinstance(query, dict) else None
        if isinstance(key, list) and key and key[0] == query_key:
            return (query.get("state") or {}).get("data")
    return None


def job_page_description(job_id):
    """The job page's embedded job-description payload (same shape as the
    BFF's `data`): the fallback when the BFF key is refused."""
    label = f"job page {job_id}"
    html = get_html(f"/jobs/job/{job_id}/{job_id}", label=label)
    if re.search(r"<title>\s*Shine\.com\s*</title>", html[:20000] or "", re.I) and "__next_f" not in html[:400000]:
        raise ShineNotFound(f"Shine has no job with the id {job_id}")
    data = rsc_query_data(rsc_payload(html), "job-description")
    if not isinstance(data, dict) or not data.get("results"):
        dump_debug(f"job_page_{job_id}", html)
        if "<title>Shine.com</title>" in html[:20000]:
            raise ShineNotFound(f"Shine has no job with the id {job_id}")
        raise ShineUpstreamError(f"no job-description payload in the page on {label}")
    return data


# ---- memo / parallel --------------------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 128


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    # Smoke test: python shine/fetch.py
    body = search({"q": "python", "loc": "bangalore", "perpage": 2})
    print("search:", body.get("count"), [j.get("jJT") for j in body["results"]])
    job_id = body["results"][0]["id"]
    data = job_description(job_id)
    print("job:", data["results"][0].get("job_title"), "|", data["results"][0].get("company_name"))
    print("similar:", similar(job_id, per_page=2).get("count"))
    print("suggest:", [s.get("pdesc") for s in bff(refdata.BFF_KEYWORD_SUGGESTIONS, {"suggestion": '"pyth"'})][:4])
    print("page fallback:", job_page_description(job_id)["results"][0].get("job_title"))
