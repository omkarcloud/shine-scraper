"""Raw Shine payloads -> clean API objects. Pure functions, no network;
every parser tolerates missing / null / wrong-typed fields and never raises
on a partial payload.

Job cards come from the search and similar-jobs JSON (search_result /
job_card: the site's terse jXX keys); the job object from the BFF
job-description (or the job page's embedded copy of it, same shape);
suggestions, the city tree and trending lists from the BFF.

Intentionally dropped everywhere (noise, session state or unverified
meaning): the per-visitor flags is_shortlisted / is_applied /
candidate_review_status (jCrwSt) / candidate_response_window, the ranking
internals jSLA / service_level_agreement, jJBL / job_boost_level (kept only
as is_boosted), jCrdSrc / credit_source, featured_recruiter_score,
quality_assurance_flag, jTag, the presentation duplicates jSpt /
job_snippet (an HTML card snippet), jCNameB / jLocB / jKwdb / highlighted_*
(bold variants of fields we return), jKwds / jKwdns / keyword_suggestions /
keyword_synopsis (splits of the keyword list), the experience / salary
band ids (jEXID, jExMinId, jExMaxId, jSalMinID, jSalMaxID, experience_id,
min/max_experience_id, salary_min_id, salary_max_id — the labels and the
rupee bounds carry the information), the always-null placeholders jAC /
jCD / jHCD / jHRPBA / jQA / jCUID / jRF / doc_id / document_id /
konnect_ids / related_links / total_profile_skills, jWM / work_mode (0 on
every record, WFH is an employment type), jWSD / jCSR / jICV / cCO
(meaning unverified, null in every capture), jFR, jSJ, the `breadcrumb`
keyword, `tags` entries like "shinedefault", learning_products /
application_highlighter_product_id / atf / new_search / nova (upsell and
A/B markers), and the duplicate `next` / `previous` URLs (route_glue builds
our own links)."""
import re
from math import ceil

from shine import refdata, refs
from shine import shared as S
from shine.shared import as_dict, as_list, g, text

# ---- small shared pieces ---------------------------------------------------------------------------

def _label_value(table, labels, raw):
    """A site id ('1') -> its public snake value ('regular') via `table`
    (public -> id) and `labels` (id -> label); unknown ids keep their label."""
    key = text(raw)
    if key is None:
        return None
    public = {v: k for k, v in table.items()}.get(key)
    if public:
        return public
    label = labels.get(key)
    return S.lower_snake(label) if label else None


def employment_type(raw):
    return _label_value(refdata.EMPLOYMENT_TYPES, refdata.EMPLOYMENT_LABELS, raw)


def shift_type(raw):
    return _label_value(refdata.SHIFT_TYPES, refdata.SHIFT_LABELS, raw)


def job_type(raw):
    return _label_value(refdata.JOB_TYPES, refdata.JOB_TYPE_LABELS, raw)


def qualification(raw):
    level = S.to_int(raw)
    return refdata.QUALIFICATION_LABELS.get(level) if level is not None else None


def _hidden(value):
    """Shine masks recruiter contacts as 'hidden_email' / 'hidden_mobile'."""
    value = text(value)
    if not value or value.lower().startswith("hidden"):
        return None
    return value


def _link_item(title, slug):
    title, slug = text(title), text(slug)
    if not title and not slug:
        return None
    return {"title": title, "slug": slug, "link": S.search_link(slug)}


def _pairs(items):
    """[["Django", "django-jobs"], …] -> [{title, slug, link}]."""
    out = []
    for item in as_list(items):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            link = _link_item(item[0], item[1])
        elif isinstance(item, dict):
            link = _link_item(item.get("title") or item.get("name"), item.get("url") or item.get("slug"))
        else:
            link = None
        if link:
            out.append(link)
    return out


def _link_groups(groups):
    """{"Mysore": [[["Django jobs in mysore", "django-jobs-in-mysore"], …]], …}
    -> {"Mysore": [{title, slug, link}, …]} (the nesting depth varies)."""
    out = {}
    for name, value in as_dict(groups).items():
        flat = []
        stack = [value]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
                link = _link_item(item[0], item[1])
                if link:
                    flat.append(link)
            elif isinstance(item, list):
                stack = list(item) + stack
        if flat:
            out[text(name) or name] = flat
    return out


def company_profile(**fields):
    """The employer block shared by cards and the job object."""
    social = fields.get("social_links")
    return {
        "id": S.to_int(fields.get("id")),
        "name": text(fields.get("name")),
        "hiring_for": text(fields.get("hiring_for")),
        "logo": text(fields.get("logo")),
        "website": text(fields.get("website")),
        "domain": text(fields.get("domain")),
        "size": text(fields.get("size")),
        "headquarters": text(fields.get("headquarters")),
        "founded_year": S.to_int(fields.get("founded_year")),
        "description": S.multiline(fields.get("description")),
        "social_links": {k: text(v) for k, v in social.items() if text(v)} or None if isinstance(social, dict) else None,
        "is_top_company": S.flag(fields.get("is_top_company")),
        "updated_at": S.iso_datetime(fields.get("updated_at")),
    }


def recruiter(**fields):
    name, email, phone = text(fields.get("name")), _hidden(fields.get("email")), _hidden(fields.get("phone"))
    link = text(fields.get("link"))
    raw_contact = [text(fields.get("email")), text(fields.get("phone"))]
    if any(raw_contact):
        # Shine shows the recruiter's address and number on some ads and
        # masks them ("hidden_email" / "hidden_mobile") on others
        hidden = any(v and v.lower().startswith("hidden") for v in raw_contact) and not (email or phone)
    else:
        hidden = None
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "link": link,
        "has_profile_badge": S.flag(fields.get("has_profile_badge")),
        "is_contact_hidden": hidden,
    }


# ---- job cards (search / similar) ---------------------------------------------------------------------

def _company_id(raw_id, is_global):
    """Shine posts every imported ("global") ad from ONE shared account
    (769865 on 168 different employers in a 16-search sample: Google, Cisco,
    Capgemini, Accenture …), so on those ads the id names no company."""
    return None if is_global else raw_id


def job_card(raw, include_description=False):
    raw = as_dict(raw)
    job_id = text(raw.get("id"))
    is_global = S.flag(raw.get("g_job_flag"))
    description_html = raw.get("jJD") if isinstance(raw.get("jJD"), str) else None
    description_text = S.html_to_text(description_html) or S.multiline(raw.get("jJDT"))
    walk_in = job_type(raw.get("jJobType")) == "walk_in"
    out = {
        "id": job_id,
        "title": text(raw.get("jJT")),
        "link": S.job_link(raw.get("jSlug"), job_id),
        "company": company_profile(
            id=_company_id(raw.get("jCID"), is_global), name=raw.get("jCName"), hiring_for=raw.get("jHF"),
            logo=raw.get("jLU") or raw.get("cCLU"), website=raw.get("cCW"), domain=raw.get("cCDom"),
            size=raw.get("cCS"), headquarters=raw.get("cCH"), founded_year=raw.get("cFY"),
            description=None, social_links=raw.get("cSML"),
            is_top_company=raw.get("jTopCmp") if raw.get("jTopCmp") is not None else raw.get("cCTop"),
            updated_at=raw.get("cUD")),
        "locations": [loc for loc in (text(x) for x in as_list(raw.get("jLoc"))) if loc],
        "reporting_location": text(raw.get("jWLC")),
        "experience": S.experience_from_label(raw.get("jExp")),
        "salary": S.salary_from_label(raw.get("jSal")),
        "industry": text(raw.get("jInd")),
        "functional_area": text(raw.get("jArea")),
        "skills": S.csv_list(raw.get("jKwd")),
        "qualification": qualification(raw.get("jQL")),
        "employment_type": employment_type(raw.get("jEType")),
        "employment_tenure": text(raw.get("jETn")),
        "shift_type": shift_type(raw.get("jTypeC")),
        "job_type": job_type(raw.get("jJobType")),
        "is_walk_in": walk_in,
        "vacancies": S.to_int(raw.get("jVanc")),
        "applicant_count": S.to_int(raw.get("jACnt")),
        "compensation_package": text(raw.get("jPack")),
        "posted_at": S.iso_datetime(raw.get("jPDate")),
        "expires_at": S.iso_datetime(raw.get("jExpDate")),
        "is_early_applicant": S.flag(raw.get("early_applicant_badge")),
        "is_instant_apply": S.flag(raw.get("iaj")),
        "is_premium": S.flag(raw.get("jPJ")),
        "is_hot": S.flag(raw.get("jHJ")),
        "is_global": is_global,
        "recruiter": recruiter(name=raw.get("jRN"), email=raw.get("jRE"), phone=raw.get("jRP"),
                               link=raw.get("jRUrl"), has_profile_badge=None),
        "description_snippet": S.snippet(description_text),
    }
    if include_description:
        out["description_text"] = description_text
        out["description_html"] = S.clean_html(description_html)
    return out


# ---- facets ---------------------------------------------------------------------------------------------

def facets(raw):
    """{"fields": {"jFLoc": [["243", 3085, "Bangalore", 0], …], …}} ->
    {"locations": [{id, name, count}], "experience": [{value, label, count}], …}."""
    fields = as_dict(as_dict(raw).get("fields"))
    out = {}
    for key, public in refdata.FACET_KEYS.items():
        items = []
        for row in as_list(fields.get(key)):
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            fid, count, label = text(row[0]), S.to_int(row[1]), text(row[2])
            if fid is None and label is None:
                continue
            item = {"id": fid, "name": label, "count": count}
            mapping = refdata.FACET_PUBLIC.get(public)
            if mapping is not None:
                item = {"value": mapping.get(fid) or S.lower_snake(label), "label": label, "count": count, "id": fid}
            items.append(item)
        out[public] = items
    return out


# ---- search --------------------------------------------------------------------------------------------------

def search_meta(raw):
    """The SEO / navigation extras of a search answer."""
    raw = as_dict(raw)
    seo = as_dict(raw.get("seo_tags"))
    interlinking = as_dict(raw.get("interlinking_data"))
    related_groups = _link_groups(interlinking.get("related_interlinking_data"))
    related_groups.update(_link_groups(as_dict(raw.get("new_related_interlinking_data"))))
    if isinstance(raw.get("related_links_data"), dict):
        related_groups.update(_link_groups(raw.get("related_links_data")))
    qna = []
    for item in as_list(raw.get("qna")):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            question, answer = text(item[0]), S.html_to_text(item[1])
            if question:
                qna.append({"question": question, "answer": answer})
    return {
        "spelling_suggestion": text(raw.get("spelling_suggestion")),
        "related_searches": _pairs(raw.get("related_searches")),
        "related_links": {
            "by_location": _pairs(interlinking.get("keyword_interlinking_data")),
            "groups": related_groups or None,
        },
        "breadcrumbs": [b for b in (_link_item(x.get("title"), (text(x.get("url")) or "").split("/job-search/")[-1])
                                    for x in as_list(raw.get("breadcrumbs")) if isinstance(x, dict)) if b],
        "faq": qna,
        "seo": {
            "title": text(seo.get("title_tag")),
            "heading": text(seo.get("head_tag")),
            "description": text(seo.get("des_tag")),
            "canonical_link": S.search_link(raw.get("canonical_url")),
        },
        "is_location_relaxed": S.flag(raw.get("location_relaxed")),
    }


def search_result(raw, page, page_size, include_description=False, posted_after=None):
    """A search answer -> jobs + facets + meta + the pagination block
    route_glue lifts. `posted_after` (UTC ISO) drops older cards from the page."""
    raw = as_dict(raw)
    total = S.to_int(raw.get("count")) or 0
    query = as_dict(raw.get("query"))
    jobs = [job_card(c, include_description) for c in as_list(raw.get("results")) if isinstance(c, dict)]
    dropped = 0
    if posted_after:
        kept = [j for j in jobs if j.get("posted_at") and j["posted_at"] >= posted_after]
        dropped = len(jobs) - len(kept)
        jobs = kept
    pages = S.to_int(raw.get("num_pages"))
    out = {
        "query": text(query.get("q")),
        "location": text(query.get("loc")),
        "jobs": jobs,
        "facets": facets(raw.get("facets")),
    }
    out.update(search_meta(raw))
    if posted_after:
        out["filtered_out_count"] = dropped
    out["pagination"] = {"page": page, "items_per_page": page_size,
                         "total_pages": pages if pages is not None else (ceil(total / page_size) if total and page_size else 0),
                         "total_count": total}
    return out


def similar_result(raw, job_id, page, page_size, include_description=False):
    raw = as_dict(raw)
    total = S.to_int(raw.get("count")) or S.to_int(raw.get("results_found")) or 0
    about = as_dict(raw.get("related_job_attributes"))
    pages = S.to_int(raw.get("num_pages"))
    return {
        "job": {
            "id": text(job_id),
            "title": text(about.get("job_title")),
            "link": S.job_link(None, job_id),
            "locations": [loc for loc in (text(x) for x in str(about.get("locations") or "").split("||")) if loc],
            "experience": S.experience_from_label(about.get("experience")),
            "salary": S.salary_from_label(about.get("salary")),
            "industry": text(about.get("ind")),
            "functional_area": text(about.get("area")),
        },
        "jobs": [job_card(c, include_description) for c in as_list(raw.get("results")) if isinstance(c, dict)],
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": pages if pages is not None else (ceil(total / page_size) if total and page_size else 0),
                       "total_count": total},
    }


# ---- job details ------------------------------------------------------------------------------------------------

def _skills(job_keywords, keywords):
    """[{"python": true}, …] (or the comma list) -> ['python', …]."""
    out = []
    for item in as_list(job_keywords):
        if isinstance(item, dict):
            for name in item:
                name = text(name)
                if name and name.lower() not in out:
                    out.append(name.lower())
    if not out:
        out = S.csv_list(keywords)
    return out


def job_details(raw):
    """A job-description payload ({results: [job], application_insights, …})
    -> the job object, or None when the payload holds no job."""
    raw = as_dict(raw)
    job = g(raw, "results", 0)
    if not isinstance(job, dict) or not job.get("id"):
        return None
    job_id = text(job.get("id"))
    description_html = job.get("job_description") if isinstance(job.get("job_description"), str) else None
    description_text = S.html_to_text(description_html)
    salary_text = text(job.get("salary_text"))
    salary_hidden = bool(salary_text and "hidden" in salary_text.lower())
    if salary_hidden:
        # a hidden salary still carries minimum/maximum_salary, but they are
        # Shine's placeholder band (2-5 lakh on every hidden ad, Google's
        # senior roles included), not the employer's figures
        salary = {"label": None, "min": None, "max": None, "currency": refdata.CURRENCY, "period": "yearly",
                  "is_hidden": True}
    else:
        salary = S.salary_from_bounds(job.get("minimum_salary"), job.get("maximum_salary"), salary_text)
        if salary is not None:
            salary["is_hidden"] = False
    areas = [text(x) for x in as_list(job.get("functional_areas"))]
    area_ids = [text(x) for x in as_list(job.get("functional_area_ids"))]
    functional_areas = [{"id": area_ids[i] if i < len(area_ids) else None, "name": name}
                        for i, name in enumerate(areas) if name]
    tags = [t for t in (text(x) for x in as_list(job.get("tags"))) if t and t.lower() not in refdata.NOISE_TAGS]
    interlinking = as_dict(raw.get("job_description_interlinking"))
    link = S.job_link(job.get("slug"), job_id)
    is_global = S.flag(job.get("global_job_flag"))
    return {
        "id": job_id,
        "title": text(job.get("job_title")),
        "link": link,
        "apply_link": text(job.get("click_through_url")) or text(job.get("listing_url")) or link,
        "company": company_profile(
            id=_company_id(job.get("company_id"), is_global), name=job.get("company_name"), hiring_for=job.get("hiring_firm"),
            logo=job.get("company_logo"), website=job.get("company_website"), domain=job.get("company_domain"),
            size=job.get("company_size"), headquarters=job.get("company_headquarters"),
            founded_year=job.get("company_founded_year"), description=job.get("company_description"),
            social_links=job.get("company_social_media_links"), is_top_company=job.get("is_top_company"),
            updated_at=job.get("company_updated_date")),
        "locations": [loc for loc in (text(x) for x in as_list(job.get("locations"))) if loc],
        "location_details": [{"city": text(x.get("loc")), "state": text(x.get("state"))}
                             for x in as_list(job.get("location_states")) if isinstance(x, dict) and text(x.get("loc"))],
        "alternate_locations": [loc for loc in (text(x) for x in as_list(job.get("alternate_locations"))) if loc],
        "reporting_location": text(job.get("reporting_location")),
        "experience": S.experience_from_label(job.get("experience_summary") or job.get("experience")),
        "salary": salary,
        "compensation_package": text(job.get("compensation_pack")),
        "industry": text(job.get("industry")),
        "functional_areas": functional_areas,
        "skills": _skills(job.get("job_keywords"), job.get("keywords")),
        "skill_tags": {
            "level_three": [t for t in (text(x) for x in as_list(job.get("skill_tags_level_three"))) if t],
            "level_four": [t for t in (text(x) for x in as_list(job.get("skill_tags_level_four"))) if t],
            "level_five": [t for t in (text(x) for x in as_list(job.get("skill_tags_level_five"))) if t],
        },
        "tags": tags,
        "qualification": qualification(job.get("qualification_level")),
        "employment_type": employment_type(job.get("employment_type")),
        "employment_type_name": text(job.get("employment_type_name")),
        "shift_type": shift_type(job.get("job_type_category") or job.get("job_category")),
        "job_type": job_type(job.get("job_type")),
        "is_walk_in": job_type(job.get("job_type")) == "walk_in",
        "work_shift": text(job.get("work_shift_details")),
        "vacancies": S.to_int(job.get("vacancies") or job.get("job_vacancies")),
        "applicant_count": S.to_int(g(raw, "application_insights", "job_apply_count")) or S.to_int(job.get("job_application_count")),
        "description_text": description_text,
        "description_html": S.clean_html(description_html),
        "description_file_link": text(job.get("job_description_file")),
        "posted_at": S.iso_datetime(job.get("posted_date")),
        "expires_at": S.iso_datetime(job.get("expiry_date")),
        "description_updated_at": S.iso_datetime(job.get("job_description_modified_on")),
        "is_early_applicant": S.flag(job.get("early_applicant_badge")),
        "is_instant_apply": S.flag(job.get("instant_apply_job")),
        "is_hot": S.flag(job.get("hot_job_flag")),
        "is_premium": S.flag(job.get("premium_job_flag")),
        "is_global": is_global,
        "is_boosted": (S.to_int(job.get("job_boost_level")) or 0) > 0,
        "has_auto_connect": S.flag(job.get("auto_connect_enabled")),
        "recruiter": recruiter(name=job.get("recruiter_name"), email=job.get("recruiter_email"),
                               phone=job.get("recruiter_phone"), link=job.get("recruiter_url"),
                               has_profile_badge=job.get("has_recruiter_profile_badge")),
        "similar_job_ids": [text(x) for x in as_list(job.get("similar_jobs")) if text(x)],
        "related_searches": {
            "by_location": _pairs(interlinking.get("keyword_interlinking_data")),
            "groups": _link_groups(interlinking.get("related_interlinking_data")) or None,
            "title": text(raw.get("interlinking_job_title")),
            "location": text(raw.get("interlinking_location")),
        },
    }


# ---- lookups --------------------------------------------------------------------------------------------------

def suggestions(raw, limit=None):
    """The keyword-suggestions list -> [{text, type, skills, job_titles, industries, link}]."""
    out = []
    for item in as_list(raw):
        if not isinstance(item, dict):
            continue
        label = text(item.get("pdesc")) or text(item.get("alias"))
        if not label:
            continue
        inference = as_dict(item.get("inference"))
        out.append({
            "text": label,
            "type": text(item.get("type")) or "keyword",
            "skills": [t for t in (text(x) for x in as_list(inference.get("skill"))) if t],
            "job_titles": [t for t in (text(x) for x in as_list(inference.get("jt"))) if t],
            "industries": [t for t in (text(x) for x in as_list(inference.get("ind"))) if t],
            "link": S.search_link(f"{refs.slugify(label)}-jobs") if refs.slugify(label) else None,
        })
        if limit and len(out) >= limit:
            break
    return out


def locations(raw, query=None, limit=None):
    """The city tree -> [{id, name, state, kind, is_top_city, link}] (flat,
    deduped: the "Top Cities" group repeats cities listed under their state),
    optionally filtered by a case-insensitive `query` on the city or state
    name; names starting with the query sort first."""
    needle = (query or "").strip().lower()
    by_id = {}
    for state in as_list(as_dict(raw).get("results")):
        state = as_dict(state)
        state_name = text(state.get("pdesc"))
        if not state_name or state_name == "N/A":
            continue
        top = state_name == "Top Cities"
        for city in as_list(state.get("child")):
            city = as_dict(city)
            cid, name = text(city.get("cid")), text(city.get("cdesc"))
            if not name or cid in (None, "0"):
                continue
            kind = refdata.VIRTUAL_LOCATIONS.get(cid) or "city"
            entry = by_id.get(cid)
            if entry is None:
                entry = by_id[cid] = {
                    "id": S.to_int(cid), "name": name,
                    "state": None if (top or state_name == "All India") else state_name,
                    "kind": kind, "is_top_city": False,
                    "link": S.search_link(f"jobs-in-{refs.slugify(name)}") if kind == "city" else None,
                }
            if top:
                entry["is_top_city"] = True
            elif entry["state"] is None and state_name != "All India":
                entry["state"] = state_name
    out = list(by_id.values())
    if needle:
        out = [e for e in out if needle in e["name"].lower() or needle in (e["state"] or "").lower()]
        out.sort(key=lambda e: (not e["name"].lower().startswith(needle), not e["is_top_city"], e["name"].lower()))
    return out[:limit] if limit else out


def location_tree(raw):
    """The city tree as the site groups it: [{state, cities: [{id, name}]}]."""
    out = []
    for state in as_list(as_dict(raw).get("results")):
        state = as_dict(state)
        name = text(state.get("pdesc"))
        if not name or name == "N/A":
            continue
        cities = [{"id": S.to_int(c.get("cid")), "name": text(c.get("cdesc"))}
                  for c in as_list(state.get("child")) if isinstance(c, dict) and text(c.get("cdesc")) and text(c.get("cid")) != "0"]
        if cities:
            out.append({"state": name, "cities": cities})
    return out


def trending(trending_raw, top_raw):
    searches = []
    for title, url in as_dict(trending_raw).items():
        title, url = text(title), text(url)
        if title and url:
            searches.append({"title": title, "link": S.link(url)})
    top = []
    for item in as_list(top_raw):
        if not isinstance(item, dict) or item.get("visibility") is False:
            continue
        title, url = text(item.get("name")), text(item.get("url"))
        if title and url:
            top.append({"title": title, "link": S.link(url), "is_new": S.flag(item.get("new_icon"))})
    return {"trending_searches": searches, "top_searches": top}


def filters(search_raw):
    """The static filter vocabularies plus the live department / industry /
    location lists (with counts) from a bare search's facets."""
    live = facets(as_dict(search_raw).get("facets"))

    def bands(table, labels, ranges, unit):
        out = []
        for public, fid in table.items():
            low, high = ranges.get(fid, (None, None))
            out.append({"value": public, "label": labels.get(fid), f"min_{unit}": low, f"max_{unit}": high})
        return out

    return {
        "sort": [{"value": k, "label": "Relevance" if k == "relevance" else "Newest first"} for k in refdata.SORT_MODES],
        "experience": bands(refdata.EXPERIENCE_BANDS, refdata.EXPERIENCE_LABELS, refdata.EXPERIENCE_YEARS, "years"),
        "salary": [dict(b, currency=refdata.CURRENCY, unit="lakh_per_year") for b in
                   bands(refdata.SALARY_BANDS, refdata.SALARY_LABELS, refdata.SALARY_LAKH, "lakh")],
        "employment_type": [{"value": k, "label": refdata.EMPLOYMENT_LABELS[v]} for k, v in refdata.EMPLOYMENT_TYPES.items()],
        "shift_type": [{"value": k, "label": refdata.SHIFT_LABELS[v]} for k, v in refdata.SHIFT_TYPES.items()],
        "job_type": [{"value": k, "label": refdata.JOB_TYPE_LABELS[v]} for k, v in refdata.JOB_TYPES.items()],
        "departments": live.get("departments") or [],
        "industries": live.get("industries") or [],
        "locations": live.get("locations") or [],
        "total_jobs": S.to_int(as_dict(search_raw).get("count")),
    }
