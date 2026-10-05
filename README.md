# 🧬 BioInfoJobs

> **Weekly bioinformatics & computational biology job board** by [@biokoderka](https://instagram.com/biokoderka)

A free, open-source job board for bioinformaticians. Offers are collected automatically every week from job feeds and company career boards, plus hand-picked and community-submitted offers. Filter by region (Poland / Europe / USA / Remote) and sector, or use the two free tools: **Job Match** and **Career Compass**.

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
| `refresh.yml` | Mondays 08:00 UTC (+ manual) | runs `scripts/fetch_jobs.py`, commits both JSON files |
| `add-job.yml` | manual | adds a job, or takes one down by id (see [ADMIN_SETUP.md](ADMIN_SETUP.md)) |

## Local development

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_jobs.py          # scrape + update docs/jobs.json and docs/archive.json
python scripts/add_job.py --help      # add / archive a manual job
python -m http.server -d docs 8000    # then open http://localhost:8000
```

Pages fetch the JSON files, so open them through a local server, not as `file://`.

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch_jobs.py` | scrapers, tagging (tech tags, geo, sector, seniority, salary), archive rules |
| `add_job.py` | add a manual job / archive a job by id |
| `cleanup_jobs.py` | one-off data cleanup (Oct 2026) — safe to re-run |
| `backfill_tech_tags.py`, `retag_expand.py` | one-off re-tagging of existing offers |
| `search_log_apps_script.gs` | optional anonymous search log for Job Match (Google Sheets) |

## License

MIT — free to use, fork, and modify.
