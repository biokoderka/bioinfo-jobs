#!/usr/bin/env python3
"""
One-off backfill: recompute `geo` for listings already stored in
docs/jobs.json and docs/archive.json with the current detect_geo().

Why: detect_geo() used to do substring matching over title + location +
description, so 'uk' fired on 'Duke', 'remote' on 'remote sensing', and
'NY office' was not recognised as USA. New scrapes get the fixed logic
automatically; this brings stored listings in line.

Run from inside the repo (pull first):
    python3 scripts/backfill_geo.py            # writes the files
    python3 scripts/backfill_geo.py --dry-run  # only prints what would change

Safe by design:
- Skips manually added jobs and Euraxess jobs (their region was set on purpose).
- Uses detect_geo() imported straight from fetch_jobs.py, so it can never
  drift from the live logic.
- Only the `geo` field is changed; file layout and other fields are untouched.
"""

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FILES = [REPO_ROOT / "docs" / "jobs.json", REPO_ROOT / "docs" / "archive.json"]
FETCH_SCRIPT = Path(__file__).parent / "fetch_jobs.py"


def load_detect_geo():
    spec = importlib.util.spec_from_file_location("fetch_jobs", FETCH_SCRIPT)
    fj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fj)
    return fj.detect_geo


def keep_as_is(job):
    src = (job.get("source") or "").lower()
    return bool(job.get("manually_added")) or src.startswith("euraxess")


def main():
    dry = "--dry-run" in sys.argv
    detect_geo = load_detect_geo()
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        moves = Counter()
        for job in data.get("jobs", []):
            if keep_as_is(job):
                continue
            new = detect_geo(job.get("title", ""), job.get("location", ""), job.get("description", ""))
            if new != job.get("geo"):
                moves[(job.get("geo"), new)] += 1
                job["geo"] = new
        print(f"{path.name}: {sum(moves.values())} of {len(data.get('jobs', []))} listings change region")
        for (old, new), n in moves.most_common():
            print(f"   {old:>7} -> {new:<7} {n}")
        if not dry and moves:
            # same layout fetch_jobs.write_outputs() uses, so the diff stays small
            if path.name == "archive.json":
                text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            else:
                text = json.dumps(data, ensure_ascii=False, indent=1)
            path.write_text(text, encoding="utf-8")
    if dry:
        print("(dry run – nothing written)")


if __name__ == "__main__":
    main()
