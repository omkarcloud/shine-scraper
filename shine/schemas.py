"""Marshmallow request schemas for every /shine/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Shine resolvers (refs.py) and the site's filter vocabularies
(refdata.py). Every schema's load() output is the kwargs dict its endpoint
function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job id OR any shine.com job link;
`company` a company name, its Shine slug or a /job-search/<company>-jobs
link; `location` city names (comma-separated) or Shine city ids; `query`
free text or a pasted shine.com /job-search/ link (its slug and filter
params are honoured)."""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, PageField, PageSizeField, PositiveInt,
                           QueryField, RefField, StrippedString)
from shine import refdata, refs
from shine.jobs import MAX_BATCH


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class LocationField(RefField):
    resolver = staticmethod(refs.resolve_location)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class SearchQueryField(StrippedString):
    """Free text, or a pasted shine.com /job-search/ link whose slug carries
    the keyword (and location / page / filters, applied by the schema)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        if len(value) > 200 and not value.lower().startswith(("http", "www.", "shine.com")):
            raise ValidationError("Longer than maximum length 200.")
        try:
            parsed = refs.resolve_search_link(value)
        except ValueError as e:
            raise ValidationError(str(e))
        if parsed.get("params") or parsed.get("location") or parsed.get("page"):
            return parsed          # a link: the schema unpacks it (validate_link)
        return parsed["query"]


class JobListField(fields.Field):
    """'19819868, https://www.shine.com/jobs/x/y/19533675' -> ['19819868', '19533675']
    (resolved, deduped, 1..MAX_BATCH)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        out = []
        for item in str(value or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                job_id = refs.resolve_job(item)
            except ValueError as e:
                raise ValidationError(f"'{item}': {e}")
            if job_id not in out:
                out.append(job_id)
        if not out:
            raise ValidationError("Must list at least one job id or link (comma-separated).")
        if len(out) > MAX_BATCH:
            raise ValidationError(f"At most {MAX_BATCH} jobs.")
        return out


class IdListField(CommaListField):
    """Shine department / industry ids ('1301,1001') as the facets list them."""

    def __init__(self, kind, **kwargs):
        kwargs.setdefault("max_items", 10)
        super().__init__(upper=False, **kwargs)
        self.kind = kind

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        for item in items or []:
            if not item.isdigit():
                raise ValidationError(f"'{item}' is not a Shine {self.kind} id (digits, see /shine/filters).")
        return items


# ---- jobs --------------------------------------------------------------------------------------------------

class _Listing(BaseSchema):
    page = PageField(max_page=refdata.MAX_PAGE)
    page_size = PageSizeField(default=refdata.DEFAULT_PAGE_SIZE, max_size=refdata.MAX_PAGE_SIZE)
    include_description = Flag(load_default=False)


class _Filtered(_Listing):
    location = LocationField()
    sort = ChoiceField(refdata.SORT_MODES, load_default=None)
    experience = CommaListField(value_map=refdata.EXPERIENCE_BANDS, max_items=7)
    salary = CommaListField(value_map=refdata.SALARY_BANDS, max_items=7)
    employment_type = CommaListField(value_map=refdata.EMPLOYMENT_TYPES, max_items=4)


class JobSearchSchema(_Filtered):
    query = SearchQueryField()
    min_experience = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=0, max=50))
    min_salary = fields.Float(load_default=None, validate=validate.Range(min=0, max=1000))
    shift_type = CommaListField(value_map=refdata.SHIFT_TYPES, max_items=2)
    job_type = CommaListField(value_map=refdata.JOB_TYPES, max_items=2)
    department = IdListField("department")
    industry = IdListField("industry")
    posted_within_days = PositiveInt(max_value=365)

    @validates_schema
    def validate_link(self, data, **kwargs):
        """A pasted search link: unpack its slug / params into the fields the
        caller left empty, and refuse a bare link with nothing to search."""
        query = data.get("query")
        if isinstance(query, dict):
            params = query.get("params") or {}
            data["query"] = query.get("query")
            if not data.get("location") and query.get("location"):
                data["location"] = query["location"]
            if not data.get("location") and params.get("location"):
                # the link's ?location=<city id> filter (search_params sends digit-only locations as ids)
                city_ids = [v.strip() for v in params["location"] if str(v).strip().isdigit()]
                if city_ids:
                    data["location"] = ",".join(city_ids)
            if data.get("page") in (None, 1) and query.get("page"):
                data["page"] = max(1, min(int(query["page"]), refdata.MAX_PAGE))
            for site_key, public_key, table in (("fexp", "experience", refdata.EXPERIENCE_BANDS),
                                                ("fsalary", "salary", refdata.SALARY_BANDS),
                                                ("emp_type", "employment_type", refdata.EMPLOYMENT_TYPES),
                                                ("shift_type", "shift_type", refdata.SHIFT_TYPES),
                                                ("job_type", "job_type", refdata.JOB_TYPES)):
                if not data.get(public_key) and params.get(site_key):
                    data[public_key] = [v for v in params[site_key] if v in table.values()] or None
            for site_key, public_key in (("farea", "department"), ("findustry", "industry")):
                if not data.get(public_key) and params.get(site_key):
                    data[public_key] = [v for v in params[site_key] if str(v).isdigit()] or None
            if data.get("min_experience") is None and params.get("minexp"):
                try:
                    data["min_experience"] = int(params["minexp"][0])
                except (TypeError, ValueError):
                    pass
            if data.get("min_salary") is None and params.get("minsal"):
                try:
                    data["min_salary"] = float(params["minsal"][0])
                except (TypeError, ValueError):
                    pass
            if not data.get("sort") and params.get("sort") == ["1"]:
                data["sort"] = refdata.SORT_MODES["newest"]
        if not any(data.get(k) for k in ("query", "location", "experience", "salary", "employment_type", "shift_type",
                                         "job_type", "department", "industry", "min_experience", "min_salary")):
            raise ValidationError({"query": ["Give a keyword, a location or at least one filter."]})


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


class SimilarJobsSchema(_Listing):
    job = JobField()


# ---- companies ----------------------------------------------------------------------------------------------

class CompanyJobsSchema(_Filtered):
    company = CompanyField()


# ---- lookups -------------------------------------------------------------------------------------------------

class SuggestSchema(BaseSchema):
    query = QueryField(max_length=100)
    type = ChoiceField(["keywords", "locations"], load_default="keywords")
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=50))


class LocationsSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    flat = Flag(load_default=True)


class EmptySchema(BaseSchema):
    pass
