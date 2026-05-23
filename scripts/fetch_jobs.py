#!/usr/bin/env python3
"""
BioInfoJobs – job fetcher
Run locally: python3 scripts/fetch_jobs.py
Then: git add docs/jobs.json && git commit -m "refresh jobs" && git push
"""

import json, re, html, hashlib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser, requests

# ── RSS FEEDS ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {"name": "JobRxiv",                "url": "https://jobrxiv.org/?post_type=job_listing&feed=rss2"},
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

GREENHOUSE_COMPANIES = [
    ("10x Genomics",               "10xgenomics"),
    ("Recursion Pharma",           "recursionpharmaceuticals"),
    ("Tempus",                     "tempus"),
    ("Foundation Medicine",        "foundationmedicine"),
    ("Moderna",                    "modernatx"),
    ("Genentech",                  "genentech"),
    ("Insitro",                    "insitro"),
    ("Relay Therapeutics",         "relaytherapeutics"),
    ("Blueprint Medicines",        "blueprintmedicines"),
    ("Guardant Health",            "guardanthealth"),
    ("Flatiron Health",            "flatironhealth"),
    ("Pacific Biosciences",        "pacificbiosciences"),
    ("Twist Bioscience",           "twistbioscience"),
    ("Chan Zuckerberg Initiative", "chanzuckerberginitiative"),
    ("Allen Institute",            "alleninstitute"),
    ("Jackson Laboratory",         "jacksonlaboratory"),
    ("New York Genome Center",     "newyorkgenomecenter"),
]

LEVER_COMPANIES = [
    ("Benchling", "benchling"),
    ("Natera",    "natera"),
    ("Veracyte",  "veracyte"),
    ("Absci",     "absci"),
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

# ── AUTO-ENRICH RULES ─────────────────────────────────────────────────────────
CATEGORY_RULES = [
    {"cat": "Startup",           "kw": ["internship to hire","startup","start-up","series a","seed round","venture","founding","early stage","genethra","balanx"]},
    {"cat": "Pharma/Biotech",    "kw": ["pharma","biotech","abbvie","illumina","roche","novartis","pfizer","biontech","genentech","merck","lilly","amgen","biogen","regeneron","sanofi","astrazeneca","therapeutics","dmpk","biotransformation","drug discovery","medicines","biopharmaceutical"]},
    {"cat": "Clinical",          "kw": ["clinical trial","hospital","nhs","diagnostic","ehr","fda","ema","regulatory","pathology","radiology","translational research","precision medicine"]},
    {"cat": "Academia",          "kw": ["university","universit","université","institute","postdoc","phd","professor","faculty","laboratory","embl","sanger","broad institute","academic","ulb","heidelberg","cea","cnrs","max planck","wellcome","mrc"]},
    {"cat": "Government/Public", "kw": ["government","public health","nih","agency","ministry","council","erc","horizon europe"]},
]

SENIORITY_RULES = [
    {"level": "Intern",   "kw": ["internship to hire","internship","intern ","trainee","student position"]},
    {"level": "PostDoc",  "kw": ["postdoc","post-doc","postdoctoral","post doctoral"]},
    {"level": "PI/Lead",  "kw": ["principal investigator","group leader","head of","director","chief scientist","staff scientist","vp of"]},
    {"level": "Junior",   "kw": ["junior","graduate","entry level","entry-level","associate scientist","scientist i,","scientist 1,"]},
    {"level": "Senior",   "kw": ["senior scientist","sr. scientist","lead scientist","principal scientist","scientist ii","scientist 2","scientist iii","scientist 3","5+ years","6+ years","7+"]},
    {"level": "Mid",      "kw": ["scientist","analyst","engineer","developer","researcher"]},
]

TECH_TAGS_LIST = [
    "Python","R","Bash","single-cell","scRNA-seq","RNA-seq","WGS","WES","NGS",
    "Nextflow","Snakemake","Docker","AWS","GCP","PyTorch","TensorFlow","AlphaFold",
    "GATK","Seurat","Scanpy","multi-omics","spatial transcriptomics","spatial genomics",
    "machine learning","deep learning","CRISPR","proteomics","metabolomics",
    "biostatistics","GWAS","variant calling","metagenomics","pangenomics",
]

KNOWN_LOCATIONS = [
    "West Point, Pennsylvania","Westport","Cambridge, MA","Boston","San Francisco",
    "San Diego","Seattle","New York","Bethesda","Baltimore","Chicago","Houston","Denver",
    "London","Paris","Berlin","Amsterdam","Brussels","Bruxelles","Heidelberg",
    "Basel","Zurich","Geneva","Stockholm","Copenhagen","Oslo","Helsinki",
    "Vienna","Warsaw","Krakow","Munich","Frankfurt","Oxford","Edinburgh",
    "Barcelona","Madrid","Milan","Rome","Dublin","Lisbon","Prague","Budapest","Leiden",
]

GEO_KW = {
    "Remote":  ["remote","fully remote","work from home","wfh","anywhere","distributed"],
    "Poland":  ["poland","polska","warsaw","wroclaw","krakow","gdansk","poznan","lodz","katowice"],
    "USA":     ["usa","united states","pennsylvania","california","massachusetts","new york",
                "west point","cambridge, ma","boston","san francisco","san diego","seattle",
                "bethesda","baltimore","chicago","houston","denver","atlanta"],
    "Europe":  ["germany","france","spain","italy","netherlands","sweden","denmark","norway",
                "finland","switzerland","austria","belgium","czech","hungary","portugal",
                "uk","united kingdom","england","scotland","ireland","heidelberg","london",
                "paris","berlin","amsterdam","barcelona","zurich","oxford","edinburgh",
                "munich","westport","bruxelles","brussels","liege","leiden","ulb"],
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def clean_html(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_location(title, desc):
    text = title + " " + desc
    # 1. Explicit "Location: ..." field
    m = re.search(r'Location[:\s]+([A-Za-z][A-Za-z\s,\.]{3,50}?)(?:\s*[\(\n]|\.(?:\s|$))', text, re.I)
    if m:
        return m.group(1).strip().rstrip(',.')
    # 2. Known city names
    for loc in KNOWN_LOCATIONS:
        if loc.lower() in text.lower():
            return loc
    # 3. City, Country/State pattern
    m = re.search(r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:Pennsylvania|California|Massachusetts|Germany|France|UK|Ireland|Belgium|Switzerland|Netherlands|Sweden|Denmark|Norway|Finland|Austria|Spain|Italy|Poland|Canada|Australia))', text)
    if m:
        return m.group(1)
    return ""

def detect_geo(title, location, desc):
    text = (title + " " + location + " " + desc).lower()
    for geo, keywords in GEO_KW.items():
        if any(k in text for k in keywords):
            return geo
    return "Other"

def detect_category(title, desc):
    text = (title + " " + desc).lower()
    for rule in CATEGORY_RULES:
        if any(k in text for k in rule["kw"]):
            return rule["cat"]
    return None

def detect_seniority(title, desc):
    text = (title + " " + desc).lower()
    for rule in SENIORITY_RULES:
        if any(k in text for k in rule["kw"]):
            return rule["level"]
    return None

def detect_tags(title, desc):
    text = title + " " + desc
    return [t for t in TECH_TAGS_LIST if t.lower() in text.lower()][:6]

def auto_enrich(job):
    t, d = job.get("title",""), job.get("description","")
    loc = job.get("location","") or extract_location(t, d)
    return {**job,
        "location":  loc or "See listing",
        "geo":       detect_geo(t, loc, d),
        "category":  detect_category(t, d),
        "seniority": detect_seniority(t, d),
        "tags":      detect_tags(t, d),
    }

def is_relevant(title, description):
    text = (title+" "+description).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

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
            resp = requests.get(f["url"], headers=headers, timeout=15)
            print(f"HTTP {resp.status_code}", end=" ", flush=True)
            feed = feedparser.parse(resp.content)
            total = len(feed.entries)
            print(f"({total} entries)", end=" ", flush=True)
            added = 0
            for e in feed.entries:
                title = clean_html(e.get("title",""))
                desc  = clean_html(e.get("summary","") or e.get("description",""))
                link  = e.get("link","#")
                if not is_relevant(title, desc): continue
                uid = job_id(title, f["name"])
                if uid in seen: continue
                seen.add(uid)
                raw = {"id":uid,"title":title,"company":f["name"],
                    "location":"","source":f["name"],
                    "date":parse_date(e),"url":link,"description":desc[:800],
                    "geo":"Other","tags":[],"category":None,"summary":None}
                results.append(auto_enrich(raw))
                added += 1
            print(f"→ {added} relevant")
        except Exception as e:
            print(f"ERROR: {e}")
    return results

def fetch_greenhouse(seen, headers):
    results = []
    for company, slug in GREENHOUSE_COMPANIES:
        try:
            r = requests.get(f"https://boards.greenhouse.io/{slug}/jobs.json", headers=headers, timeout=12)
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
                uid = job_id(title, company)
                if uid in seen: continue
                seen.add(uid)
                raw = {"id":uid,"title":title,"company":company,
                    "location":loc,"source":f"{company} (Greenhouse)",
                    "date":date,"url":link,"description":desc,
                    "geo":"Other","tags":[],"category":None,"summary":None}
                results.append(auto_enrich(raw))
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
                desc  = clean_html(job.get("description",""))[:800]
                if not is_relevant(title, desc): continue
                uid = job_id(title, company)
                if uid in seen: continue
                seen.add(uid)
                raw = {"id":uid,"title":title,"company":company,
                    "location":loc,"source":f"{company} (Lever)",
                    "date":today(),"url":link,"description":desc,
                    "geo":"Other","tags":[],"category":None,"summary":None}
                results.append(auto_enrich(raw))
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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    all_jobs = [j for j in all_jobs if j.get("date","0000-00-00") >= cutoff]

    # Preserve manually added jobs
    out = Path(__file__).parent.parent / "docs" / "jobs.json"
    existing_manual = []
    if out.exists():
        try:
            existing = json.loads(out.read_text())
            existing_manual = [j for j in existing.get("jobs",[]) if j.get("manually_added")]
            if existing_manual:
                print(f"\n✓ Preserving {len(existing_manual)} manually added jobs")
        except: pass

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
        "sources": {"rss":len(rss),"greenhouse":len(gh),"lever":len(lv),"manual":len(existing_manual)},
        "jobs": all_jobs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(all_jobs)} jobs saved → {out}")
    print(f"   RSS: {len(rss)} · Greenhouse: {len(gh)} · Lever: {len(lv)} · Manual: {len(existing_manual)}")

if __name__ == "__main__":
    main()