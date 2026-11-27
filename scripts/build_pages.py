#!/usr/bin/env python3
"""
Static pages generated from docs/jobs.json + docs/archive.json.

    docs/browse/<slug>.html     region, city, sector and level pages (SEO landing pages)
    docs/companies/…            employer directory + one page per employer
    docs/skills.html            "what employers ask for" – skill ranking with trends
    docs/reports/<yyyy>-q<n>    quarterly job-market reports (+ .json for carousels)
    docs/sitemap.xml

It also (re)computes the derived fields from enrich.py on every offer –
active and archived – so the score and badges exist for the whole archive.

Run after fetch_jobs.py / add_job.py (the workflows do):
    python scripts/build_pages.py
Only the standard library is needed. Output depends only on the data
(dates come from jobs.json "updated"), so a re-run without new data
changes nothing.
"""
import html
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich import enrich, slugify, TIERS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
JOBS_PATH = DOCS / "jobs.json"
ARCHIVE_PATH = DOCS / "archive.json"
BASE_URL = "https://biokoderka.github.io/bioinfo-jobs/"
FRESH_DAYS = 7
MIN_REL = 60          # "relevant" threshold used for skill statistics

STATIC_PAGES = [  # (path, changefreq, priority) – hand-written pages
    ("", "weekly", "1.0"), ("match.html", "weekly", "0.8"), ("career.html", "weekly", "0.8"),
    ("stats.html", "weekly", "0.7"), ("submit.html", "monthly", "0.5"), ("archive.html", "weekly", "0.4"),
    ("privacy.html", "yearly", "0.1"),
]

esc = lambda s: html.escape(str(s if s is not None else ""), quote=True)


# ── DATA ─────────────────────────────────────────────────────────────────────
def load(path):
    if not path.exists():
        return {"jobs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_if_changed(path, data, compact):
    text = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) if compact
            else json.dumps(data, ensure_ascii=False, indent=1))
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def seen_date(j):
    return (j.get("first_seen") or j.get("date") or "")[:10]


def employer_of(j):
    return j.get("employer")


# ── CLASSIFICATION ───────────────────────────────────────────────────────────
# Big pharma & CROs – the "Pharma" browse page; other industry offers are "Biotech".
BIG_PHARMA = re.compile(
    r"astrazeneca|roche|genentech|\bgsk\b|glaxo|novartis|sanofi|takeda|bristol[- ]myers|\bbms\b|pfizer|\bmerck\b|\bmsd\b"
    r"|johnson ?& ?johnson|janssen|abbvie|amgen|gilead|bayer|boehringer|novo nordisk|eli lilly|\blilly\b|regeneron"
    r"|biogen|astellas|daiichi|servier|\bucb\b|ipsen|teva|sandoz|polpharma|adamed|moderna|biontech|vertex|\bcsl\b"
    r"|iqvia|\bicon\b|parexel|\bppd\b|syneos|cytel|medpace|labcorp|charles river|thermo fisher|fortrea|worldwide clinical",
    re.I)

CITY = {
    "warszawa": re.compile(r"warsz|warsaw", re.I),
    "krakow": re.compile(r"krak[oó]w|cracow", re.I),
    "wroclaw": re.compile(r"wroc[lł]aw", re.I),
    "poznan": re.compile(r"pozna[nń]", re.I),
    "trojmiasto": re.compile(r"gda[nń]sk|gdynia|sopot", re.I),
    "lodz": re.compile(r"[lł][oó]d[zź]", re.I),
}


def city_match(key):
    return lambda j: bool(CITY[key].search(j.get("location") or ""))


def is_pharma(j):
    return j.get("category") in ("Pharma/Biotech", "Clinical") and bool(BIG_PHARMA.search(employer_of(j) or j.get("company") or ""))


# slug, group, short label, h1, intro, predicate, board query
BROWSE = [
    ("poland", "Region", "🇵🇱 Poland", "Bioinformatics jobs in <em>Poland</em>",
     "Bioinformatics, computational biology and biostatistics offers located in Poland — pharma R&D hubs, CROs, institutes and startups.",
     lambda j: j.get("geo") == "Poland", "geo=Poland"),
    ("europe", "Region", "🇪🇺 Europe", "Bioinformatics jobs in <em>Europe</em>",
     "Computational biology and bioinformatics offers across Europe (outside Poland), from EMBL-style institutes to pharma and biotech.",
     lambda j: j.get("geo") == "Europe", "geo=Europe"),
    ("usa", "Region", "🇺🇸 USA", "Bioinformatics jobs in the <em>USA</em>",
     "Bioinformatics and computational biology roles in the United States — biotech hubs, pharma and academic medical centres.",
     lambda j: j.get("geo") == "USA", "geo=USA"),
    ("remote", "Region", "🌐 Remote", "<em>Remote</em> bioinformatics jobs",
     "Offers that state remote work in the location or description. Check the listing for the countries an employer can hire in.",
     lambda j: j.get("geo") == "Remote", "geo=Remote"),
    ("warszawa", "City", "Warszawa", "Bioinformatics jobs in <em>Warszawa</em>",
     "Offers in Warsaw — the biggest cluster of pharma and CRO data teams in Poland (biostatistics, clinical data science, RWE, bioinformatics).",
     city_match("warszawa"), "q=Warsaw"),
    ("krakow", "City", "Kraków", "Bioinformatics jobs in <em>Kraków</em>",
     "Offers in Kraków — drug-discovery companies, life-science IT and research institutes.",
     city_match("krakow"), "q=Krak"),
    ("wroclaw", "City", "Wrocław", "Bioinformatics jobs in <em>Wrocław</em>",
     "Offers in Wrocław — biotech, research institutes and life-science software teams.",
     city_match("wroclaw"), "q=Wroc"),
    ("poznan", "City", "Poznań", "Bioinformatics jobs in <em>Poznań</em>",
     "Offers in Poznań — research institutes, universities and life-science companies.",
     city_match("poznan"), "q=Pozna"),
    ("trojmiasto", "City", "Trójmiasto", "Bioinformatics jobs in <em>Gdańsk, Gdynia &amp; Sopot</em>",
     "Offers in the Tri-City area — biotech, diagnostics and university research.",
     city_match("trojmiasto"), "q=Gda"),
    ("lodz", "City", "Łódź", "Bioinformatics jobs in <em>Łódź</em>",
     "Offers in Łódź — biotech, pharma services and universities.",
     city_match("lodz"), "q=d%C5%BA"),
    ("pharma", "Sector", "Pharma & CRO", "Bioinformatics jobs in <em>pharma &amp; CROs</em>",
     "Computational roles at large pharmaceutical companies and contract research organisations: biostatistics, statistical programming, clinical data science, RWE and bioinformatics.",
     is_pharma, "cat=Pharma%2FBiotech"),
    ("biotech", "Sector", "Biotech & industry", "Bioinformatics jobs in <em>biotech</em>",
     "Industry roles outside big pharma — biotech, genomics and sequencing companies, AI drug discovery and life-science software.",
     lambda j: j.get("category") == "Pharma/Biotech" and not is_pharma(j), "cat=Pharma%2FBiotech"),
    ("startups", "Sector", "Startups", "Bioinformatics jobs at <em>startups</em>",
     "Offers from early-stage companies (seed, Series A/B, stealth).",
     lambda j: j.get("category") == "Startup", "cat=Startup"),
    ("academia", "Sector", "Academia", "Academic bioinformatics jobs",
     "Universities and research institutes: research software engineers, staff scientists, core facilities, lecturers and PhD positions.",
     lambda j: j.get("category") == "Academia", "cat=Academia"),
    ("clinical", "Sector", "Clinical", "<em>Clinical</em> bioinformatics &amp; data jobs",
     "Clinical genomics, clinical data science, biostatistics for trials and diagnostics labs.",
     lambda j: j.get("category") == "Clinical", "cat=Clinical"),
    ("internships", "Level", "Internships", "Bioinformatics <em>internships</em>",
     "Internships, placements and student positions. Only open offers are listed — recurring programmes appear when they open.",
     lambda j: j.get("seniority") == "Intern", "sen=Intern"),
    ("entry-level", "Level", "Entry level", "<em>Entry-level</em> bioinformatics jobs",
     "Junior roles and internships — good first steps after a degree or a career switch.",
     lambda j: j.get("seniority") in ("Intern", "Junior"), "sen=Junior"),
    ("postdoc", "Level", "PostDoc", "Bioinformatics <em>postdoc</em> positions",
     "Postdoctoral positions in computational biology, genomics and biostatistics.",
     lambda j: j.get("seniority") == "PostDoc", "sen=PostDoc"),
    ("mid", "Level", "Mid level", "<em>Mid-level</em> bioinformatics jobs",
     "Scientist / engineer roles without a junior or senior label — usually a few years of experience.",
     lambda j: j.get("seniority") == "Mid", "sen=Mid"),
    ("senior", "Level", "Senior", "<em>Senior</em> bioinformatics jobs",
     "Senior, staff and principal roles in computational biology and data science for life sciences.",
     lambda j: j.get("seniority") == "Senior", "sen=Senior"),
    ("leadership", "Level", "Lead / PI", "Bioinformatics <em>leadership</em> roles",
     "Group leaders, heads of department, directors and principal investigators.",
     lambda j: j.get("seniority") == "PI/Lead", "sen=PI%2FLead"),
]

# skill groups for the skills guide (anything else is a domain)
TOOLS = {"python", "r", "sql", "aws", "gcp", "azure", "docker", "nextflow", "snakemake", "git", "pytorch", "tensorflow",
         "hpc", "sas", "snowflake", "databricks", "kubernetes", "mongodb", "pandas", "scikit-learn", "power bi",
         "power query", "fortran", "gatk", "etl", "mlops", "lims", "alphafold", "vector database", "sparql", "rdf", "owl"}
METHODS = {"machine learning", "deep learning", "ai", "genai", "biostatistics", "statistics", "ngs", "single cell",
           "rna-seq", "wgs", "wes", "variant calling", "gwas", "bayesian", "survival analysis", "multi-omics",
           "spatial transcriptomics", "genome assembly", "protein structure prediction", "molecular dynamics",
           "molecular modeling", "bioinformatics pipeline", "crispr", "rag", "gnn", "knowledge graph", "atac-seq",
           "data engineering", "data visualization", "data modeling", "software engineering", "signal processing"}


# ── HTML PIECES ──────────────────────────────────────────────────────────────
NAV = [("", "Jobs"), ("browse/", "Browse"), ("companies/", "Companies"), ("skills.html", "Skills"),
       ("reports/", "Reports"), ("stats.html", "Stats"), ("archive.html", "Archive")]


def page(title, description, path, body, *, noindex=False, jsonld=None, nav_on=None):
    depth = path.count("/")
    up = "../" * depth
    nav = "".join(f'<a href="{up}{href or "index.html"}"{" class=on" if href == nav_on else ""}>{label}</a>'
                  for href, label in NAV)
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    canonical = BASE_URL + re.sub(r"index\.html$", "", path)
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{robots}
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="BioInfoJobs">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BASE_URL}og-image.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0a0010">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%230a0010'/%3E%3Ctext x='50' y='68' font-size='58' text-anchor='middle'%3E%F0%9F%A7%AC%3C/text%3E%3C/svg%3E">
<script defer src="https://umami-rose-alpha.vercel.app/script.js" data-website-id="0f8a4bbd-7790-437c-912f-15149106ebab"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}assets/pages.css">
{ld}
</head>
<body>
<div id="header">
  <a id="logo" href="{up}index.html"><div id="logo-icon">🧬</div><div id="logo-text"><span>BioInfo</span>Jobs<small>by @biokoderka · weekly</small></div></a>
  <nav class="nav">{nav}</nav>
</div>
<main>
{body}
</main>
<footer>
  🧬 <strong>BioInfoJobs</strong> — curated by <a href="https://instagram.com/biokoderka" target="_blank" rel="noopener">@biokoderka</a> ·
  <a href="https://biokoderka.github.io/bioinfosites/" target="_blank" rel="noopener">BioinfoSites</a> ·
  generated from the weekly refresh · <a href="{up}privacy.html">Privacy &amp; Terms</a><br>
  Offers link to the employer's original posting. Always verify details with the employer.
</footer>
</body>
</html>
"""


def rel_badge(j):
    r = j.get("relevance")
    if r is None:
        return ""
    t = j.get("relevance_tier", "loose")
    label = {k: lab for _c, k, lab in TIERS}[t]
    return f'<span class="rel rel-{t}" title="{label} · relevance {r}/100">🎯 {r}</span>'


def badges(j, as_of):
    out = []
    try:
        if (as_of - date.fromisoformat(seen_date(j))).days <= FRESH_DAYS:
            out.append('<span class="badge b-fresh">✨ Fresh</span>')
    except ValueError:
        pass
    if j.get("salary_text"):
        out.append(f'<span class="badge b-salary">💰 {esc(j["salary_text"])}</span>')
    if j.get("geo") == "Remote":
        out.append('<span class="badge b-remote">🌐 Remote</span>')
    elif re.search(r"hybrid", j.get("location") or "", re.I):
        out.append('<span class="badge b-remote">🏠 Hybrid</span>')
    if j.get("employment_type"):
        out.append(f'<span class="badge">{esc(j["employment_type"])}</span>')
    for t in (j.get("tags") or [])[:3]:
        out.append(f'<span class="badge">{esc(t)}</span>')
    return f'<div class="badges">{"".join(out)}</div>' if out else ""


def card(j, as_of, up):
    emp = employer_of(j)
    company = esc(emp or j.get("company"))
    if emp:
        company = f'<a href="{up}companies/{slugify(emp)}.html">{company}</a>'
    when = esc(j.get("date") or "")
    return f"""<div class="card">
  <div class="top"><span>{esc(j.get("source"))}</span><span>{rel_badge(j)} {when}</span></div>
  <a class="t" href="{esc(j.get("url"))}" target="_blank" rel="noopener nofollow">{esc(j.get("title"))} ↗</a>
  <div class="c">{company} · {esc(j.get("seniority") or "")}</div>
  <div class="l">📍 {esc(j.get("location"))}</div>
  {badges(j, as_of)}
</div>"""


def cards(jobs, as_of, up):
    return '<div class="grid">' + "\n".join(card(j, as_of, up) for j in jobs) + "</div>"


def by_relevance(jobs):
    """Most relevant first; newest first among equal scores."""
    newest = sorted(jobs, key=lambda j: j.get("date") or "", reverse=True)
    return sorted(newest, key=lambda j: -(j.get("relevance") or 0))


def split_relevant(jobs):
    good = [j for j in jobs if (j.get("relevance") or 0) >= MIN_REL]
    rest = [j for j in jobs if (j.get("relevance") or 0) < MIN_REL]
    return by_relevance(good), by_relevance(rest)


def job_list(jobs, as_of, up, empty_msg):
    good, rest = split_relevant(jobs)
    if not jobs:
        return f'<p class="note">{empty_msg}</p>'
    out = cards(good, as_of, up) if good else '<p class="note">No offers scored 60+ right now — see the less relevant ones below.</p>'
    if rest:
        out += (f'<details><summary>{len(rest)} less relevant offer{"s" if len(rest) != 1 else ""} '
                f'(relevance below {MIN_REL}) — often generic data roles or lab positions</summary>{cards(rest, as_of, up)}</details>')
    return out


def item_list_ld(name, jobs):
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name, "numberOfItems": len(jobs),
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": j.get("url"), "name": j.get("title")}
                                for i, j in enumerate(jobs[:50]) if (j.get("url") or "#") != "#"]}


def plain(h):
    return re.sub(r"<[^>]+>", "", html.unescape(h))


def tag_counts(jobs):
    """Case-insensitive tag counts, shown under the most common spelling."""
    spell = defaultdict(Counter)
    cnt = Counter()
    for j in jobs:
        for t in set(x.lower() for x in (j.get("tags") or [])):
            cnt[t] += 1
        for t in (j.get("tags") or []):
            spell[t.lower()][t] += 1
    return cnt, {k: v.most_common(1)[0][0] for k, v in spell.items()}


def top_chips(counter, names, n, up=None, link=None):
    items = counter.most_common(n)
    if not items:
        return '<span class="muted">—</span>'
    out = []
    for k, c in items:
        label = esc(names.get(k, k) if names else k)
        if link:
            out.append(f'<a class="chip" href="{link(k)}">{label}<small>{c}</small></a>')
        else:
            out.append(f'<span class="chip">{label}<small>{c}</small></span>')
    return '<div class="chips">' + "".join(out) + "</div>"


def pct(a, b):
    return round(100 * a / b) if b else 0


def bar_table(rows, total, head=("", "Offers", "Share")):
    if not rows:
        return '<p class="muted">—</p>'
    mx = max(c for _k, c in rows) or 1
    body = "".join(f'<tr><td>{esc(k)}</td><td class="num">{c}</td><td class="num">{pct(c, total)}%</td>'
                   f'<td class="barcell"><div class="bar" style="width:{max(2, round(100 * c / mx))}%"></div></td></tr>'
                   for k, c in rows)
    return (f'<table><tr><th>{head[0]}</th><th class="num">{head[1]}</th><th class="num">{head[2]}</th><th></th></tr>'
            f'{body}</table>')


# ── BROWSE PAGES ─────────────────────────────────────────────────────────────
def build_browse(active, everything, as_of, archive_since):
    out = {}
    hub_groups = defaultdict(list)
    for slug, group, label, h1, intro, pred, query in BROWSE:
        now = [j for j in active if pred(j)]
        ever = [j for j in everything if pred(j)]
        good, _rest = split_relevant(now)
        tags, names = tag_counts(good or now)
        emps = Counter(employer_of(j) for j in now if employer_of(j))
        sal = sum(1 for j in now if j.get("salary_text"))
        hub_groups[group].append((slug, label, len(now), len(ever)))
        title_txt = plain(h1)
        if now:
            summary = (f"<strong>{len(now)}</strong> active offer{'s' if len(now) != 1 else ''} right now"
                       f" ({len(good)} scored 60+ for relevance), {sal} with a disclosed salary."
                       f" <strong>{len(ever)}</strong> offers in this category since {archive_since}.")
        else:
            summary = (f"No active offers right now. <strong>{len(ever)}</strong> past offers in this category since "
                       f"{archive_since} are in the archive — the page fills up again with the next weekly refresh.")
        emp_links = lambda e: f"../companies/{slugify(e)}.html"
        body = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / <a href="index.html">Browse</a> / {esc(group)}</div>
<h1>{h1}</h1>
<p class="lead">{esc(intro)}</p>
<p>{summary}</p>
<a class="btn btn-ai" href="../index.html?{query}&amp;rel=0">Open on the board with filters →</a>
<a class="btn btn-ol" href="../match.html">🎯 Find my match</a>
<div class="cols" style="margin-top:22px">
  <div class="panel"><h3>Most requested skills</h3>{top_chips(tags, names, 10)}</div>
  <div class="panel"><h3>Employers hiring</h3>{top_chips(emps, None, 10, link=emp_links)}</div>
</div>
<h2>Current offers</h2>
{job_list(now, as_of, "../", "Nothing open here this week. Browse the <a href='../archive.html'>archive</a> or other categories below.")}
<h2>Other categories</h2>
{{OTHER}}
<p class="note">Updated every Monday from job boards and company career pages. Offers are sorted by relevance (a keyword
model scoring 0–100 how clearly the role is computational biology). Last refresh: {as_of.isoformat()}.</p>"""
        desc = plain(f"{title_txt}: {len(now)} active offers. {intro}")[:300]
        out[slug] = dict(body=body, title=f"{title_txt} — {len(now)} offers | BioInfoJobs", desc=desc,
                         noindex=not now, ld=item_list_ld(title_txt, by_relevance(now)) if now else None)

    others = "".join(
        f'<h3>{esc(g)}</h3><div class="chips">' +
        "".join(f'<a class="chip" href="{s}.html">{esc(lab)}<small>{n}</small></a>' for s, lab, n, _e in items) + "</div>"
        for g, items in hub_groups.items())
    pages = {}
    for slug, p in out.items():
        pages[f"browse/{slug}.html"] = page(p["title"], p["desc"], f"browse/{slug}.html",
                                            p["body"].replace("{OTHER}", others), noindex=p["noindex"],
                                            jsonld=p["ld"], nav_on="browse/")
    hub_rows = "".join(
        f'<div class="panel"><h3>{esc(g)}</h3><table><tr><th></th><th class="num">Active</th><th class="num">All time</th></tr>' +
        "".join(f'<tr><td><a href="{s}.html">{esc(lab)}</a></td><td class="num">{n}</td><td class="num">{e}</td></tr>'
                for s, lab, n, e in items) + "</table></div>"
        for g, items in hub_groups.items())
    hub = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / Browse</div>
<h1>Browse bioinformatics jobs by <em>place, sector &amp; level</em></h1>
<p class="lead">Every category has its own page with current offers, the skills employers ask for and who is hiring.
Counts include all active offers; "all time" counts the permanent archive since {archive_since}.</p>
<div class="cols" style="margin-top:20px">{hub_rows}</div>"""
    pages["browse/index.html"] = page("Browse bioinformatics jobs by region, city, sector and level | BioInfoJobs",
                                      "Bioinformatics and computational biology jobs by region (Poland, Europe, USA, remote), "
                                      "Polish city, sector and career level.", "browse/index.html", hub, nav_on="browse/")
    indexable = ["browse/"] + [f"browse/{s}.html" for s, p in out.items() if not p["noindex"]]
    return pages, indexable


# ── COMPANIES ────────────────────────────────────────────────────────────────
def build_companies(active, everything, as_of):
    groups = defaultdict(list)
    names = defaultdict(Counter)
    for j in everything:
        e = employer_of(j)
        if e:
            groups[slugify(e)].append(j)
            names[slugify(e)][e] += 1
    active_ids = {j["id"] for j in active}
    pages, indexable, rows = {}, [], []
    for slug, jobs in groups.items():
        name = names[slug].most_common(1)[0][0]
        now = [j for j in jobs if j["id"] in active_ids]
        past = sorted([j for j in jobs if j["id"] not in active_ids], key=seen_date, reverse=True)
        tags, tnames = tag_counts(jobs)
        regions = Counter(j.get("geo") for j in jobs)
        levels = Counter(j.get("seniority") for j in jobs)
        sal = sum(1 for j in jobs if j.get("salary_text"))
        first = min((seen_date(j) for j in jobs if seen_date(j)), default="")
        rows.append((name, slug, len(now), len(jobs), regions.most_common(1)[0][0] if regions else ""))
        past_rows = "".join(
            f'<tr><td><a href="{esc(j.get("url"))}" target="_blank" rel="noopener nofollow">{esc(j.get("title"))}</a></td>'
            f'<td>{esc(j.get("location"))}</td><td class="num">{esc(seen_date(j))}</td></tr>' for j in past[:100])
        body = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / <a href="index.html">Companies</a> / {esc(name)}</div>
<h1>{esc(name)} — <em>bioinformatics jobs</em></h1>
<p class="lead">{len(now)} active offer{"s" if len(now) != 1 else ""} · {len(jobs)} computational offer{"s" if len(jobs) != 1 else ""} seen on BioInfoJobs since {esc(first)}{f" · {sal} with salary" if sal else ""}.</p>
<a class="btn btn-ai" href="../index.html?company={quote(name)}&amp;rel=0">Open on the board →</a>
<div class="cols" style="margin-top:22px">
  <div class="panel"><h3>Skills in their offers</h3>{top_chips(tags, tnames, 12)}</div>
  <div class="panel"><h3>Where &amp; which level</h3>{top_chips(regions, None, 5)}{top_chips(levels, None, 6)}</div>
</div>
<h2>Open now</h2>
{job_list(now, as_of, "../", "No open offers this week. Past offers below show what they usually hire for.")}
{f'<h2>Past offers ({len(past)})</h2><table><tr><th>Title</th><th>Location</th><th class="num">First seen</th></tr>{past_rows}</table>' if past else ""}"""
        noindex = not now and len(jobs) < 3
        pages[f"companies/{slug}.html"] = page(
            f"{name} bioinformatics jobs — {len(now)} open | BioInfoJobs",
            f"{name}: {len(now)} open bioinformatics / computational biology offers and {len(past)} past ones, "
            f"with the skills they ask for.", f"companies/{slug}.html", body, noindex=noindex, nav_on="companies/",
            jsonld=item_list_ld(f"{name} jobs", now) if now else None)
        if not noindex:
            indexable.append(f"companies/{slug}.html")
    rows.sort(key=lambda r: (-r[2], -r[3], r[0].lower()))
    table = "".join(
        f'<tr data-n="{esc(n.lower())}"><td><a href="{s}.html">{esc(n)}</a></td><td>{esc(g)}</td>'
        f'<td class="num">{a}</td><td class="num">{t}</td></tr>' for n, s, a, t, g in rows)
    n_active = sum(1 for r in rows if r[2])
    unnamed = sum(1 for j in everything if not employer_of(j))
    body = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / Companies</div>
<h1>Who hires <em>bioinformaticians</em></h1>
<p class="lead">{len(rows)} employers with computational biology offers on BioInfoJobs, {n_active} hiring right now.
Each page shows open offers, past offers and the skills the employer asks for.</p>
<input class="dir-search" id="q" type="search" placeholder="🔍 Filter employers…" aria-label="Filter employers">
<table id="dir"><tr><th>Employer</th><th>Main region</th><th class="num">Open</th><th class="num">All time</th></tr>{table}</table>
<p class="note">{unnamed} offers came from job boards that don't name the employer in their feed (mostly JobRxiv), so they
aren't counted here. They are still on the board and in the archive.</p>
<script>
document.getElementById("q").addEventListener("input", e => {{
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#dir tr[data-n]").forEach(r => r.style.display = r.dataset.n.includes(q) ? "" : "none");
}});
</script>"""
    pages["companies/index.html"] = page(f"Companies hiring bioinformaticians — {n_active} hiring now | BioInfoJobs",
                                         "Directory of employers with bioinformatics and computational biology offers: "
                                         "pharma, CROs, biotech, institutes — open and past offers per company.",
                                         "companies/index.html", body, nav_on="companies/")
    return pages, ["companies/"] + indexable


# ── SKILLS GUIDE ─────────────────────────────────────────────────────────────
def share_by_window(everything, start, end):
    jobs = [j for j in everything if start <= seen_date(j) < end and (j.get("relevance") or 0) >= MIN_REL]
    cnt, _ = tag_counts(jobs)
    return cnt, len(jobs)


def trend_cell(now_share, prev_share, prev_n):
    if prev_n < 20:
        return '<td class="num flat">—</td>'
    d = now_share - prev_share
    if abs(d) < 1.5:
        return f'<td class="num flat">→ {d:+.0f} pp</td>'
    return f'<td class="num {"up" if d > 0 else "down"}">{"↑" if d > 0 else "↓"} {d:+.0f} pp</td>'


def build_skills(active, everything, as_of):
    # Active offers alone are too few (and feeds truncate descriptions), so the ranking
    # uses every relevant offer first seen in the last 90 days – active or already archived.
    d90 = (as_of - timedelta(days=90)).isoformat()
    d180 = (as_of - timedelta(days=180)).isoformat()
    tomorrow = (as_of + timedelta(days=1)).isoformat()
    rel = [j for j in everything if d90 <= seen_date(j) < tomorrow and (j.get("relevance") or 0) >= MIN_REL]
    cnt, names = tag_counts(rel)
    _all_cnt, all_names = tag_counts(everything)
    names = {**all_names, **names}
    recent, n_recent = cnt, len(rel)
    prev, n_prev = share_by_window(everything, d180, d90)

    def table(keys, limit):
        rows = []
        for k in sorted(keys, key=lambda k: -cnt[k])[:limit]:
            if not cnt[k]:
                continue
            s_now = 100 * recent[k] / n_recent if n_recent else 0
            s_prev = 100 * prev[k] / n_prev if n_prev else 0
            rows.append(f'<tr><td><a href="index.html?q={quote(names.get(k, k))}&amp;rel=60">{esc(names.get(k, k))}</a></td>'
                        f'<td class="num">{cnt[k]}</td><td class="num">{pct(cnt[k], len(rel))}%</td>'
                        f'{trend_cell(s_now, s_prev, n_prev)}'
                        f'<td class="barcell"><div class="bar" style="width:{max(2, round(100 * cnt[k] / (cnt.most_common(1)[0][1] or 1)))}%"></div></td></tr>')
        return ('<table><tr><th>Skill</th><th class="num">Offers</th><th class="num">Share</th>'
                '<th class="num" title="Share of offers in the last 90 days vs the 90 days before">Trend</th><th></th></tr>'
                + "".join(rows) + "</table>") if rows else '<p class="muted">—</p>'

    # JobRxiv feed entries are teasers unless the page was read (full_text); other sources give the whole offer
    read_full = sum(1 for j in rel if j.get("full_text") or j.get("source") != "JobRxiv")
    tools = [k for k in cnt if k in TOOLS]
    methods = [k for k in cnt if k in METHODS]
    domains = [k for k in cnt if k not in TOOLS and k not in METHODS]

    def segment(label, pred):
        seg = [j for j in rel if pred(j)]
        c, nm = tag_counts(seg)
        return (f'<div class="panel"><h3>{esc(label)} <span class="muted">· {len(seg)} offers</span></h3>'
                f'{top_chips(c, {**names, **nm}, 8)}</div>')

    body = f"""<div class="crumbs"><a href="index.html">Jobs</a> / Skills</div>
<h1>What employers ask for in <em>bioinformatics</em> offers</h1>
<p class="lead">A live ranking built from the {len(rel)} offers that scored 60+ for relevance and appeared in the last 90 days
(open now or already closed), refreshed every Monday. Trends compare each skill's share with the 90 days before.</p>
<div class="kpis">
  <div class="kpi"><b>{len(rel)}</b><span>relevant offers in the last 90 days</span></div>
  <div class="kpi"><b>{esc(names.get(cnt.most_common(1)[0][0], "—")) if cnt else "—"}</b><span>most requested skill</span></div>
  <div class="kpi"><b>{esc(names.get(max(methods, key=lambda k: cnt[k]), "—")) if methods else "—"}</b><span>top method / data type</span></div>
  <div class="kpi"><b>{esc(names.get(max(tools, key=lambda k: cnt[k]), "—")) if tools else "—"}</b><span>top language / tool</span></div>
</div>
<p class="note">Skills are detected automatically in the offer text. {pct(read_full, len(rel))}% of these offers were read in
full (company career pages, and JobRxiv offers fetched from their own page since November 2026); for the rest only the
feed's first few hundred characters were available — where employers describe the science, not the tools — so languages
and tools are still under-counted. Treat the ranking as relative, not absolute.</p>
<h2>Domains</h2>{table(domains, 25)}
<h2>Methods &amp; data types</h2>{table(methods, 25)}
<h2>Languages &amp; tools</h2>{table(tools, 25)}
<h2>By career level</h2>
<div class="cols">
{segment("Intern & junior", lambda j: j.get("seniority") in ("Intern", "Junior"))}
{segment("Mid level", lambda j: j.get("seniority") == "Mid")}
{segment("Senior & lead", lambda j: j.get("seniority") in ("Senior", "PI/Lead"))}
{segment("PostDoc", lambda j: j.get("seniority") == "PostDoc")}
</div>
<h2>By sector &amp; region</h2>
<div class="cols">
{segment("Pharma & CRO", is_pharma)}
{segment("Biotech & industry", lambda j: j.get("category") == "Pharma/Biotech" and not is_pharma(j))}
{segment("Academia", lambda j: j.get("category") == "Academia")}
{segment("🇵🇱 Poland", lambda j: j.get("geo") == "Poland")}
</div>
<a class="btn btn-ai" href="career.html">🧭 Check your skills with Career Compass →</a>
<a class="btn btn-ol" href="reports/">📈 Quarterly reports</a>
<p class="note">Last refresh: {as_of.isoformat()}. {n_recent} relevant offers first seen in the last 90 days vs {n_prev}
in the 90 days before.</p>"""
    return {"skills.html": page("Bioinformatics skills in demand — live ranking | BioInfoJobs",
                                "Which programming languages, tools, methods and domains bioinformatics employers ask for — "
                                "ranked from live job offers, with 90-day trends.", "skills.html", body, nav_on="skills.html")}


# ── QUARTERLY REPORTS ────────────────────────────────────────────────────────
def quarter_of(d):
    return f"{d[:4]}-q{(int(d[5:7]) - 1) // 3 + 1}"


def quarter_bounds(q):
    y, n = int(q[:4]), int(q[-1])
    start = date(y, 3 * (n - 1) + 1, 1)
    end = date(y + (n == 4), (3 * n) % 12 + 1, 1)
    return start, end


def annual(j):
    """Mid-point of the salary range per year, or None. Uses the period from the text."""
    lo, hi = j.get("salary_min"), j.get("salary_max")
    if not lo and not hi:
        return None
    mid = ((lo or hi) + (hi or lo)) / 2
    period = (j.get("salary_period") or "").lower()
    txt = (j.get("salary_text") or "").lower()
    if period.startswith("h") or "/hr" in txt or "/h" in txt or "hour" in txt:
        mid *= 2080
    elif period.startswith("m") or "/mo" in txt or "month" in txt or "mies" in txt:
        mid *= 12
    return mid if mid >= 1000 else None


def quarter_stats(jobs):
    n = len(jobs)
    rel = [j for j in jobs if (j.get("relevance") or 0) >= MIN_REL]
    tags, names = tag_counts(rel)
    sal = defaultdict(list)
    for j in rel:
        a = annual(j)
        if a and j.get("salary_currency"):
            sal[(j["salary_currency"], j.get("seniority") or "—")].append(a)
            sal[(j["salary_currency"], "All levels")].append(a)
    return {
        "offers": n,
        "relevant": len(rel),
        "employers": len({employer_of(j) for j in jobs if employer_of(j)}),
        "with_salary": sum(1 for j in jobs if j.get("salary_text")),
        "remote": sum(1 for j in jobs if j.get("geo") == "Remote"),
        "poland": sum(1 for j in jobs if j.get("geo") == "Poland"),
        "regions": Counter(j.get("geo") or "Other" for j in jobs).most_common(),
        "sectors": Counter(j.get("category") or "—" for j in jobs).most_common(),
        "levels": Counter(j.get("seniority") or "—" for j in jobs).most_common(),
        "skills": [(names[k], c, round(100 * c / len(rel), 1) if rel else 0) for k, c in tags.most_common(15)],
        "skill_share": {k: 100 * c / len(rel) for k, c in tags.items()} if rel else {},
        "top_employers": Counter(employer_of(j) for j in jobs if employer_of(j)).most_common(12),
        "salaries": {f"{cur} · {lvl}": {"n": len(v), "median": round(statistics.median(v))}
                     for (cur, lvl), v in sal.items() if len(v) >= 3},
        "sources": Counter("JobRxiv" if j.get("source") == "JobRxiv" else "Company boards (Greenhouse, Lever, Workday)"
                           if re.search(r"\((Greenhouse|Lever|Workday)\)$", j.get("source") or "")
                           else "Other boards & manual" for j in jobs).most_common(),
    }


def delta(now, prev, as_pct=False):
    if prev is None:
        return ""
    d = now - prev
    if as_pct:
        cls = "up" if d > 0.5 else "down" if d < -0.5 else "flat"
        return f'<i class="{cls}">{d:+.0f} pp vs previous quarter</i>'
    if not prev:
        return ""
    ch = 100 * d / prev
    cls = "up" if ch > 2 else "down" if ch < -2 else "flat"
    return f'<i class="{cls}">{ch:+.0f}% vs previous quarter</i>'


def build_reports(everything, as_of):
    by_q = defaultdict(list)
    for j in everything:
        d = seen_date(j)
        if re.match(r"\d{4}-\d{2}-\d{2}$", d):
            by_q[quarter_of(d)].append(j)
    # a quarter with a handful of offers (back-dated postings before launch) isn't a report
    quarters = sorted(q for q, v in by_q.items() if len(v) >= 30)
    pages, data_files, indexable, index_rows = {}, {}, [], []
    prev_stats = None
    for i, q in enumerate(quarters):
        jobs = by_q[q]
        st = quarter_stats(jobs)
        start, end = quarter_bounds(q)
        first = min(seen_date(j) for j in jobs)
        partial_start = first > (start + timedelta(days=7)).isoformat()
        in_progress = as_of < end - timedelta(days=1)
        label = f"Q{q[-1]} {q[:4]}"
        coverage = (f"{first if partial_start else start.isoformat()} – "
                    f"{as_of.isoformat() if in_progress else (end - timedelta(days=1)).isoformat()}")
        status = (" · <strong>in progress</strong>, updated weekly" if in_progress else "") + \
                 (" · the board started collecting offers mid-quarter" if partial_start else "")
        p = prev_stats

        def kpi(val, lab, key=None, share_of=None):
            d = ""
            if p and key:
                if share_of:
                    d = delta(pct(st[key], st[share_of]), pct(p[key], p[share_of]), as_pct=True)
                elif not in_progress:
                    d = delta(st[key], p[key])
            return f'<div class="kpi"><b>{val}</b><span>{lab}</span>{d}</div>'

        skill_rows = []
        for name, c, share in st["skills"]:
            prev_share = p["skill_share"].get(name.lower()) if p else None
            ch = "" if prev_share is None else f"{share - prev_share:+.1f} pp"
            cls = "flat" if prev_share is None or abs(share - prev_share) < 1 else "up" if share > prev_share else "down"
            skill_rows.append(f'<tr><td>{esc(name)}</td><td class="num">{c}</td><td class="num">{share:.0f}%</td>'
                              f'<td class="num {cls}">{ch or "new"}</td></tr>')
        risers = []
        if p:
            for k, s in st["skill_share"].items():
                if st["relevant"] >= 30 and p["relevant"] >= 30 and s >= 3:
                    risers.append((s - p["skill_share"].get(k, 0), k))
            risers.sort(reverse=True)
        _c, all_names = tag_counts(jobs)
        rising = ", ".join(f"{esc(all_names.get(k, k))} ({d:+.0f} pp)" for d, k in risers[:3] if d >= 1.5) or "—"
        falling = ", ".join(f"{esc(all_names.get(k, k))} ({d:+.0f} pp)" for d, k in sorted(risers)[:3] if d <= -1.5) or "—"
        sal_rows = "".join(f'<tr><td>{esc(k)}</td><td class="num">{v["n"]}</td><td class="num">{v["median"]:,.0f}</td></tr>'
                           for k, v in sorted(st["salaries"].items()))
        emp_rows = "".join(f'<tr><td><a href="../companies/{slugify(e)}.html">{esc(e)}</a></td><td class="num">{c}</td></tr>'
                           for e, c in st["top_employers"])
        nav = []
        if i > 0:
            nav.append(f'<a class="btn btn-ol" href="{quarters[i - 1]}.html">← Q{quarters[i - 1][-1]} {quarters[i - 1][:4]}</a>')
        if i < len(quarters) - 1:
            nav.append(f'<a class="btn btn-ol" href="{quarters[i + 1]}.html">Q{quarters[i + 1][-1]} {quarters[i + 1][:4]} →</a>')
        body = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / <a href="index.html">Reports</a> / {label}</div>
<h1>Bioinformatics job market — <em>{label}</em></h1>
<p class="lead">Offers first seen on BioInfoJobs between {coverage}{status}.</p>
<div class="kpis">
  {kpi(st["offers"], "new offers", "offers")}
  {kpi(f'{pct(st["relevant"], st["offers"])}%', "scored 60+ for relevance", "relevant", "offers")}
  {kpi(st["employers"], "named employers", "employers")}
  {kpi(f'{pct(st["with_salary"], st["offers"])}%', "disclosed a salary", "with_salary", "offers")}
  {kpi(f'{pct(st["remote"], st["offers"])}%', "remote", "remote", "offers")}
  {kpi(st["poland"], "🇵🇱 in Poland", "poland")}
</div>
{"<p class='note'>Quarter in progress — counts grow every Monday, so the change vs the previous quarter is shown only for shares.</p>" if in_progress and p else ""}
<div class="cols" style="margin-top:14px">
  <div class="panel"><h3>📈 Rising skills</h3><p>{rising}</p></div>
  <div class="panel"><h3>📉 Falling skills</h3><p>{falling}</p></div>
</div>
<h2>Where</h2>{bar_table(st["regions"], st["offers"], ("Region", "Offers", "Share"))}
<h2>Sector</h2>{bar_table(st["sectors"], st["offers"], ("Sector", "Offers", "Share"))}
<h2>Career level</h2>{bar_table(st["levels"], st["offers"], ("Level", "Offers", "Share"))}
<h2>Top skills <span class="muted" style="font-size:13px">· share of the {st["relevant"]} relevant offers</span></h2>
<table><tr><th>Skill</th><th class="num">Offers</th><th class="num">Share</th><th class="num">vs prev. quarter</th></tr>{"".join(skill_rows)}</table>
<div class="cols" style="margin-top:8px">
  <div><h2>Most active employers</h2>{f'<table><tr><th>Employer</th><th class="num">Offers</th></tr>{emp_rows}</table>' if emp_rows else '<p class="muted">—</p>'}</div>
  <div><h2>Salaries</h2>{f'<table><tr><th>Currency · level</th><th class="num">n</th><th class="num">Median / year</th></tr>{sal_rows}</table>' if sal_rows else '<p class="muted">Fewer than 3 offers with a salary in any group.</p>'}
  <p class="note">Mid-point of the advertised range, converted to a yearly amount. Only groups with 3+ offers.</p></div>
</div>
<h2>Method</h2>
<p class="note">Sources this quarter: {", ".join(f"{esc(s)} {pct(c, st['offers'])}%" for s, c in st["sources"])}.
Offers are de-duplicated by URL and title + employer and dated by the day they first appeared on the board. Relevance is a
transparent keyword model (0–100) — skills and salaries are taken only from offers scoring 60+. Job-board feeds often
include only the start of an offer, so skill counts are lower bounds. The archive is permanent, so past quarters can be
re-checked at any time; raw numbers: <a href="{q}.json">{q}.json</a>.</p>
{"".join(nav)}
<a class="btn btn-ai" href="../skills.html">🧠 Live skills ranking</a>"""
        title = f"Bioinformatics job market report {label} | BioInfoJobs"
        desc = (f"{label}: {st['offers']} new bioinformatics offers, {pct(st['with_salary'], st['offers'])}% with salary, "
                f"top skills {', '.join(s for s, _c, _p in st['skills'][:3])}. Regions, sectors, levels and employers.")
        pages[f"reports/{q}.html"] = page(title, desc, f"reports/{q}.html", body, nav_on="reports/")
        indexable.append(f"reports/{q}.html")
        export = {k: v for k, v in st.items() if k != "skill_share"}
        export.update({"quarter": label, "coverage": coverage, "in_progress": in_progress, "generated": as_of.isoformat()})
        data_files[f"reports/{q}.json"] = json.dumps(export, ensure_ascii=False, indent=1)
        index_rows.append((q, label, st, coverage, in_progress))
        prev_stats = st

    rows = "".join(
        f'<tr><td><a href="{q}.html">{label}</a>{" <span class=muted>· in progress</span>" if ip else ""}</td>'
        f'<td>{esc(cov)}</td><td class="num">{st["offers"]}</td><td class="num">{pct(st["with_salary"], st["offers"])}%</td>'
        f'<td>{esc(", ".join(s for s, _c, _p in st["skills"][:3]))}</td></tr>'
        for q, label, st, cov, ip in reversed(index_rows))
    body = f"""<div class="crumbs"><a href="../index.html">Jobs</a> / Reports</div>
<h1>Quarterly <em>bioinformatics job market</em> reports</h1>
<p class="lead">Built from the permanent BioInfoJobs archive: every computational biology offer the board has seen, by quarter —
regions, sectors, levels, skills, employers and salaries.</p>
<table><tr><th>Quarter</th><th>Coverage</th><th class="num">Offers</th><th class="num">With salary</th><th>Top skills</th></tr>{rows}</table>
<a class="btn btn-ai" href="../skills.html">🧠 Live skills ranking</a>"""
    pages["reports/index.html"] = page("Bioinformatics job market reports by quarter | BioInfoJobs",
                                       "Quarterly reports on the bioinformatics and computational biology job market: "
                                       "offers, skills, employers, salaries.", "reports/index.html", body, nav_on="reports/")
    return pages, data_files, ["reports/"] + indexable


# ── SITEMAP ──────────────────────────────────────────────────────────────────
def sitemap(paths, as_of):
    urls = [(p, f, pr) for p, f, pr in STATIC_PAGES]
    for p in paths:
        pr = "0.7" if p in ("browse/", "companies/", "skills.html", "reports/") else "0.5"
        urls.append((p, "weekly", pr))
    body = "\n".join(f"  <url><loc>{BASE_URL}{p}</loc><lastmod>{as_of.isoformat()}</lastmod>"
                     f"<changefreq>{f}</changefreq><priority>{pr}</priority></url>" for p, f, pr in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


# ── MAIN ─────────────────────────────────────────────────────────────────────
def write(rel_path, text, written):
    path = DOCS / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    written.add(path)


def main():
    data = load(JOBS_PATH)
    arch = load(ARCHIVE_PATH)
    if not data.get("jobs"):
        print("⚠ docs/jobs.json has no jobs — nothing to build")
        return
    for j in data["jobs"] + arch.get("jobs", []):
        enrich(j)
    changed = save_if_changed(JOBS_PATH, data, compact=False) | save_if_changed(ARCHIVE_PATH, arch, compact=True)

    as_of = date.fromisoformat((data.get("updated") or date.today().isoformat())[:10])
    active = [j for j in data["jobs"] if not j.get("archived")]
    everything = data["jobs"] + arch.get("jobs", [])
    since_dates = sorted(seen_date(j) for j in everything if seen_date(j) >= "2026-05")
    archive_since = date.fromisoformat(since_dates[0]).strftime("%B %Y") if since_dates else "launch"

    pages, files, indexable = {}, {}, []
    for build in (lambda: build_browse(active, everything, as_of, archive_since),
                  lambda: build_companies(active, everything, as_of)):
        p, idx = build()
        pages.update(p)
        indexable += idx
    pages.update(build_skills(active, everything, as_of))
    indexable.append("skills.html")
    p, f, idx = build_reports(everything, as_of)
    pages.update(p)
    files.update(f)
    indexable += idx

    written = set()
    for rel_path, text in {**pages, **files}.items():
        write(rel_path, text, written)
    write("sitemap.xml", sitemap(indexable, as_of), written)

    # employer pages that no longer exist (an employer renamed) – remove the stale file
    for folder in ("browse", "companies", "reports"):
        for old in (DOCS / folder).glob("*"):
            if old.is_file() and old not in written:
                old.unlink()

    print(f"✅ {len(pages)} pages, {len(files)} data files, sitemap with {len(indexable) + len(STATIC_PAGES)} URLs"
          f"{' · enriched jobs.json/archive.json' if changed else ''}")


if __name__ == "__main__":
    main()
