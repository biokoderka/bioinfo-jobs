#!/usr/bin/env python3
"""
BioInfoJobs – job fetcher
Sources: RSS feeds + Greenhouse JSON API + Lever JSON API
Run locally: python3 scripts/fetch_jobs.py
"""

import json, re, hashlib, subprocess, sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser, requests


def check_git_up_to_date():
    """
    Bail out if the local branch is behind origin/main. This repo is updated
    by two GitHub Actions (weekly refresh + job approvals) that commit and
    push straight to GitHub, bypassing local checkouts. Running this script
    against a stale local docs/jobs.json silently drops manually-added and
    archived jobs. Skips the check quietly if this isn't a git repo (e.g.
    running inside CI, where checkout is always fresh) or git/network isn't
    available.
    """
    repo_dir = Path(__file__).parent.parent
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo_dir, capture_output=True, check=True, timeout=5,
        )
    except Exception:
        return  # not a git repo (or git unavailable) - nothing to check

    try:
        subprocess.run(["git", "fetch", "origin"], cwd=repo_dir,
                        capture_output=True, check=True, timeout=20)
        behind = subprocess.run(
            ["git", "log", "HEAD..origin/main", "--oneline"],
            cwd=repo_dir, capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
    except Exception as e:
        print(f"⚠️  Could not check git status against origin/main ({e}) — proceeding anyway.")
        return

    if behind:
        print("🛑 Your local branch is behind origin/main:\n")
        print(behind)
        print(
            "\nRunning fetch_jobs.py now would merge fresh listings on top of an "
            "outdated docs/jobs.json and could silently drop manually-added or "
            "archived jobs that only exist on GitHub.\n"
            "Run `git pull origin main` first, then re-run this script."
        )
        sys.exit(1)

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
    ("Enveda Biosciences","enveda"),
    ("Synthego",         "synthego"),
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

def detect_category(title, company, description=""):
    t = (title + " " + company + " " + description).lower()
    if any(k in t for k in ["university","institute","phd","postdoc","post-doc","professor",
                             "faculty","fellow","laboratory of","department of","academic",
                             "research fellow","doctoral"]):
        return "Academia"
    if any(k in t for k in ["nhs","government","ministry","national institute","public health",
                             "agency","federal","ec.europa","euraxess"]):
        return "Government/Public"
    if any(k in t for k in ["clinical","cro ","biostatistic","clinical trial","pharmacovigilance",
                             "regulatory","gmp","gcp","quality assurance"]):
        return "Clinical"
    if any(k in t for k in ["startup","seed","series a","series b","ai-native","stealth"]):
        return "Startup"
    return "Pharma/Biotech"

def detect_seniority(title):
    t = title.lower()
    if any(k in t for k in ["postdoc","post-doc","post doc"]):
        return "PostDoc"
    if any(k in t for k in ["intern","internship","placement student"]):
        return "Intern"
    if any(k in t for k in ["principal investigator"," pi ","group leader","lab head",
                             "head of","director","vp ","vice president","chief"]):
        return "PI/Lead"
    if any(k in t for k in ["senior","sr.","sr ","staff","lead "]):
        return "Senior"
    if any(k in t for k in ["junior","jr.","jr ","entry level","graduate"]):
        return "Junior"
    return "Mid"


def extract_salary(text):
    """
    Parse salary/compensation info from free text.
    Returns dict: {salary_min, salary_max, salary_currency, salary_text} or all None.
    Handles: $120k-$150k, $120,000-$150,000, €50,000-€70,000, 12,000-18,000 PLN, £45k-£55k,
             single values, per-month PLN (gross/netto), and Lever HTML salary blocks.
    """
    if not text:
        return {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_text": None}

    t = re.sub(r'&nbsp;', ' ', text)
    t = re.sub(r'<[^>]+>', ' ', t)  # strip HTML

    def parse_num(s):
        """Turn '340,000' or '340k' or '340' into float."""
        s = s.replace(',', '').replace(' ', '').lower()
        if s.endswith('k'):
            return float(s[:-1]) * 1000
        try:
            return float(s)
        except ValueError:
            return None

    PATTERNS = [
        # $120,000 – $150,000  or  $120k–$150k
        (r'\$\s*([\d,]+(?:\.\d+)?k?)\s*[-–—]\s*\$?\s*([\d,]+(?:\.\d+)?k?)', 'USD'),
        # €50,000 – €70,000
        (r'€\s*([\d,]+(?:\.\d+)?k?)\s*[-–—]\s*€?\s*([\d,]+(?:\.\d+)?k?)', 'EUR'),
        # £45,000 – £55,000
        (r'£\s*([\d,]+(?:\.\d+)?k?)\s*[-–—]\s*£?\s*([\d,]+(?:\.\d+)?k?)', 'GBP'),
        # 12 000 – 18 000 PLN  or  12,000-18,000 PLN/zł
        (r'(\d[\d\s,.]{2,9})\s*[-–—]\s*(\d[\d\s,.]{2,9})\s*(?:PLN|zł|pln|zl)\b', 'PLN'),
        # PLN 12,000 – 18,000
        (r'(?:PLN|zł)\s*(\d[\d\s,.]{2,9})\s*[-–—]\s*(\d[\d\s,.]{2,9})', 'PLN'),
        # 8 000 zł brutto/netto
        (r'(\d[\d\s,.]{2,9})\s*(?:zł|PLN)\s*(?:brutto|netto|gross|net)\b', 'PLN'),
        # Single values: $120,000 or $150k
        (r'\$\s*([\d,]+(?:\.\d+)?k?)', 'USD'),
        (r'€\s*([\d,]+(?:\.\d+)?k?)', 'EUR'),
        (r'£\s*([\d,]+(?:\.\d+)?k?)', 'GBP'),
    ]

    for pat, currency in PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if not m:
            continue
        g = m.groups()
        v1 = parse_num(g[0])
        v2 = parse_num(g[1]) if len(g) > 1 else None

        if v1 is None:
            continue

        # Sanity check: skip implausibly small or large numbers
        for v in [v1, v2]:
            if v and (v < 1000 or v > 5_000_000):
                v1 = v2 = None
                break
        if v1 is None:
            continue

        # Normalize: if both values, min < max
        if v2 and v2 < v1:
            v1, v2 = v2, v1

        # Build human-readable salary_text
        def fmt(v, cur):
            if cur == 'PLN':
                return f"{int(v):,} PLN".replace(',', ' ')
            syms = {'USD': '$', 'EUR': '€', 'GBP': '£'}
            s = syms.get(cur, cur)
            if v >= 1000:
                return f"{s}{int(v):,}"
            return f"{s}{v:.0f}"

        if v2:
            salary_text = f"{fmt(v1, currency)} – {fmt(v2, currency)}"
        else:
            salary_text = fmt(v1, currency)

        # Detect period: look only 40 chars immediately after the salary match
        ctx_after = t[m.end():m.end()+40].lower()
        # Also check 20 chars before (e.g. "B2B 1000-1100 PLN/dzień")
        ctx_before = t[max(0, m.start()-20):m.start()].lower()
        ctx = ctx_before + ctx_after

        has_month = any(k in ctx for k in ["/month", "/miesiąc", "/mies", "miesięcznie", "monthly", "gross/month", "net/month", "/mo"])
        has_year  = any(k in ctx for k in ["/year", "/yr", "/rok", "rocznie", "annual", "per year"])
        has_day   = any(k in ctx for k in ["/dzień", "netto/day", "dziennie", "/day", "per day"]) and not has_month
        has_hour  = any(k in ctx for k in ["/h,", "/h.", " /h", "pln/h"]) and not has_month

        if has_month:
            period = "monthly"
        elif has_year:
            period = "annual"
        elif has_day:
            period = "daily"
        elif has_hour:
            period = "hourly"
        else:
            # Infer from magnitude
            if currency == "PLN" and v1 < 3000:
                period = "daily"
            elif currency in ("USD", "EUR", "GBP") and v1 > 20000:
                period = "annual"
            else:
                period = "monthly" if currency == "PLN" else "annual"

        period_label = {"annual": "/yr", "monthly": "/mo", "daily": "/day", "hourly": "/hr"}.get(period, "")
        salary_text_full = salary_text + period_label

        return {
            "salary_min": int(v1),
            "salary_max": int(v2) if v2 else None,
            "salary_currency": currency,
            "salary_period": period,
            "salary_text": salary_text_full,
        }

    return {"salary_min": None, "salary_max": None, "salary_currency": None, "salary_text": None}


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

def url_key(url):
    """Normalize URL for deduplication — strip tracking params and trailing slashes."""
    if not url or url == "#":
        return None
    url = re.sub(r'[?&](utm_[^&]+|ref=[^&]+|gh_src=[^&]+|lever-origin=[^&]+)', '', url)
    url = url.rstrip("/").lower().split("#")[0]
    return url or None

def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── FETCHERS ──────────────────────────────────────────────────────────────────
def fetch_rss(seen, headers, seen_urls=None):
    if seen_urls is None: seen_urls = set()
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
                # JobRxiv RSS doesn't include location — scrape the job page for it
                if f["name"] == "JobRxiv" and not loc and link != "#":
                    try:
                        rp = requests.get(link, headers=headers, timeout=8)
                        if rp.status_code == 200:
                            m = re.search(r'class="location"\s*>\s*<a[^>]*>([^<]{2,60})</a>', rp.text)
                            if m:
                                loc = m.group(1).strip()
                    except:
                        pass
                if is_excluded(title): continue
                if not is_relevant(title, desc): continue
                uid = job_id(title, f["name"])
                if uid in seen: continue
                ukey = url_key(link)
                if ukey and ukey in seen_urls: continue
                seen.add(uid)
                if ukey: seen_urls.add(ukey)
                sal = extract_salary(desc)
                results.append({"id":uid,"title":title,"company":f["name"],
                    "location":loc or "See listing","source":f["name"],
                    "date":parse_date(e),"url":link,"description":desc[:800],
                    "geo":detect_geo(title,loc,desc),"tags":[],
                    "category":detect_category(title,f["name"],desc),
                    "seniority":detect_seniority(title),
                    "salary_min":sal["salary_min"],"salary_max":sal["salary_max"],
                    "salary_currency":sal["salary_currency"],"salary_text":sal["salary_text"],
                    "summary":None})
                added += 1
            print(f"→ {added} relevant")
        except Exception as e:
            print(f"ERROR: {e}")
    return results

def fetch_greenhouse(seen, headers, seen_urls=None):
    if seen_urls is None: seen_urls = set()
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
                ukey = url_key(link)
                if ukey and ukey in seen_urls: continue
                seen.add(uid)
                if ukey: seen_urls.add(ukey)
                sal = extract_salary(desc)
                results.append({"id":uid,"title":title,"company":company,
                    "location":loc or "See listing","source":f"{company} (Greenhouse)",
                    "date":date,"url":link,"description":desc,
                    "geo":detect_geo(title,loc,desc),"tags":[],
                    "category":detect_category(title,company,desc),
                    "seniority":detect_seniority(title),
                    "salary_min":sal["salary_min"],"salary_max":sal["salary_max"],
                    "salary_currency":sal["salary_currency"],"salary_text":sal["salary_text"],
                    "summary":None})
                added += 1
            if added: print(f"  ✓ {company}: {added} jobs")
        except Exception as e:
            print(f"  ⚠ {company}: {e}")
    return results

def fetch_lever(seen, headers, seen_urls=None):
    if seen_urls is None: seen_urls = set()
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
                ukey = url_key(link)
                if ukey and ukey in seen_urls: continue
                seen.add(uid)
                if ukey: seen_urls.add(ukey)
                # Lever: salary often in raw description HTML before stripping
                sal = extract_salary(job.get("description",""))
                results.append({"id":uid,"title":title,"company":company,
                    "location":loc or "See listing","source":f"{company} (Lever)",
                    "date":today(),"url":link,"description":desc,
                    "geo":detect_geo(title,loc,desc),"tags":[],
                    "category":detect_category(title,company,desc),
                    "seniority":detect_seniority(title),
                    "salary_min":sal["salary_min"],"salary_max":sal["salary_max"],
                    "salary_currency":sal["salary_currency"],"salary_text":sal["salary_text"],
                    "summary":None})
                added += 1
            if added: print(f"  ✓ {company}: {added} jobs")
        except Exception as e:
            print(f"  ⚠ {company}: {e}")
    return results

# ── MAIN ──────────────────────────────────────────────────────────────────────

def fetch_hire_omics(seen, headers, seen_urls=None):
    if seen_urls is None: seen_urls = set()
    """Scrape jobs from hire-omics.com — Webflow job board for bioinformatics/genomics."""
    results = []
    base = "https://hire-omics.com"
    try:
        r = requests.get(f"{base}/jobs", headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"  ⚠ HTTP {r.status_code}")
            return results
        html = r.text
        # Each job is a link: /job-posting/SLUG with title and meta in surrounding text
        # Pattern: <a href="/job-posting/SLUG" ...>...Company...Title...Location...</a>
        links = re.findall(r'href="(/job-posting/[^"]+)"', html)
        links = list(dict.fromkeys(links))
        added = 0
        for path in links[:200]:
            url = base + path
            uid = job_id(path, "HireOmics")
            if uid in seen:
                continue
            try:
                page = requests.get(url, headers=headers, timeout=12)
                if page.status_code != 200:
                    continue
                ptext = page.text
                title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', ptext)
                title = title_m.group(1).strip() if title_m else path.split('/')[-1].replace('-',' ').title()
                if is_excluded(title): continue
                if not is_relevant(title, ptext[:2000]): continue
                # Company name often in a heading near top
                comp_m = re.search(r'<h2[^>]*>([^<]{2,60})</h2>', ptext)
                company = comp_m.group(1).strip() if comp_m else "See listing"
                # Location — look for common patterns
                loc_m = re.search(r'(Remote|Hybrid|Onsite)[,\s]*([A-Za-z,.\s]{0,40})?', ptext)
                loc = loc_m.group(0).strip() if loc_m else ""
                desc_m = re.findall(r'<p[^>]*>(.{40,}?)</p>', ptext, re.DOTALL)
                desc = " ".join(re.sub(r'<[^>]+>',' ',p).strip() for p in desc_m[:3])[:800]
                ukey = url_key(url)
                if ukey and ukey in seen_urls: continue
                seen.add(uid)
                if ukey: seen_urls.add(ukey)
                sal = extract_salary(ptext)  # full page text has better salary context
                results.append({"id":uid,"title":title,"company":company,
                    "location":loc or "See listing","source":"Hire Omics",
                    "date":today(),"url":url,"description":desc,
                    "geo":detect_geo(title,loc,desc),"tags":[],
                    "category":detect_category(title,company,desc),
                    "seniority":detect_seniority(title),
                    "salary_min":sal["salary_min"],"salary_max":sal["salary_max"],
                    "salary_currency":sal["salary_currency"],"salary_text":sal["salary_text"],
                    "summary":None})
                added += 1
            except Exception:
                continue
        print(f"  → {added} relevant")
    except Exception as e:
        print(f"  ERROR: {e}")
    return results

def main():
    print(f"\n🧬 BioInfoJobs Fetcher — {datetime.now(timezone.utc).isoformat()}\n")
    check_git_up_to_date()
    seen = set()       # tracks job IDs (title+company hash)
    seen_urls = set()  # tracks canonical URLs for cross-source dedup
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    print("📡 RSS feeds:")
    rss = fetch_rss(seen, headers, seen_urls)

    print("\n🏢 Greenhouse APIs:")
    gh = fetch_greenhouse(seen, headers, seen_urls)

    print("\n🔧 Lever APIs:")
    lv = fetch_lever(seen, headers, seen_urls)

    print("\n💼 Hire Omics:")
    ho = fetch_hire_omics(seen, headers, seen_urls)

    all_jobs = sorted(rss + gh + lv + ho, key=lambda j: j["date"], reverse=True)

    # Drop jobs older than 60 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    all_jobs = [j for j in all_jobs if j.get("date","0000-00-00") >= cutoff]

    # Load existing jobs.json so nothing freshly fetched gets silently deleted.
    # Anything present before but missing from this run's results is kept
    # and flagged as "archived" instead of being dropped.
    out = Path(__file__).parent.parent / "docs" / "jobs.json"
    existing_jobs = []
    if out.exists():
        try:
            existing = json.loads(out.read_text())
            existing_jobs = existing.get("jobs", [])
        except: pass

    if not all_jobs and not existing_jobs:
        print("No jobs fetched and no existing jobs.json - nothing to write")
        return

    fresh_ids = {j["id"] for j in all_jobs}
    archived_count = 0
    unarchived_count = 0

    for j in existing_jobs:
        if j["id"] in fresh_ids:
            if j.get("archived"):
                unarchived_count += 1
            continue
        if not j.get("archived"):
            archived_count += 1
        j["archived"] = True
        j.setdefault("archived_date", today())
        all_jobs.append(j)

    if archived_count:
        print(f"\nArchived {archived_count} jobs no longer found by scraper (kept, not deleted)")
    if unarchived_count:
        print(f"{unarchived_count} previously archived jobs are active again")

    manual_count = sum(1 for j in all_jobs if j.get("manually_added"))
    if manual_count:
        print(f"{manual_count} manually added jobs present")

    if not all_jobs:
        print("No jobs fetched - keeping existing jobs.json unchanged")
        return

    all_jobs.sort(key=lambda j: j["date"], reverse=True)
    all_jobs.sort(key=lambda j: j.get("archived", False))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(all_jobs),
        "sources": {"rss": len(rss), "greenhouse": len(gh), "lever": len(lv), "hire_omics": len(ho), "manual": manual_count, "archived": archived_count},
        "jobs": all_jobs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {len(all_jobs)} jobs saved → {out}")
    print(f"   RSS: {len(rss)} · Greenhouse: {len(gh)} · Lever: {len(lv)} · Manual: {manual_count} · Archived: {archived_count}")

if __name__ == "__main__":
    main()
