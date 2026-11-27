# 🧬 BioInfoJobs

> **Weekly bioinformatics & computational biology job board** by [@biokoderka](https://instagram.com/biokoderka)

A free job board for bioinformaticians with a public repository (no open-source license is granted unless stated). Offers are collected automatically every week from job feeds and company career boards, plus hand-picked and community-submitted offers. Filter by region (Poland / Europe / USA / Remote) and sector, or use the two free tools: **Job Match** and **Career Compass**.

🌐 **Live:** https://biokoderka.github.io/bioinfo-jobs · part of [BioinfoSites](https://biokoderka.github.io/bioinfosites/)

---

## Pages

| Page | What it does |
|------|--------------|
| `index.html` | The board — search, filters, salary info, job details |
| `match.html` | **Job Match** — pick your skills & interests, get matching offers + advice |
| `career.html` | **Career Compass** — skills self-assessment against live market data |
| `stats.html` | Market statistics (regions, sectors, skills, salaries) |
| `archive.html` | All past offers — the archive is permanent |
| `browse/` | *generated* — landing pages per region, Polish city, sector and level (SEO) |
| `companies/` | *generated* — employer directory + one page per employer (open & past offers, skills) |
| `skills.html` | *generated* — skills employers ask for, with 90-day trends |
| `reports/` | *generated* — quarterly job-market reports (+ `.json` with the raw numbers) |
| `job/` | *generated* — one page per offer. Open offers with the full text, a named employer and a known country carry **JobPosting** markup (Google for Jobs) and go into the sitemap; others are `noindex`. Closed offers keep a "closed" page without markup for 90 days |
| `descriptions.json` | full offer texts `{id: text}` for active offers, written by `fetch_jobs.py` (kept out of `jobs.json` so the board stays light) |
| `submit.html` | Submit a job (reviewed before publishing) |

## Where the jobs come from

| Source | How |
|--------|-----|
| [JobRxiv](https://jobrxiv.org) | RSS (most listings) |
| Company career boards — 10x Genomics, Recursion, Altos Labs, Flatiron, Beam, … | Greenhouse & Lever APIs, **computational roles only** |
| [Hire Omics](https://hire-omics.com) | Omics job board |
| Hand-picked (LinkedIn, Polish companies, institutes) & community submissions | `Add job` GitHub Action |

Other feeds (Nature Careers, jobs.ac.uk, EMBL, Euraxess…) are configured in `scripts/fetch_jobs.py` but often block requests from GitHub Actions, so they contribute only occasionally.

## Data files

| File | Contents |
|------|----------|
| `docs/jobs.json` | **Active** offers — loaded by every page |
| `docs/archive.json` | All archived offers — never deleted |

### Derived fields (`scripts/enrich.py`)

| Field | Meaning |
|-------|---------|
| `relevance` | 0–100, how clearly the offer is a computational-biology role — a transparent keyword model on title, description and tags (weights documented in the file) |
| `relevance_tier` | `high` (80–100) · `relevant` (60–79) · `loose` (< 60). The board hides `loose` offers by default ("All" shows them) |
| `employment_type` | `Full-time` / `Part-time` / `Contract` — only when the offer says so |
| `employer` | the real employer; missing when a job board doesn't name it |
| `full_text` | `true` when a JobRxiv offer was read from its own page (the feed only has a teaser). Tags, location and employer then come from the full offer; the page is fetched once and reused on later runs (max `JOBRXIV_MAX_PAGES` new pages per run, 0.5 s apart) |

The board also shows **Fresh** (first seen in the last 7 days), **salary**, **Remote/Hybrid** badges, and lets visitors
**save offers** (stored in their browser only). Filters live in the URL, e.g. `index.html?geo=Poland&sen=Junior&rel=0`.

### When does an offer get archived?

- a scraped offer is no longer listed by its source → `not_found`
  *(unless the whole source failed in that run — then nothing from it is touched)*
- an RSS offer is older than 60 days → `expired`
- the deadline has passed → `deadline`
- a manual/community offer **without** a deadline: 60 days after it was added → `expired`

Manual offers are never archived just because the scraper didn't "find" them.

## Automation

| Workflow | When | What |
|----------|------|------|
| `refresh.yml` | Mondays 08:00 UTC (+ manual) | runs `scripts/fetch_jobs.py` + `scripts/build_pages.py`, commits the JSON files and generated pages |
| `add-job.yml` | manual | adds a job, or takes one down by id (see [ADMIN_SETUP.md](ADMIN_SETUP.md)) |

## Local development

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_jobs.py          # scrape + update docs/jobs.json and docs/archive.json
python scripts/build_pages.py         # score offers + regenerate browse/, companies/, skills.html, reports/, sitemap
python -m unittest discover tests     # tests (standard library only)
python scripts/add_job.py --help      # add / archive a manual job
python -m http.server -d docs 8000    # then open http://localhost:8000
```

Pages fetch the JSON files, so open them through a local server, not as `file://`.

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch_jobs.py` | scrapers, tagging (tech tags, geo, sector, seniority, salary), archive rules |
| `add_job.py` | add a manual job / archive a job by id |
| `enrich.py` | relevance score, employment type, employer name (used by `fetch_jobs.py` and `build_pages.py`) |
| `build_pages.py` | generates the static pages and `sitemap.xml` from the JSON files — don't edit generated pages by hand |
| `cleanup_jobs.py` | one-off data cleanup (Oct 2026) — safe to re-run |
| `backfill_tech_tags.py`, `retag_expand.py` | one-off re-tagging of existing offers |
| `search_log_apps_script.gs` | optional anonymous search log for Job Match (Google Sheets) |

## License

MIT — free to use, fork, and modify.
