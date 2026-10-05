#!/usr/bin/env python3
"""
Add a manual / community job to docs/jobs.json — or archive one by id.

Used by the "Add job" GitHub Action (Actions → Add job → Run workflow), and
can be run locally as well:

  python3 scripts/add_job.py --json '{"title": "...", "company": "...", "url": "...", ...}'
  python3 scripts/add_job.py --title "Bioinformatician" --company "Ardigen" \
      --url "https://..." --location "Kraków, Poland" --deadline 2026-11-30
  python3 scripts/add_job.py --archive manual_ab12cd34ef

Manual jobs stay active until their deadline (or 60 days without one) —
the weekly scraper never archives them for "not being found".
"""
import argparse, hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_jobs as fj

GEOS = {"Poland", "Europe", "USA", "Remote", "Other"}
CATEGORIES = {"Academia", "Pharma/Biotech", "Clinical", "Startup", "Government/Public"}
SENIORITIES = {"Intern", "Junior", "Mid", "Senior", "PostDoc", "PI/Lead"}

# keys accepted in --json (the Formspree e-mail block uses the same names)
ALIASES = {"listing_url": "url", "region": "geo", "sector": "category",
           "desc": "description", "submitted_by": "submitter"}


def build_job(d):
    d = {ALIASES.get(k, k): (v.strip() if isinstance(v, str) else v) for k, v in d.items()}
    for k in ("title", "company", "url"):
        if not d.get(k):
            sys.exit(f"❌ Missing required field: {k}")
    title, company = fj.strip_html(d["title"]), fj.strip_html(d["company"])
    location = fj.clean_location(d.get("location"))
    desc = fj.strip_html(d.get("description", ""))[:800]
    deadline = d.get("deadline") or None
    if deadline in ("no deadline", "none", ""):
        deadline = None

    geo = d.get("geo") if d.get("geo") in GEOS else fj.detect_geo(title, location, desc)
    cat = d.get("category") if d.get("category") in CATEGORIES else fj.detect_category(title, company, desc)
    sen = d.get("seniority") if d.get("seniority") in SENIORITIES else fj.detect_seniority(title)
    sal = fj.extract_salary(desc)

    return {
        "id": "manual_" + hashlib.md5(f"{title}{company}".encode()).hexdigest()[:10],
        "title": title, "company": company, "location": location,
        "source": d.get("source") or "Community submission",
        "date": fj.today(), "first_seen": fj.today(),
        "url": d["url"], "description": desc,
        "geo": geo, "category": cat, "seniority": sen,
        "tags": fj.extract_tech_tags(f"{title} {desc}"),
        "salary_min": sal["salary_min"], "salary_max": sal["salary_max"],
        "salary_currency": sal["salary_currency"], "salary_text": sal["salary_text"],
        "summary": None, "manually_added": True, "deadline": deadline,
        **({"submitted_by": d["submitter"]} if d.get("submitter") and d["submitter"] != "anonymous" else {}),
    }


def load():
    return json.loads(fj.JOBS_PATH.read_text(encoding="utf-8"))


def save(data, archived_extra=None):
    archive = []
    if fj.ARCHIVE_PATH.exists():
        archive = json.loads(fj.ARCHIVE_PATH.read_text(encoding="utf-8")).get("jobs", [])
    if archived_extra:
        archive = archived_extra + archive
    fj.write_outputs(data["jobs"], archive, data.get("sources", {}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--archive", help="id of a job to move to the archive")
    for f in ("title", "company", "url", "location", "deadline", "description",
              "geo", "category", "seniority", "source"):
        ap.add_argument(f"--{f}")
    a = ap.parse_args()
    data = load()

    if a.archive:
        hit = [j for j in data["jobs"] if j["id"] == a.archive]
        if not hit:
            sys.exit(f"❌ No active job with id {a.archive}")
        data["jobs"] = [j for j in data["jobs"] if j["id"] != a.archive]
        save(data, [fj.archive(hit[0], "manual")])
        print(f"📦 Archived: {hit[0]['title']} @ {hit[0]['company']}")
        return

    fields = json.loads(a.json) if a.json else {}
    for f in ("title", "company", "url", "location", "deadline", "description",
              "geo", "category", "seniority", "source"):
        if getattr(a, f):
            fields[f] = getattr(a, f)
    job = build_job(fields)

    if job["deadline"] and job["deadline"] < fj.today():
        sys.exit(f"❌ Deadline {job['deadline']} has already passed — not adding.")
    uk = fj.url_key(job["url"])
    for j in data["jobs"]:
        if j["id"] == job["id"] or (uk and fj.url_key(j.get("url")) == uk):
            sys.exit(f"ℹ Already on the board: {j['title']} @ {j['company']} ({j['id']})")

    data["jobs"].insert(0, job)
    data.setdefault("sources", {})["manual"] = sum(1 for j in data["jobs"] if j.get("manually_added"))
    save(data)
    print(f"✅ Added: {job['title']} @ {job['company']} · {job['geo']} · id {job['id']}"
          + (f" · until {job['deadline']}" if job["deadline"] else " · 60 days (no deadline)"))


if __name__ == "__main__":
    main()
