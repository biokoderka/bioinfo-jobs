"""Offer pages + JobPosting markup + docs/descriptions.json (no network)."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_pages as bp  # noqa: E402
import fetch_jobs as fj   # noqa: E402

FULL = "We build genomics pipelines.\n\n• Python and R\n• Nextflow </script><b>x</b>\n\n" + "Responsibilities and requirements. " * 30


def base(id_, **kw):
    j = {"id": id_, "title": f"Senior Bioinformatician {id_}", "company": "Roche", "source": "Roche (Workday)",
         "location": "Warsaw, Poland", "geo": "Poland", "category": "Pharma/Biotech", "seniority": "Senior",
         "date": "2026-11-20", "first_seen": "2026-11-20", "url": f"https://example.org/{id_}",
         "description": "genomics NGS python", "tags": ["Python"], "salary_text": "20 000–25 000 PLN/mo",
         "salary_min": 20000, "salary_max": 25000, "salary_currency": "PLN"}
    j.update(kw)
    return j


def ld_of(page_html):
    m = re.search(r'<script type="application/ld\+json">(\{"@context": "https://schema.org/", "@type": "JobPosting".*?)</script>',
                  page_html, re.S)
    return json.loads(m.group(1)) if m else None


class OfferPages(unittest.TestCase):
    def build(self, jobs, archived, texts):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            (docs / "jobs.json").write_text(json.dumps({"updated": "2026-11-23T08:00:00+00:00", "jobs": jobs}))
            (docs / "archive.json").write_text(json.dumps({"jobs": archived}))
            (docs / "descriptions.json").write_text(json.dumps(texts))
            stale = docs / "job" / "old-offer-zzz.html"
            stale.parent.mkdir()
            stale.write_text("old")
            with mock.patch.multiple(bp, DOCS=docs, JOBS_PATH=docs / "jobs.json", ARCHIVE_PATH=docs / "archive.json",
                                     DESCRIPTIONS_PATH=docs / "descriptions.json"):
                bp.main()
            return {str(p.relative_to(docs)): p.read_text() for p in docs.rglob("*.html")} | \
                   {"sitemap.xml": (docs / "sitemap.xml").read_text(), "_stale_exists": str(stale.exists())}

    def test_markup_only_for_complete_open_offers(self):
        jobs = [base("a1"), base("b2"), base("c3", company="JobRxiv", source="JobRxiv", url="https://jobrxiv.org/job/x/")]
        archived = [base("d4", archived=True, archived_date="2026-11-10"),
                    base("e5", archived=True, archived_date="2026-06-01")]
        out = self.build(jobs, archived, {"a1": FULL, "c3": FULL})
        pa, pb, pc = (out[f"job/senior-bioinformatician-{i}-{i}.html"] for i in ("a1", "b2", "c3"))

        ld = ld_of(pa)
        self.assertIsNotNone(ld)
        self.assertEqual(ld["hiringOrganization"]["name"], "Roche")
        self.assertEqual(ld["jobLocation"]["address"], {"@type": "PostalAddress", "addressCountry": "PL", "addressLocality": "Warsaw"})
        self.assertEqual(ld["baseSalary"]["value"]["unitText"], "MONTH")
        self.assertEqual(ld["datePosted"], "2026-11-20")
        self.assertNotIn("</script><b>", pa)                 # text escaped, JSON can't close the script
        self.assertNotIn("noindex", pa)
        self.assertIn("job/senior-bioinformatician-a1-a1.html", out["sitemap.xml"])

        for p in (pb, pc):                                    # teaser only / no named employer
            self.assertIsNone(ld_of(p))
            self.assertIn("noindex", p)
        self.assertNotIn("senior-bioinformatician-b2", out["sitemap.xml"])

        closed = out["job/senior-bioinformatician-d4-d4.html"]
        self.assertIn("This offer has closed", closed)
        self.assertIsNone(ld_of(closed))
        self.assertIn("noindex", closed)
        self.assertNotIn("job/senior-bioinformatician-e5-e5.html", out)   # closed too long ago
        self.assertEqual(out["_stale_exists"], "False")

    def test_cards_link_to_offer_page_and_apply(self):
        out = self.build([base("a1")], [], {"a1": FULL})
        poland = out["browse/poland.html"]
        self.assertIn('href="../job/senior-bioinformatician-a1-a1.html"', poland)
        self.assertIn('href="https://example.org/a1" target="_blank"', poland)


class Descriptions(unittest.TestCase):
    def test_full_texts_kept_for_active_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            (docs / "descriptions.json").write_text(json.dumps({"keep": "earlier full text", "gone": "x"}))
            with mock.patch.object(fj, "DOCS", docs):
                active = [{"id": "keep"}, {"id": "new", "description_full": "fresh <b>text</b>"}, {"id": "none"}]
                archived = [{"id": "gone", "description_full": "y"}]
                n = fj.write_descriptions(active, archived)
            texts = json.loads((docs / "descriptions.json").read_text())
        self.assertEqual(n, 2)
        self.assertEqual(texts, {"keep": "earlier full text", "new": "fresh ‹b›text‹/b›"})
        self.assertNotIn("description_full", active[1])
        self.assertNotIn("description_full", archived[0])

    def test_html_to_text_keeps_structure(self):
        t = fj.html_to_text("&lt;p&gt;Team &amp;amp; science&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;R&lt;/li&gt;&lt;/ul&gt;")
        self.assertEqual(t, "Team & science\n\n• Python\n\n• R")


if __name__ == "__main__":
    unittest.main()
