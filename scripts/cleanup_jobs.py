#!/usr/bin/env python3
"""
One-off cleanup of the BioInfoJobs data (October 2026). Safe to re-run.

What it does, without scraping anything:
  1. Decodes HTML entities (&amp; &#8211;) and strips the WordPress
     "The post ... appeared first on JobRxiv" footer from titles/descriptions.
  2. Removes Greenhouse/Lever listings whose title isn't computational
     (medicinal chemistry, in-vivo pharmacology, lab associates...).
  3. Replaces work-mode-only locations ("Onsite") with "See listing · Onsite".
  4. Re-runs the archive rules from fetch_jobs.merge(): manual jobs live until
     their deadline, deadline-passed jobs go to the archive, duplicates go away.
     Nothing is deleted from the archive.
  5. Splits the data into docs/jobs.json (active) and docs/archive.json.

Writes a timestamped backup of both files first.
Run from the repo root:  python3 scripts/cleanup_jobs.py
"""
import json, re, shutil, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_jobs as fj

ATS_SUFFIXES = ("(Greenhouse)", "(Lever)")
TRUNCATED_WP_FOOTER = re.compile(r"\s*The post\s+\S.{0,200}$", re.S)


def clean_text(job):
    for k in ("title", "company", "location", "description"):
        if isinstance(job.get(k), str):
            job[k] = fj.strip_html(job[k])
    # descriptions were cut at 800 chars, so the footer is often half there
    if job.get("source") == "JobRxiv" and job.get("description"):
        tail = job["description"][-260:]
        m = TRUNCATED_WP_FOOTER.search(tail)
        if m:
            job["description"] = job["description"][: len(job["description"]) - len(tail) + m.start()].rstrip()
    job["location"] = fj.clean_location(job.get("location"))
    return job


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in (fj.JOBS_PATH, fj.ARCHIVE_PATH):
        if p.exists():
            shutil.copy(p, p.with_name(f"{p.stem}.backup-{stamp}.json"))

    existing = [clean_text(j) for j in fj.load_existing()]
    print(f"Loaded {len(existing)} jobs")

    dropped = [j for j in existing
               if j.get("source", "").endswith(ATS_SUFFIXES) and not fj.is_relevant_ats(j["title"])]
    drop_ids = {j["id"] for j in dropped}
    existing = [j for j in existing if j["id"] not in drop_ids]
    print(f"Removed {len(dropped)} non-computational company-board listings, e.g.:")
    for j in dropped[:8]:
        print(f"   - {j['title']} @ {j['company']}")

    # Jobs that were active after the last real scrape count as "still listed".
    fresh = []
    for j in existing:
        if not j.get("archived") and not j.get("manually_added"):
            j = dict(j)
            if j.get("source") not in ("Hire Omics", "LinkedIn") and not j["source"].endswith(ATS_SUFFIXES):
                j["rss"] = True
            fresh.append(j)

    old_sources = {}
    if fj.JOBS_PATH.exists():
        old_sources = json.loads(fj.JOBS_PATH.read_text(encoding="utf-8")).get("sources", {})

    active, archived = fj.merge(fresh, existing)
    for j in active + archived:
        j.pop("rss", None)
    sources = {k: v for k, v in old_sources.items() if k not in ("archived", "manual")}
    sources["manual"] = sum(1 for j in active if j.get("manually_added"))
    fj.write_outputs(active, archived, sources)


if __name__ == "__main__":
    main()
