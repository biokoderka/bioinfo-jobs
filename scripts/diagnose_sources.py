#!/usr/bin/env python3
"""
BioInfoJobs – source diagnostics.

Checks every RSS feed and the Euraxess (Poland) search page, and reports
exactly what each one returns: HTTP status, redirects, content type, size,
whether it parses as a feed, how many entries, how many pass the relevance
filter, and the first bytes of the response.

Output:
  * a readable log (stdout)
  * a Markdown table in the GitHub Actions run summary ($GITHUB_STEP_SUMMARY)
  * diag/ folder with the raw response of every source + report.json
    (the workflow uploads it as the "source-diagnostics" artifact)

It never changes jobs.json / archive.json and never fails the workflow.

Run locally:  python3 scripts/diagnose_sources.py
"""

import json, os, re, sys, time
from pathlib import Path

import feedparser, requests

sys.path.insert(0, str(Path(__file__).parent))
import fetch_jobs as fj  # noqa: E402

OUT = Path(os.environ.get("DIAG_DIR", Path(__file__).parent.parent / "diag"))
UA = "BioInfoJobs-fetcher/1.0 (+https://biokoderka.github.io/bioinfo-jobs/privacy.html)"
HEADERS = {"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"}

# The old Euraxess RSS URL is no longer in RSS_FEEDS, but check it once more
# so the report shows why it was replaced.
EXTRA = [{"name": "Euraxess (old RSS URL)", "url": "https://euraxess.ec.europa.eu/jobs/rss"}]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def verdict(r):
    if r.get("error"):
        return "❌ connection error"
    st = r["status"]
    if st in (401, 403):
        return "⛔ blocked (403) – the site refuses our bot"
    if st == 404:
        return "❌ URL does not exist (404)"
    if st == 429:
        return "⏳ rate limited (429)"
    if st >= 500:
        return f"❌ server error ({st})"
    if st != 200:
        return f"⚠ HTTP {st}"
    if r.get("looks_like_html") and not r.get("entries"):
        return "⚠ returns an HTML page, not a feed (captcha/login/changed URL?)"
    if not r.get("entries"):
        return "⚠ valid response but 0 entries"
    if not r.get("relevant"):
        return "⚠ entries found, but none pass the keyword filter"
    return "✅ OK"


def check_feed(feed):
    rec = {"name": feed["name"], "url": feed["url"]}
    t0 = time.time()
    try:
        url = feed["url"] + ("&paged=1" if feed.get("paginate") else "")
        resp = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    except Exception as e:
        rec.update(error=f"{type(e).__name__}: {e}", seconds=round(time.time() - t0, 1))
        rec["verdict"] = verdict(rec)
        return rec, b""
    body = resp.content or b""
    head = body[:600].decode("utf-8", "replace")
    parsed = feedparser.parse(body)
    entries = parsed.entries
    relevant = [e for e in entries
                if fj.is_relevant(fj.strip_html(e.get("title", "")),
                                  fj.strip_html(e.get("summary", "") or e.get("description", "")))
                and not fj.is_excluded(fj.strip_html(e.get("title", "")))]
    rec.update(
        status=resp.status_code,
        final_url=resp.url,
        redirects=[h.headers.get("Location", "") for h in resp.history],
        content_type=resp.headers.get("Content-Type", ""),
        server=resp.headers.get("Server", ""),
        bytes=len(body),
        seconds=round(time.time() - t0, 1),
        feed_ok=not parsed.bozo,
        feed_error=str(parsed.get("bozo_exception", "")) if parsed.bozo else "",
        looks_like_html=bool(re.search(r"<!doctype html|<html", head, re.I)),
        page_title=(re.search(r"<title[^>]*>(.*?)</title>", body[:20000].decode("utf-8", "replace"), re.S | re.I)
                    or [None, ""])[1].strip()[:120] if body else "",
        entries=len(entries),
        relevant=len(relevant),
        first_entry=fj.strip_html(entries[0].get("title", ""))[:120] if entries else "",
        first_relevant=fj.strip_html(relevant[0].get("title", ""))[:120] if relevant else "",
        head=re.sub(r"\s+", " ", head)[:300],
    )
    rec["verdict"] = verdict(rec)
    return rec, body


def check_euraxess():
    rec = {"name": "Euraxess – Poland (new scraper)", "url": fj.EURAXESS_PL_SEARCH}
    try:
        r = requests.get(fj.EURAXESS_PL_SEARCH, headers={**HEADERS, "Accept": "text/html"}, timeout=25)
    except Exception as e:
        rec.update(error=f"{type(e).__name__}: {e}", verdict="❌ connection error")
        return rec, b""
    items = fj.parse_euraxess_list(r.text) if r.status_code == 200 else []
    polish = [i for i in items if re.search(r"\bPoland\b|\bPolska\b", i["text"])]
    rel = [i for i in polish if fj.euraxess_relevant(i["title"], i["field"])]
    count = re.search(r"Search results\s*\(([\d,\s]+)\)", fj.strip_html(r.text))
    rec.update(
        status=r.status_code, final_url=r.url, content_type=r.headers.get("Content-Type", ""),
        bytes=len(r.content), total_results=count.group(1).strip() if count else "?",
        entries=len(items), polish=len(polish), relevant=len(rel),
        parsed_with_date=sum(1 for i in items if i["posted"]),
        parsed_with_deadline=sum(1 for i in items if i["deadline"]),
        parsed_with_field=sum(1 for i in items if i["field"]),
        sample=[{k: i[k] for k in ("title", "url", "posted", "deadline", "location", "field")} for i in items[:3]],
        first_relevant=rel[0]["title"][:120] if rel else "",
    )
    if r.status_code != 200:
        rec["verdict"] = verdict({**rec, "entries": 0})
    elif not items:
        rec["verdict"] = "⚠ page loads, but the parser found no offers (markup changed?)"
    elif len(polish) < len(items):
        rec["verdict"] = f"⚠ country filter not applied? only {len(polish)}/{len(items)} offers are in Poland"
    elif not rel:
        rec["verdict"] = "✅ parser works (no bio/computational offers on page 1 this week)"
    else:
        rec["verdict"] = "✅ OK"
    return rec, r.content


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"\n🩺 BioInfoJobs source diagnostics\n   User-Agent: {UA}\n")
    report = []
    for feed in fj.RSS_FEEDS + EXTRA:
        print(f"→ {feed['name']}", flush=True)
        rec, body = check_feed(feed)
        (OUT / f"{slug(feed['name'])}.txt").write_bytes(body[:400_000])
        report.append(rec)
        for k in ("verdict", "status", "final_url", "content_type", "bytes", "entries", "relevant",
                  "feed_error", "page_title", "first_entry", "error", "head"):
            if rec.get(k) not in (None, "", []):
                print(f"     {k:13} {rec[k]}")
        time.sleep(1)

    print("→ Euraxess – Poland (new scraper)", flush=True)
    rec, body = check_euraxess()
    (OUT / "euraxess-poland.html").write_bytes(body[:2_000_000])
    report.append(rec)
    for k, v in rec.items():
        if k not in ("name", "url"):
            print(f"     {k:20} {v}")

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["## 🩺 Job source diagnostics", "",
             "| Source | Result | HTTP | Entries | Relevant | Details |",
             "|---|---|---|---|---|---|"]
    for r in report:
        det = (r.get("error") or (f"page title: {r['page_title']}" if r.get("page_title") else "")
               or r.get("first_relevant") or r.get("feed_error") or "")
        det = str(det).replace("|", "/")[:90]
        lines.append(f"| {r['name']} | {r.get('verdict','')} | {r.get('status','–')} | "
                     f"{r.get('entries','–')} | {r.get('relevant','–')} | {det} |")
    lines += ["", "Raw responses: download the **source-diagnostics** artifact of this run."]
    md = "\n".join(lines) + "\n"
    print("\n" + md)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(md)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # diagnostics must never break the weekly refresh
        print(f"Diagnostics crashed: {e}")
