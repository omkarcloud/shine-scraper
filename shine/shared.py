"""Value helpers for the Shine parsers: safe nested access, numbers, text,
IST timestamps -> UTC ISO, HTML -> text, Shine's salary / experience labels
and site links. Pure functions, no network; every helper tolerates None and
junk.

The generic helpers (g / as_list / as_dict, num, to_int, text, multiline,
html_to_text) have the same semantics as jobstreet/shared.py and
stepstone/shared.py; they live here so the shine package stands alone (it
ships as its own open-source repo, which must not pull in other sites'
modules). Shine-specific: rupee labels quoted in lakh per year
("Rs 3.0 - 10 Lakh/Yr", "10 - 30 Lakh/Yr", "< 50,000 /Yr"), experience
labels in years ("0 to 4 Yrs", "< 1 Year", "> 15 Years") and naive IST
timestamps ("2026-10-13T05:35:15")."""
import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from shine import refdata

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- numbers -------------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def amount(value):
    """A money amount: whole numbers as int, others rounded to 2 places."""
    out = num(value)
    if out is None:
        return None
    return int(out) if float(out).is_integer() else round(out, 2)


def flag(value):
    """Shine's booleans arrive as true/false, 1/0 or "1"/"0"; junk -> None."""
    if isinstance(value, bool):
        return value
    if value in (1, 0, "1", "0", "true", "false", "True", "False"):
        return str(value).lower() in ("1", "true")
    return None


# ---- text ----------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (dict, list)):
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (descriptions)."""
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


def csv_list(value, lower=True):
    """'python,  azure,  aws' -> ['python', 'azure', 'aws'] (trimmed, deduped, order kept)."""
    if isinstance(value, list):
        items = [text(v) for v in value]
    else:
        items = [text(v) for v in str(value or "").split(",")]
    out = []
    for item in items:
        if not item:
            continue
        item = item.lower() if lower else item
        if item not in out:
            out.append(item)
    return out


def snippet(value, limit=300):
    """The first `limit` characters of a text, cut on a word boundary with an ellipsis."""
    value = text(value)
    if not value:
        return None
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


# ---- dates ---------------------------------------------------------------------------------

_IST = timezone(timedelta(hours=5, minutes=30))


def iso_datetime(value):
    """Shine's naive IST stamp '2026-10-13T05:35:15' (or one carrying +05:30 /
    Z) -> UTC ISO '2026-10-13T00:05:15Z'; a bare date -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?", value)
    if not match:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        return None
    stamp = datetime.strptime(f"{match.group(1)}T{match.group(2)}", "%Y-%m-%dT%H:%M:%S")
    zone = match.group(3)
    if not zone:
        stamp = stamp.replace(tzinfo=_IST)
    elif zone == "Z":
        stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        sign = 1 if zone[0] == "+" else -1
        digits = zone[1:].replace(":", "")
        stamp = stamp.replace(tzinfo=timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))))
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_date(value):
    out = iso_datetime(value)
    return out[:10] if out else None


# ---- links ---------------------------------------------------------------------------------

def link(path):
    """A site-relative path (or absolute URL) -> absolute https link on www.shine.com."""
    path = text(path)
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"{refdata.SITE}/{path.lstrip('/')}"


def job_link(slug=None, job_id=None):
    """'python-developer/meeden-labs/19819868' -> the job page; an id alone ->
    the id-only form the site resolves regardless of the slug words."""
    slug = text(slug)
    if slug:
        return f"{refdata.SITE}/jobs/{slug.strip('/')}"
    job_id = text(job_id)
    return f"{refdata.SITE}/jobs/job/{job_id}/{job_id}" if job_id else None


def search_link(slug):
    """'python-jobs-in-bangalore' -> the SEO search page."""
    slug = text(slug)
    return f"{refdata.SITE}/job-search/{slug.strip('/')}" if slug else None


# ---- labels -------------------------------------------------------------------------------

_EXP_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)", re.I)
_EXP_ONE = re.compile(r"(<|>|\bless than\b|\bmore than\b|\bupto\b|\bup to\b)?\s*(\d+(?:\.\d+)?)", re.I)


def experience_from_label(label):
    """'0 to 4 Yrs' -> {label, min_years: 0, max_years: 4}; '< 1 Year' -> 0..1;
    '> 15 Years' -> 15..None; '' -> None."""
    label = text(label)
    if not label:
        return None
    low, high = None, None
    match = _EXP_RANGE.search(label)
    if match:
        low, high = num(match.group(1)), num(match.group(2))
    else:
        match = _EXP_ONE.search(label)
        if match:
            value = num(match.group(2))
            qualifier = (match.group(1) or "").lower()
            if qualifier in ("<", "less than", "upto", "up to"):
                low, high = 0, value
            elif qualifier in (">", "more than"):
                low, high = value, None
            else:
                low = high = value
    return {"label": label, "min_years": amount(low), "max_years": amount(high)}


_SAL_FIGURE = re.compile(r"(\d+(?:,\d+)*(?:\.\d+)?)")


def _salary_figures(label):
    """Every figure in a rupee label, in rupees: a figure followed (before the
    next figure) by Lakh / Lac / LPA is scaled by 1e5, a comma-grouped or
    >= 1000 figure is already rupees ('< Rs 50,000 - 3.0 Lakh/Yr' -> 50000,
    300000)."""
    out = []
    matches = list(_SAL_FIGURE.finditer(label))
    low = label.lower()
    mentions_lakh = bool(re.search(r"lakh|lac\b|lacs|lpa", low))
    for i, match in enumerate(matches):
        raw = match.group(1)
        value = num(raw.replace(",", ""))
        if value is None:
            continue
        tail = low[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(low)]
        grouped = "," in raw or value >= 1000
        if not grouped and (re.search(r"lakh|lac\b|lacs|lpa", tail) or mentions_lakh):
            value *= refdata.LAKH
        out.append(value)
    return out


def salary_from_label(label):
    """'Rs 3.0 - 10 Lakh/Yr' -> {label, min: 300000, max: 1000000, currency: INR, period: yearly};
    '< Rs 50,000 - 3.0 Lakh/Yr' -> 50000..300000; '10 - 30 Lakh/Yr' -> 1000000..3000000. '' -> None."""
    label = text(label)
    if not label:
        return None
    low = label.lower()
    figures = _salary_figures(label)
    period = "yearly" if re.search(r"/\s*yr|per year|annum|yearly|lpa|p\.?a\.?\b", low) else \
        ("monthly" if re.search(r"/\s*mo|per month|monthly|p\.?m\.?\b", low) else None)
    lo = hi = None
    if len(figures) >= 2:
        lo, hi = min(figures[:2]), max(figures[:2])
    elif len(figures) == 1:
        if re.search(r"<|less than|up ?to|below", low):
            hi = figures[0]
        elif re.search(r">|more than|above|\+", low):
            lo = figures[0]
        else:
            lo = hi = figures[0]
    return {"label": label, "min": amount(lo), "max": amount(hi), "currency": refdata.CURRENCY,
            "period": period or "yearly"}


def salary_from_bounds(minimum, maximum, label=None):
    """The detail payload's minimum_salary / maximum_salary (rupees per year,
    as strings) -> the same shape as salary_from_label; both None -> the label
    parse, else None."""
    lo, hi = amount(minimum), amount(maximum)
    if lo is None and hi is None:
        return salary_from_label(label)
    if lo == 0 and hi == 0:
        return salary_from_label(label)
    out = salary_from_label(label) or {"label": None, "min": None, "max": None,
                                       "currency": refdata.CURRENCY, "period": "yearly"}
    out["min"], out["max"] = lo or out["min"], hi or out["max"]
    return out


def lower_snake(value):
    """'Work from home' -> 'work_from_home'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


# ---- HTML -> text ---------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()
    return out or None


def clean_html(value):
    """An HTML fragment with scripts / inline event handlers stripped; '' -> None."""
    value = value if isinstance(value, str) else None
    if not value or not value.strip():
        return None
    out = re.sub(r"<(script|style)\b.*?</\1>", "", value, flags=re.S | re.I)
    out = re.sub(r"\son\w+=\"[^\"]*\"", "", out)
    out = out.strip()
    return out or None
