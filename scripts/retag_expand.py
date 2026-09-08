#!/usr/bin/env python3
"""
One-off: after adding new tag patterns to extract_tech_tags() (broader
domain/role tags like genomics, oncology, omics, microbiome, etc.), this
re-scans every AUTO-SCRAPED job (never manually_added ones) and MERGES any
newly-matching tags into its existing tags list, instead of skipping jobs
that already have tags (which is what backfill_tech_tags.py does, correctly,
to protect manually-curated tags).

Safe by design:
- Never touches jobs where manually_added is true (their tags are hand-picked
  and must not be altered).
- Only ADDS tags found by extract_tech_tags(); never removes anything.
- Writes a timestamped backup of jobs.json before making any changes.

Run once from inside the repo:
    python3 scripts/retag_expand.py
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
    spec = importlib.util.spec_from_file_location("fetch_jobs", FETCH_SCRIPT)
    fj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fj)
    return fj.extract_tech_tags


def main():
    extract_tech_tags = load_extract_tech_tags()

    data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])

    enriched = 0
    unchanged = 0
    skipped_manual = 0
    added_tag_counts = {}

    for j in jobs:
        if j.get("manually_added"):
            skipped_manual += 1
            continue
        text = f"{j.get('title', '')} {j.get('description', '')}"
        found = extract_tech_tags(text)
        existing = j.get("tags") or []
        new_tags = [t for t in found if t not in existing]
        if new_tags:
            j["tags"] = existing + new_tags
            enriched += 1
            for t in new_tags:
                added_tag_counts[t] = added_tag_counts.get(t, 0) + 1
        else:
            unchanged += 1

    print(f"Manually-added jobs skipped (untouched): {skipped_manual}")
    print(f"Jobs enriched with new tags:              {enriched}")
    print(f"Jobs unchanged (no new tags found):       {unchanged}")
    print()
    print("New tags added, by tag:")
    for t, c in sorted(added_tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    if enriched == 0:
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
