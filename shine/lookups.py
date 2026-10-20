"""/shine/suggest, /shine/locations, /shine/filters, /shine/trending — the
BFF's keyword suggestions and city tree, the filter vocabularies (static
ids + the live department / industry / location facets of a bare search)
and the site's trending / top searches."""
from shine import fetch, refdata
from shine import parsers as P


def suggest(query, type="keywords", limit=10):
    """Search-box autocomplete: keywords with skill / job-title inference, or locations with their Shine city ids."""
    if type == "locations":
        raw = fetch.memoized("cities", lambda: fetch.bff(refdata.BFF_CITIES, label="city tree"), ttl=3600)
        items = P.locations(raw, query=query, limit=limit)
        return {"query": query, "type": type, "count": len(items), "locations": items}
    raw = fetch.bff(refdata.BFF_KEYWORD_SUGGESTIONS, {"suggestion": f'"{query}"'}, label=f"suggestions {query!r}")
    items = P.suggestions(raw, limit=limit)
    return {"query": query, "type": type, "count": len(items), "keywords": items}


def locations(query=None, flat=True):
    """Every location Shine's filter knows (states with their cities, plus the
    WFH / Hybrid / All India pseudo-locations); `query` narrows the flat list."""
    raw = fetch.bff(refdata.BFF_CITIES, label="city tree")
    if flat or query:
        items = P.locations(raw, query=query)
        return {"query": query, "count": len(items), "locations": items}
    tree = P.location_tree(raw)
    return {"query": None, "count": sum(len(s["cities"]) for s in tree), "states": tree}


def filters():
    """Every filter value the search takes: experience and salary bands, employment, shift and job types, plus live department, industry and city ids with job counts."""
    raw = fetch.search({"perpage": 1}, label="filter facets")
    return P.filters(raw)


def trending():
    """Shine's trending searches and most-clicked job searches, with their search links."""
    results = fetch.run_parallel([
        lambda: fetch.bff(refdata.BFF_TRENDING_SEARCHES, label="trending searches"),
        lambda: fetch.bff(refdata.BFF_TOP_SEARCHES, label="top searches"),
    ], 2)
    payloads = []
    for status, value in results:
        if status == "error":
            raise value
        payloads.append(value)
    return P.trending(*payloads)
