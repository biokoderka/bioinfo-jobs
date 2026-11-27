"""
Derived fields for every job, computed from what the scrapers already store.

    relevance        0–100, how clearly the offer is a computational-biology role
    relevance_tier   "high" (80–100) · "relevant" (60–79) · "loose" (< 60)
    employment_type  "Full-time" / "Part-time" / "Contract" / None (not stated)
    employer         the real employer, or None when only the job board is known
                     (most JobRxiv offers)

No network, no API keys, no third-party packages: fetch_jobs.py calls
enrich() before writing the JSON files, and build_pages.py re-runs it over
the whole archive so old offers get the same fields. The score is a
transparent keyword model, not an AI – the weights below are the whole story.
"""
import re
import unicodedata
from urllib.parse import urlparse

# ── RELEVANCE ────────────────────────────────────────────────────────────────
# A title like these is a computational-biology role on its own.
TITLE_STRONG = re.compile(
    r"bioinformat|computational (biolog|genom|oncolog|immunolog|neuro|medicine|pathology|drug|chem)"
    r"|\bgenomic|genome (assembl|analy|informat)|\bbiostatist|stat(istical|\.)? (genetic|genomic|programm)"
    r"|cheminformat|systems biolog|biomedical (informatic|data)|clinical data scien|pharmacometric"
    r"|structural bioinformat|multi-?omics (data|analy|integration|model)|\bgwas\b|population genetic"
    r"|phylogenet|quantitative genetic", re.I)
# Strong hint, but also used for bench roles (Proteomics Scientist, Sequencing Lead).
TITLE_CORE = re.compile(
    r"\b(?!econ|ergon)\w*omics\b|\bngs\b|\bsequencing\b|single[- ]cell|precision medicine"
    r"|quantitative (biolog|pharmacolog|systems)|molecular (ai|modell?ing|dynamics)|protein design"
    r"|computational\b|\b(r|sas) programm|clinical programm|\bstatistician|epidemiolog|real[- ]world (evidence|data)|\brwe\b", re.I)
# Computational, but needs life-science context from the rest of the offer.
TITLE_COMPUTE = re.compile(
    r"data (scien|engineer|analy|steward|platform)|machine learning|\bml\b|\bai\b|deep learning"
    r"|statistic|software|programm|developer|\bpipeline|algorithm|model+ing|informatic|quantitative"
    r"|research software|\bmlops\b|\bllm\b|foundation model", re.I)
# Life-science words that turn a compute title into a domain one ("ML Scientist, Drug Discovery").
TITLE_BIO = re.compile(
    r"\bbio|drug|protein|molecul|genet|clinical|health|pharma|cell|rna\b|dna\b|cancer|oncolog|immun"
    r"|neuro|disease|medic|patient|epidemiolog|real[- ]world|\brwe\b|biomarker|translational|life scien", re.I)
# Clearly another field – these slipped through the generic keyword check.
TITLE_OFF = re.compile(
    r"batter|lithium|sodium-ion|electrochem|thermal energy|building|photoswitch|hydrogel|materials (chem|scien)"
    r"|\bfire\b|political|irony|food process|macromolecular chem|metal hydride|catalys|\bnmr\b"
    r"|seismolog|geophys|astrophys|climate|stem expert|ai safety"
    r"|programme management|technology services|equipment application|emg technician|reporting data analyst", re.I)
# Bench / lab roles: biology, but not computational.
TITLE_WETLAB = re.compile(
    r"technician|lab manager|laboratory (manager|engineer|supervisor)|lab supervisor|manufacturing|wet[- ]lab"
    r"|biochemistry|biophysic|assay|in vivo|cell culture|protein production|chemistry\b|chemist\b|wound healing"
    r"|screening|high[- ]throughput|cryo-?em|vaccine|drug product", re.I)

# A bench word next to one of these is still a dry role ("Assay Bioinformatics").
TITLE_DRY = re.compile(r"bioinformat|computational|data|statistic|software|machine learning|\\bai\\b|\\bml\\b|model+ing", re.I)

# Generic title ("Research Associate") but the text says what the role is.
DESC_ROLE = re.compile(
    r"(seek\w*|hiring|recruit\w*|looking for|invite\w* applications for|opening for)\b.{0,80}?"
    r"(bioinformatic|computational (biolog|genomic)|biostatistic|statistical genetic|genomic data|structural bioinformat)",
    re.I)

DESC_BIO_TERMS = [
    r"bioinformat", r"computational biolog", r"genomic", r"\bngs\b|next[- ]generation sequencing",
    r"rna[- ]?seq", r"single[- ]cell|scrna", r"\bwgs\b|whole[- ]genome", r"\bwes\b|whole[- ]exome",
    r"variant (calling|interpretation|annotation)", r"\bgwas\b", r"transcriptom", r"proteomic",
    r"metabolomic", r"multi[- ]?omics", r"\bomics\b", r"epigenom", r"metagenom|microbiome",
    r"spatial (transcriptom|omics|biology)", r"genome assembl", r"phylogen", r"population genetic",
    r"biostatist", r"cheminformat", r"structural bioinformat|protein structure|alphafold",
    r"sequencing data", r"biological data|biomedical data|omics data", r"systems biolog",
    r"statistical genetic", r"pipeline", r"crispr screen", r"drug discovery",
]
DESC_COMPUTE_TERMS = [
    r"\bpython\b", r"(?<![A-Za-z&])R(?![A-Za-z&])", r"\bsql\b", r"\bnextflow\b", r"\bsnakemake\b",
    r"\bdocker\b|\bsingularity\b|\bcontainers?\b", r"\bhpc\b|high[- ]performance computing|cluster",
    r"\baws\b|\bgcp\b|\bazure\b|cloud", r"\bgit\b|github", r"\blinux\b|\bunix\b|\bbash\b",
    r"machine learning|deep learning|\bpytorch\b|tensorflow", r"bioconductor|seurat|scanpy|\bgatk\b",
    r"statistic", r"\bsas\b|\bcdisc\b",
]
_DESC_BIO = [re.compile(p, re.I) for p in DESC_BIO_TERMS]
# "R" must stay case-sensitive, the rest are case-insensitive
_DESC_COMPUTE = [re.compile(p) if p.startswith("(?<![A-Za-z&])R") else re.compile(p, re.I)
                 for p in DESC_COMPUTE_TERMS]

TIERS = [(80, "high", "Highly relevant"), (60, "relevant", "Relevant"), (0, "loose", "Loosely related")]


def relevance_score(job):
    """
    Title decides most of it, the description and tags add evidence:
      core title (Bioinformatician, Biostatistician…)         +80
      omics / sequencing / "computational" title               +65
      compute title with bio context (ML Scientist, Oncology)  +55
      compute title alone (Data Scientist)                     +30
      text names a bioinformatics role ("seeking a … bioinformatician")  +55
      each distinct bio/omics term in the text                  +6  (max +30)
      each distinct computing term in the text                  +3  (max +15)
      off-field title (batteries, chemistry, NMR…)             −45
      bench/lab title without a computational word             −20
    Clamped to 0–100.
    """
    title = job.get("title") or ""
    text = " ".join([title, job.get("description") or "", " ".join(job.get("tags") or [])])

    score = 0
    strong = bool(TITLE_STRONG.search(title))
    core = strong or bool(TITLE_CORE.search(title))
    if strong:
        score += 80
    elif core:
        score += 65
    elif TITLE_COMPUTE.search(title):
        score += 55 if TITLE_BIO.search(title) else 30
    if not strong and DESC_ROLE.search(job.get("description") or ""):
        score += 55

    bio_hits = sum(1 for p in _DESC_BIO if p.search(text))
    compute_hits = sum(1 for p in _DESC_COMPUTE if p.search(text))
    score += min(bio_hits * 6, 30) + min(compute_hits * 3, 15)

    if TITLE_OFF.search(title):
        score -= 45
    elif TITLE_WETLAB.search(title) and not TITLE_DRY.search(title):
        score -= 20
    return max(0, min(100, score))


def relevance_tier(score):
    for cut, key, _label in TIERS:
        if score >= cut:
            return key
    return "loose"


# ── EMPLOYMENT TYPE ──────────────────────────────────────────────────────────
_PART = re.compile(r"\bpart[- ]time\b|\bteilzeit\b|\b\d{2}\s?%\s?(fte|position|employment)", re.I)
_CONTRACT = re.compile(r"\bcontract(or)?\s+(role|position|basis)|\bfixed[- ]term\b|\btemporary\b|\bhourly contract\b"
                       r"|\bfreelance\b|\b\d{1,2}[- ]month (contract|position|appointment)", re.I)
_FULL = re.compile(r"\bfull[- ]time\b|\bvollzeit\b|\bpermanent (role|position|contract)\b|\b100\s?%\s?(fte|position)", re.I)


def employment_type(job):
    """What the offer itself says – None when it doesn't say (no guessing)."""
    text = f"{job.get('title') or ''} {job.get('description') or ''}"
    if _PART.search(text):
        return "Part-time"
    if _CONTRACT.search(text):
        return "Contract"
    if _FULL.search(text):
        return "Full-time"
    return None


# ── EMPLOYER ─────────────────────────────────────────────────────────────────
# "company" holds the job board's name for feed offers – not an employer.
BOARD_NAMES = {
    "jobrxiv", "nature careers", "jobs.ac.uk – bioinfo", "jobs.ac.uk – genomics", "jobs.ac.uk – compbio",
    "euroscience jobs", "eurosciencejobs", "embl jobs", "science careers (aaas)", "bioinformatics.org",
    "iscb careers", "compbiojobs", "hire omics", "euraxess", "the team", "confidential", "see listing", "",
}
# JobRxiv's employer-posted offers carry the employer in the URL:
# /job/columbia-university-irving-medical-center-27778-staff-associate-iii/
_JOBRXIV_SLUG = re.compile(r"/job/([a-z0-9-]+?)-277\d\d-")
_SMALL = {"of", "for", "and", "the", "at", "in", "de", "la", "du", "und", "fur", "für"}
_UPPER = {"nyu", "mit", "ucl", "ucsf", "ucla", "embl", "dkfz", "eth", "epfl", "nih", "nci", "kth", "csiro"}


def _title_case(slug):
    words = slug.replace("-", " ").split()
    out = []
    for i, w in enumerate(words):
        if w in _UPPER:
            out.append(w.upper())
        elif i and w in _SMALL:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def employer(job):
    """Real employer name, or None when we only know which board it came from."""
    if job.get("employer"):
        return job["employer"]
    company = (job.get("company") or "").strip()
    if company.lower() not in BOARD_NAMES:
        return company
    m = _JOBRXIV_SLUG.search(urlparse(job.get("url") or "").path + "-")
    if m:
        return _title_case(m.group(1))
    return None


def slugify(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return t[:80] or "x"


def page_path(job):
    """Offer page under docs/, stable for the offer's lifetime (title + id only)."""
    return f"job/{slugify(job.get('title'))[:60].strip('-')}-{slugify(str(job.get('id')))}.html"


# ── ALL TOGETHER ─────────────────────────────────────────────────────────────
def enrich(job):
    """Adds/refreshes the derived fields in place and returns the job."""
    job["relevance"] = relevance_score(job)
    job["relevance_tier"] = relevance_tier(job["relevance"])
    job["employment_type"] = employment_type(job)
    job["page"] = page_path(job)
    emp = employer(job)
    if emp:
        job["employer"] = emp
    else:
        job.pop("employer", None)
    return job
