#!/usr/bin/env python3
"""
One-off backfill: fills in `tags` for jobs already sitting in docs/jobs.json
that currently have tags == [] (i.e. everything scraped before
extract_tech_tags() existed in fetch_jobs.py).

Run ONCE from inside the repo:
    python3 scripts/backfill_tech_tags.py

Safe by design:
- Only touches jobs where tags is currently empty. Never overwrites tags
  that are already present (e.g. the 85 manually-submitted jobs).
- Writes a timestamped backup of jobs.json before making any changes.
- Uses the exact same extract_tech_tags() logic as fetch_jobs.py (imported
  directly from it), so results stay consistent with what future fetches
  will produce - no separate keyword list to keep in sync.
"""

import json
import shutil
import importlib.util
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).parent.parent
JOBS_PATH = REPO_ROOT / "docs" / "jobs.json"
FETCH_SCRIPT = Path(__file__).parent / "fetch_jobs.py"


def load_extract_tech_tags():
    """Import extract_tech_tags() straight from fetch_jobs.py so this
    backfill can never drift out of sync with the live tagging logic."""
    spec = importlib.util.spec_from_file_location("fetch_jobs", FETCH_SCRIPT)
    fj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fj)
    return fj.extract_tech_tags


def main():
    if not JOBS_PATH.exists():
        print(f"🛑 Could not find {JOBS_PATH}. Run this from inside the repo, "
              f"or place it in scripts/ next to fetch_jobs.py.")
        return
    if not FETCH_SCRIPT.exists():
        print(f"🛑 Could not find {FETCH_SCRIPT} - this script needs the "
              f"patched fetch_jobs.py (with extract_tech_tags) next to it.")
        return

    extract_tech_tags = load_extract_tech_tags()

    data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])

    updated = 0
    still_empty = 0
    skipped_had_tags = 0

    for j in jobs:
        if j.get("tags"):
            skipped_had_tags += 1
            continue
        text = f"{j.get('title', '')} {j.get('description', '')}"
        new_tags = extract_tech_tags(text)
        if new_tags:
            j["tags"] = new_tags
            updated += 1
        else:
            still_empty += 1

    print(f"Jobs already tagged (untouched): {skipped_had_tags}")
    print(f"Jobs newly tagged:               {updated}")
    print(f"Jobs still empty (no keyword hit): {still_empty}")

    if updated == 0:
        print("\nNothing to write - no changes made.")
        return

    backup_path = JOBS_PATH.with_suffix(
        f".backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    shutil.copy2(JOBS_PATH, backup_path)
    print(f"\n📦 Backup saved to {backup_path.name}")

    JOBS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ Wrote updated tags → {JOBS_PATH}")


if __name__ == "__main__":
    main()
