#!/usr/bin/env python3
"""
BioinfoSites – stats aggregator.

Pulls live data straight from the three sibling repos (raw.githubusercontent.com,
no auth needed since they're public) and computes docs-free, ready-to-render
numbers into stats.json, which index.html fetches client-side.

Run locally: python3 scripts/generate_stats.py
"""
import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

RAW = "https://raw.githubusercontent.com/biokoderka/{repo}/main/{path}"


def fetch_json(repo, path):
    url = RAW.format(repo=repo, path=path)
    req = urllib.request.Request(url, headers={"User-Agent": "bioinfosites-stats/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def pick(counter: Counter, keys):
    """Return an ordered dict with just the requested keys (0 if missing)."""
    return {k: counter.get(k, 0) for k in keys}


# ── BioInfoJobs ────────────────────────────────────────────────────────────
def stats_jobs():
    data = fetch_json("bioinfo-jobs", "docs/jobs.json")
    # Since Oct 2026 jobs.json holds ACTIVE offers only (archived ones live in
    # docs/archive.json), so every number below describes the current board.
    jobs = [j for j in data.get("jobs", []) if not j.get("archived")]
    total = len(jobs)

    geo = Counter(j.get("geo") for j in jobs)
    sector = Counter(j.get("category") for j in jobs)
    seniority = Counter(j.get("seniority") for j in jobs)

    return {
        "total": total,
        "archived": data.get("archived_count", 0),
        "geo": pick(geo, ["USA", "Europe", "Other", "Remote", "Poland"]),
        "sector": pick(sector, ["Pharma/Biotech", "Academia", "Clinical", "Startup"]),
        "seniority": pick(seniority, ["Mid", "Senior", "PostDoc", "PI/Lead"]),
    }


# ── BioInfoNews ────────────────────────────────────────────────────────────
def stats_news():
    board = fetch_json("bioinfo-news", "news.json").get("entries", [])
    research = fetch_json("bioinfo-news", "research-news.json").get("entries", [])

    active = [e for e in board if not e.get("archived")]
    board_type = Counter(e.get("type") for e in active)

    research_type = Counter(e.get("type") for e in research)

    return {
        "board_total": len(active),
        "board_types": {
            "Kursy stałe": board_type.get("course-free", 0),
            "Meetupy": board_type.get("meetup", 0),
            "Inne inicjatywy": board_type.get("other", 0),
            "Kursy z terminem": board_type.get("course-dated", 0),
            "Projekty": board_type.get("project", 0),
        },
        "board_courses_total": board_type.get("course-free", 0) + board_type.get("course-dated", 0),
        "research_total": len(research),
        "research_types": {
            "Artykuły / preprinty": research_type.get("research", 0),
            "Narzędzia": research_type.get("narzedzie", 0),
            "Granty": research_type.get("grant", 0),
        },
    }


# ── BioInfoUni ─────────────────────────────────────────────────────────────
def stats_uni():
    unis = fetch_json("bioinfo-uni", "universities.json").get("universities", [])
    reviews = fetch_json("bioinfo-uni", "reviews.json").get("reviews", [])

    cities = Counter(u.get("Miasto") for u in unis)
    levels = Counter(u.get("Typ oferty") for u in unis)
    second_degree = Counter(u.get("Czy jest II stopień na tej samej uczelni?") for u in unis)
    uczelnie = {u.get("Uczelnia") for u in unis if u.get("Uczelnia")}

    top_cities = ["Warszawa", "Kraków", "Poznań", "Wrocław"]
    other_cities = sum(v for k, v in cities.items() if k not in top_cities)

    return {
        "programs": len(unis),
        "universities": len(uczelnie),
        "cities_count": len(cities),
        "cities": {**pick(cities, top_cities), "Inne miasta": other_cities},
        "levels": {
            "I stopień": levels.get("I stopień", 0),
            "II stopień": levels.get("II stopień", 0) + levels.get("II stopień / specjalizacja", 0),
            "Studia podyplomowe": levels.get("studia podyplomowe", 0),
        },
        "reviews": len(reviews),
        "offers_second_degree": second_degree.get("Tak", 0),
        "no_second_degree": second_degree.get("Brak", 0),
        # duplicated as a nested group so the bar-width calc on the page can
        # find all three numbers under one data-stat-group path
        "reviews_group": {
            "reviews": len(reviews),
            "offers_second_degree": second_degree.get("Tak", 0),
            "no_second_degree": second_degree.get("Brak", 0),
        },
    }


def main():
    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": stats_jobs(),
        "news": stats_news(),
        "uni": stats_uni(),
    }
    out = Path(__file__).parent.parent / "stats.json"
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ stats.json written → {out}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
