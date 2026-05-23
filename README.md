# 🧬 BioInfoJobs

> **Weekly bioinformatics job board**

A free, open-source job board for bioinformaticians. Aggregates offers from Nature Careers, EMBL, EuroScienceJobs, jobs.ac.uk and more. Filters by region (Poland / Europe / USA / Remote) and sector. AI-powered job analysis via Claude.

🌐 **Live site:** `https://biokoderka.github.io/bioinfo-jobs`

---

## Features

- 📡 **Auto-refresh** — GitHub Actions fetches new jobs every Monday at 08:00 UTC
- 📍 **Geo filtering** — Poland / Europe / USA / Remote / Other
- 🏢 **Sector filtering** — Academia / Pharma/Biotech / Clinical / Startup
- 🤖 **AI analysis** — click any job to get Claude's summary, tags, seniority, and relevance score
- 🔍 **Full-text search** — across title, company, location, tags
- 💾 **Local cache** — browser caches results for 72h

## Job sources

| Source | Focus |
|--------|-------|
| [Nature Careers](https://www.nature.com/naturecareers) | Academic & industry science |
| [EMBL Jobs](https://www.embl.org/jobs) | European molecular biology |
| [jobs.ac.uk](https://www.jobs.ac.uk) | UK & international academia |
| [EuroScienceJobs](https://www.eurosciencejobs.com) | European science |
| [ISCB Careers](https://careers.iscb.org) | Computational biology |

## Setup (5 minutes)

### 1. Fork & clone
```bash
git clone https://github.com/YOUR_USERNAME/bioinfo-jobs
cd bioinfo-jobs
```

### 2. Enable GitHub Pages
Go to **Settings → Pages → Source: Deploy from branch → Branch: main → Folder: /docs**

### 3. Enable GitHub Actions
Go to **Actions tab → Enable workflows**

That's it! The site will be live at `https://YOUR_USERNAME.github.io/bioinfo-jobs` and jobs will refresh every Monday automatically.

### Manual refresh
Go to **Actions → Weekly Job Refresh → Run workflow**

### Local development
```bash
pip install -r scripts/requirements.txt
python scripts/fetch_jobs.py   # generates docs/jobs.json
# open docs/index.html in browser
```

## Keyword filtering

Jobs are included if they match any of these keywords in title or description:

`bioinformatics` · `computational biology` · `genomics` · `NGS` · `sequencing` · `proteomics` · `structural biology` · `biostatistics` · `systems biology` · `metagenomics` · `transcriptomics` · `single cell` · `scRNA` · `CRISPR` · `phylogenetics` · `cheminformatics` · `drug discovery` · `variant calling` · `RNA-seq` · `WGS` · `WES` · `multi-omics` · `nanopore`

## Contributing

PRs welcome! Ideas:
- Add more RSS sources
- Improve geo-detection
- Add email digest / Telegram bot
- Add job deduplication across sources

## License

MIT — free to use, fork, and modify.
