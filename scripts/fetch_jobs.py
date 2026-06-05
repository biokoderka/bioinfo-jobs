#!/usr/bin/env python3
"""
BioInfoJobs – job fetcher
Sources: RSS feeds + Greenhouse JSON API + Lever JSON API
Run locally: python3 scripts/fetch_jobs.py
"""

import json, re, hashlib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser, requests

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Confirmed working from local Mac
    {"name": "JobRxiv",                "url": "https://jobrxiv.org/?post_type=job_listing&feed=rss2", "paginate": True},
    # Try these - may work from local IP but not GitHub Actions
    {"name": "Nature Careers",         "url": "https://www.nature.com/naturecareers/rss/latest"},
    {"name": "jobs.ac.uk – Bioinfo",   "url": "https://www.jobs.ac.uk/search/rss?keywords=bioinformatics"},
    {"name": "jobs.ac.uk – Genomics",  "url": "https://www.jobs.ac.uk/search/rss?keywords=genomics"},
    {"name": "jobs.ac.uk – CompBio",   "url": "https://www.jobs.ac.uk/search/rss?keywords=computational+biology"},
    {"name": "EuroScienceJobs",        "url": "https://www.eurosciencejobs.com/rss/all"},
    {"name": "EMBL Jobs",              "url": "https://www.embl.org/jobs/rss"},
    {"name": "Science Careers (AAAS)", "url": "https://jobs.sciencecareers.org/searchjobs/?Keywords=bioinformatics&format=rss"},
    {"name": "Euraxess",               "url": "https://euraxess.ec.europa.eu/jobs/rss"},
    {"name": "Bioinformatics.org",     "url": "https://bioinformatics.org/jobs/rss"},
    {"name": "ISCB Careers",           "url": "https://careers.iscb.org/jobs/rss"},
    {"name": "CompBioJobs",            "url": "https://compbiojobs.com/feed/"},
]

# ── GREENHOUSE — verified working slugs only ──────────────────────────────────
GREENHOUSE_COMPANIES = [
    # ✅ Confirmed working locally (2026-06-05)
    ("10x Genomics",               "10xgenomics"),
    ("Recursion Pharma",           "recursionpharmaceuticals"),
    ("Relay Therapeutics",         "relaytherapeutics"),
    ("Blueprint Medicines",        "blueprintmedicines"),
    ("Flatiron Health",            "flatironhealth"),
    ("Twist Bioscience",           "twistbioscience"),
    ("Chan Zuckerberg Initiative", "chanzuckerberginitiative"),
    ("Altos Labs",                 "altoslabs"),
    ("Prime Medicine",             "primemedicine"),
    ("Beam Therapeutics",          "beamtherapeutics"),
    ("Absci",                      "absci"),
]

LEVER_COMPANIES = [
    ("Benchling",        "benchling"),
    ("Natera",           "natera"),
    ("Veracyte",         "veracyte"),
    ("Absci",            "absci"),
]

# ── KEYWORDS ──────────────────────────────────────────────────────────────────
KEYWORDS = [
    "bioinformatics","bioinformatician","computational biology","computational biologist",
    "genomics","genomicist","NGS","next generation sequencing","sequencing",
    "metagenomics","transcriptomics","proteomics","metabolomics","epigenomics",
    "structural biology","biostatistics","systems biology","cheminformatics",
    "single cell","scRNA","spatial transcriptomics","spatial genomics",
    "CRISPR","phylogenetics","population genetics","GWAS","polygenic",
    "variant calling","genome assembly","genome annotation","pangenomics",
    "RNA-seq","WGS","WES","ChIP-seq","ATAC-seq","multi-omics","nanopore","long read","PacBio",
    "data scientist life science","data scientist biology","data scientist biotech",
    "machine learning biology","machine learning genomics","deep learning biology",
    "AI drug discovery","computational drug discovery","biomedical data","biological data","omics data",
    "drug discovery","target identification","protein structure",
    "clinical bioinformatics","clinical genomics","clinical sequencing",
    "laboratory informatics","LIMS","biological database","sequence analysis",
    "pipeline developer","pipeline engineer","bioinformatics pipeline",
    "genomics engineer","scientific programmer","research software engineer",
    "bioinformatics tools","bioinformatics platform","scientific software",
    "life science data","life sciences data","pharma data scientist",
    "precision medicine","personalized medicine","medical genomics",
    "translational bioinformatics","biomedical informatics",
]

POLAND_KW  = ["poland","polska","warsaw","wroclaw","krakow","gdansk","poznan","lodz","katowice"]
USA_KW     = ["usa","united states","boston","cambridge, ma","new york","san francisco",
              "seattle","bethesda","baltimore","san diego"," ca,"," ny,"," ma,"," wa,"]
REMOTE_KW  = ["remote","fully remote","100% remote","work from home","wfh","anywhere"]
EUROPE_KW  = ["germany","france","spain","italy","netherlands","sweden","denmark","norway",
              "finland","switzerland","austria","belgium","czech","hungary","portugal",
              "uk","united kingdom","england","scotland","ireland","heidelberg","london",
              "paris","berlin","amsterdam","barcelona","zurich","oxford","edinburgh","munich"]

# ── HELPERS ───────────────────────────────────────────────────────────────────
# ── EXCLUDE — non-scientific/non-technical roles ──────────────────────────────
EXCLUDE_TITLE_KEYWORDS = [
    "account manager", "account executive", "sales manager", "sales director",
    "sales executive", "sales specialist", "sales representative",
    "district sales", "inside sales", "field sales",
    "area business manager", "corporate account director", "national account",
    "director of sales", "director, sales",
    "marketing manager", "marketing director", "content marketing",
    "digital marketing", "hcp marketing", "patient marketing",
    "global marketing", "product marketing", "media relations", "brand manager",
    "accountant", "accounting manager", "revenue accounting",
    "payroll", "collections analyst", "staff accountant",
    "fp&a", "fpa manager", "compensation analyst",
    "human resources", "hr business partner", "people and culture",
    "executive assistant", "admin project coordinator", "senior executive assistant",
    "vendor management", "supply chain", "logistics",
    "warehouse", "manufacturing associate", "senior manufacturing", "strategic sourcing",
    "animal care", "veterinarian", "iacuc", "senior technician, instrumentation",
    "laboratory operations associate",
    "counsel", "exempt organizations", "privacy and compliance",
    "regulatory affairs", "ip and strategic", "labeling and promotion", "cmc regulatory",
    "medical affairs", "medical science liaison", "medical information",
    "clinical project manager", "clinical trial manager", "clinical research coordinator",
    "drug product process development", "dmpk", "safety assessment", "toxicology",
    "it support", "end user support", "workday analyst", "procurement",
    "network operations analyst", "senior buyer",
    "investor relations", "public relations", "talent acquisition", "recruiter",
    "general job application", "talent community", "join our",
    "senior director, project team leader", "executive director, asset project",
    "vice president, head of strategy", "head of clinical operations",
    "corporate communications", "product designer",
    "quality assurance manager", "quality control raw", "quality control automation",
    "product quality assurance", "quality control technical",
    "committee member", "communications & events", "health and wellness benefits",
    "solutions manager", "ngs service lab associate",
    "investigative pathologist", "discovery pharmacology", "formulation development",
    "in vivo genomics", "molecular and cell biology",
    "manager, antibody characterization", "project manager, custom antibodies",
    "staff product manager - protein", "commodity business manager",
    "qc associate, data digitalization", "technical lead, instrument software",
    "analytical research and development", "primary pharmacology",
    "communications manager", "enterprise systems analyst, finance",
    "information security, central tech", "cybersecurity engineer",
    "technical program manager, product security", "business systems, central technology",
    "web project manager, digital technology", "director, clinical pharmacology",
    "senior manager, drug product", "associate director, clinical data management",
    "staff engineer, identity & access", "staff mechanical engineer",
    "sr director, customer relationship", "senior manager, supply planning",
    "vice president, compliance", "staff engineer, ai security",
    "director, operations and r&d finance", "director, insights & analytics",
    "field service engineer", "precision medicine executive",
    "scientist, biological sciences", "vice president, business systems",
    "senior technical program manager", "clinical laboratory scientist",
    "staff data scientist, sales analytics", "senior product manager, revenue",
    "associate research scientist, knowledge management",
    "senior research associate, functional genomics & cell biology",
    "sr. program manager", "senior npi mechanical",
    "vp/sr. director, global marketing", "sr global product marketing",
    "research associate ii", "research associate, primary",
    "research scientist, immunology", "scientist, formulation",
    "scientist, in vivo", "scientist i, molecular",
    "senior scientist, discovery", "specialist ii, product quality",
]

def is_excluded(title):
    t = title.lower()
    return any(kw in t for kw in EXCLUDE_TITLE_KEYWORDS)


def detect_geo(title, location, description):
    text = (title+" "+location+" "+description).lower()
    if any(k in text for k in REMOTE_KW): return "Remote"
    if any(k in text for k in POLAND_KW): return "Poland"
    if any(k in text for k in USA_KW):    return "USA"
    if any(k in text for k in EUROPE_KW): return "Europe"
    return "Other"

def detect_seniority(title):
    t = title.lower()
    if any(k in t for k in ["phd", "ph.d", "doctoral", "doctorate"]):
        return "PostDoc" if any(k in t for k in ["postdoc","post-doc","post doc","fellow"]) else "PostDoc"
    if any(k in t for k in ["postdoc","post-doc","post doc","postdoctoral","research fellow"]):
        return "PostDoc"
    if any(k in t for k in ["phd student","phd position","phd candidate","phd fellowship",
                             "phd thesis","doctoral student","doctorate student"]):
        return "PostDoc"
    if any(k in t for k in ["intern","internship","trainee","praktyk","staz","staż"]):
        return "Intern"
    if any(k in t for k in ["junior","entry level","entry-level","graduate","jr."]):
        return "Junior"
    if any(k in t for k in ["principal","staff scientist","staff engineer","distinguished",
                             "vp ","vice president","chief","head of","director"]):
        return "PI/Lead"
    if any(k in t for k in ["senior","sr.","sr ","lead","principal","staff","associate director",
                             "associate professor","assistant professor","professor"]):
        return "Senior"
    if any(k in t for k in ["associate","scientist ii","scientist 2","engineer ii","engineer 2",
                             "analyst ii","analyst 2","mid-level"]):
        return "Mid"
    return "Mid"  # default for unclassified scientist/engineer roles


def is_relevant(title, description):
    text = (title+" "+description).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()

def extract_location(text):
    patterns = [
        r'[Ll]ocation[:\s]+([A-Za-z\s,]+?)(?:\.|,\s*\n|\n|$)',
        r'[Bb]ased in[:\s]+([A-Za-z\s,]+?)(?:\.|,|\n|$)',
        r'([A-Za-z\s]+,\s*(?:USA|UK|Germany|France|Poland|Sweden|Denmark|Netherlands|Switzerland|Austria|Belgium|Spain|Italy|Canada|Australia))',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            loc = match.group(1).strip()
            if 3 < len(loc) < 50:
                return loc
    return ""

def parse_date(entry):
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try: return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
            except: pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def job_id(title, company):
    return hashlib.md5(f"{title}{company}".encode()).hexdigest()[:10]

def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── FETCHERS ──────────────────────────────────────────────────────────────────
def fetch_rss(seen, headers):
    results = []
    for f in RSS_FEEDS:
        print(f"  → {f['name']} ...", end=" ", flush=True)
        try:
            # Paginate for feeds that support it (e.g. JobRxiv WordPress)
            all_entries = []
            if f.get("paginate"):
                for page in range(1, 21):  # max 20 pages = 2000 entries
                    paged_url = f["url"] + f"&paged={page}"
                    resp = requests.get(paged_url, headers=headers, timeout=15)
                    if resp.status_code != 200:
                        break
                    feed_page = feedparser.parse(resp.content)
                    if not feed_page.entries:
                        break
                    new_entries = [e for e in feed_page.entries if e.get("link") not in {x.get("link") for x in all_entries}]
                    if not new_entries:
                        break
                    all_entries.extend(new_entries)
                resp_status = 200
            else:
                resp = requests.get(f["url"], headers=headers, timeout=15)
                resp_status = resp.status_code
                feed_obj = feedparser.parse(resp.content)
                all_entries = feed_obj.entries

            print(f"HTTP {resp_status if not f.get('paginate') else 200}", end=" ", flush=True)
            total = len(all_entries)
            print(f"({total} entries)", end=" ", flush=True)
            added = 0
            for e in all_entries:
                title = strip_html(e.get("title",""))
                desc  = strip_html(e.get("summary","") or e.get("description",""))
                link  = e.get("link","#")
                loc   = strip_html(e.get("location","")) or extract_location(desc)
                if is_excluded(title): continue
                if not is_relevant(title, desc): continue
                uid = job_id(title, f["name"])
                if uid in seen: continue
                seen.add(uid)
                results.append({"id":uid,"title":title,"company":f["name"],
                    "location":loc or "See listing","source":f["name"],
                    "date":parse_date(e),"url":link,"description":desc[:800],
                    "geo":detect_geo(title,loc,desc),"tags":[],"category":None,
                    "seniority":detect_seniority(title),"summary":None})
                added += 1
            print(f"→ {added} relevant")
        except Exception as e:
            print(f"ERROR: {e}")
    return results

def fetch_greenhouse(seen, headers):
    results = []
    for company, slug in GREENHOUSE_COMPANIES:
        try:
            url = f"https://boards.greenhouse.io/{slug}/jobs.json"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
                r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                print(f"  ⚠ {company}: HTTP {r.status_code}")
                continue
            added = 0
            for job in r.json().get("jobs", []):
                title = job.get("title","")
                loc_d = job.get("location",{})
                loc   = loc_d.get("name","") if isinstance(loc_d,dict) else str(loc_d)
                link  = job.get("absolute_url","#")
                upd   = job.get("updated_at","")
                date  = upd[:10] if upd else today()
                depts = ", ".join(d.get("name","") for d in job.get("departments",[]))
                desc  = f"{depts}. {title} at {company}.".strip(". ")
                if is_excluded(title): continue
                if not is_relevant(title, desc): continue
                uid = job_id(title, company)
                if uid in seen: continue
                seen.add(uid)
                results.append({"id":uid,"title":title,"company":company,
                    "location":loc or "See listing","source":f"{company} (Greenhouse)",
                    "date":date,"url":link,"description":desc,
                    "geo":detect_geo(title,loc,desc),"tags":[],"category":None,
                    "seniority":detect_seniority(title),"summary":None})
                added += 1
            if added: print(f"  ✓ {company}: {added} jobs")
        except Exception as e:
            print(f"  ⚠ {company}: {e}")
    return results

def fetch_lever(seen, headers):
    results = []
    for company, slug in LEVER_COMPANIES:
        try:
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", headers=headers, timeout=12)
            if r.status_code != 200: continue
            added = 0
            for job in r.json():
                title = job.get("text","")
                loc   = job.get("categories",{}).get("location","")
                link  = job.get("hostedUrl","#")
                desc  = strip_html(job.get("description",""))[:800]
                if not is_relevant(title, desc): continue
                if is_excluded(title): continue
                if not is_relevant(title, desc): continue
                uid = job_id(title, company)
                if uid in seen: continue
                seen.add(uid)
                results.append({"id":uid,"title":title,"company":company,
                    "location":loc or "See listing","source":f"{company} (Lever)",
                    "date":today(),"url":link,"description":desc,
                    "geo":detect_geo(title,loc,desc),"tags":[],"category":None,
                    "seniority":detect_seniority(title),"summary":None})
                added += 1
            if added: print(f"  ✓ {company}: {added} jobs")
        except Exception as e:
            print(f"  ⚠ {company}: {e}")
    return results

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🧬 BioInfoJobs Fetcher — {datetime.now(timezone.utc).isoformat()}\n")
    seen = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    print("📡 RSS feeds:")
    rss = fetch_rss(seen, headers)

    print("\n🏢 Greenhouse APIs:")
    gh = fetch_greenhouse(seen, headers)

    print("\n🔧 Lever APIs:")
    lv = fetch_lever(seen, headers)

    all_jobs = sorted(rss + gh + lv, key=lambda j: j["date"], reverse=True)

    # Drop jobs older than 60 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    all_jobs = [j for j in all_jobs if j.get("date","0000-00-00") >= cutoff]

    # Load existing jobs to preserve manually approved ones
    out = Path(__file__).parent.parent / "docs" / "jobs.json"
    existing_manual = []
    if out.exists():
        try:
            existing = json.loads(out.read_text())
            existing_manual = [j for j in existing.get("jobs",[]) if j.get("manually_added")]
            if existing_manual:
                print(f"\n✓ Preserving {len(existing_manual)} manually approved jobs")
        except: pass

    # Merge — manual jobs first, then auto-fetched
    seen_ids = {j["id"] for j in all_jobs}
    for j in existing_manual:
        if j["id"] not in seen_ids:
            all_jobs.append(j)

    if not all_jobs:
        print("⚠ No jobs fetched — keeping existing jobs.json unchanged")
        return

    all_jobs.sort(key=lambda j: j["date"], reverse=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(all_jobs),
        "sources": {"rss": len(rss), "greenhouse": len(gh), "lever": len(lv), "manual": len(existing_manual)},
        "jobs": all_jobs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(all_jobs)} jobs saved → {out}")
    print(f"   RSS: {len(rss)} · Greenhouse: {len(gh)} · Lever: {len(lv)} · Manual: {len(existing_manual)}")

if __name__ == "__main__":
    main()
