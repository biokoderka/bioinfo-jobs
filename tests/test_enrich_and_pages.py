"""python -m unittest discover tests   (standard library only)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import enrich as en          # noqa: E402
import build_pages as bp     # noqa: E402


def job(title, desc="", **kw):
    return {"id": title[:10], "title": title, "description": desc, "tags": [], "company": "Acme Bio", **kw}


class Relevance(unittest.TestCase):
    def test_core_titles_are_highly_relevant(self):
        for t in ["Senior Bioinformatician", "Computational Biologist", "Principal Biostatistician",
                  "Statistical Programmer", "Postdoc in Computational Genomics"]:
            self.assertGreaterEqual(en.relevance_score(job(t)), 80, t)

    def test_off_field_and_lab_roles_are_loose(self):
        for t in ["Postdoctoral Researcher in Lithium-Ion Batteries", "PhD student in phosphorus-based photoswitches",
                  "Lab Manager", "Senior Scientist, High Throughput Protein Production"]:
            self.assertLess(en.relevance_score(job(t)), 60, t)

    def test_generic_data_title_needs_life_science_context(self):
        self.assertLess(en.relevance_score(job("Data Scientist")), 60)
        self.assertGreaterEqual(en.relevance_score(job("Machine Learning Scientist, Drug Discovery",
                                                       "single-cell RNA-seq and genomics data, Python")), 60)

    def test_description_naming_the_role_lifts_a_generic_title(self):
        j = job("Staff Associate III", "The lab is seeking a bioinformatics Staff Associate to analyse sequencing data.")
        self.assertGreaterEqual(en.relevance_score(j), 60)

    def test_score_is_clamped_and_tiers(self):
        j = job("Bioinformatics Scientist, Genomics", "bioinformatics genomics NGS RNA-seq single-cell WGS GWAS python R "
                "nextflow docker HPC AWS git linux machine learning statistics", tags=["Python"])
        self.assertEqual(en.relevance_score(j), 100)
        self.assertEqual(en.relevance_tier(85), "high")
        self.assertEqual(en.relevance_tier(60), "relevant")
        self.assertEqual(en.relevance_tier(59), "loose")


class Fields(unittest.TestCase):
    def test_employment_type_only_when_stated(self):
        self.assertEqual(en.employment_type(job("Analyst", "This is a part-time role")), "Part-time")
        self.assertEqual(en.employment_type(job("Analyst", "fixed-term contract for 24 months")), "Contract")
        self.assertEqual(en.employment_type(job("Analyst", "Full-time position")), "Full-time")
        self.assertIsNone(en.employment_type(job("Analyst", "Join our team")))

    def test_employer_from_board_offer(self):
        j = job("Staff Associate III", company="JobRxiv",
                url="https://jobrxiv.org/job/columbia-university-irving-medical-center-27778-staff-associate-iii/")
        self.assertEqual(en.employer(j), "Columbia University Irving Medical Center")
        self.assertIsNone(en.employer(job("Bioinformatician", company="JobRxiv", url="https://jobrxiv.org/job/bioinformatician-21/")))
        self.assertEqual(en.employer(job("x", company="IQVIA")), "IQVIA")

    def test_enrich_is_idempotent(self):
        j = job("Senior Bioinformatician", "genomics", company="JobRxiv", url="https://jobrxiv.org/job/x/")
        once = dict(en.enrich(dict(j)))
        self.assertEqual(once, en.enrich(dict(once)))


class Pages(unittest.TestCase):
    def test_build_writes_pages_and_keeps_data(self):
        jobs = [
            job("Senior Bioinformatician", "genomics NGS python", geo="Poland", location="Wrocław, Poland",
                category="Pharma/Biotech", seniority="Senior", date="2026-11-20", first_seen="2026-11-20",
                url="https://example.org/1", company="Roche", source="Roche (Workday)", salary_text="20 000 PLN/mo",
                salary_min=20000, salary_max=20000, salary_currency="PLN"),
            job("Postdoc in Lithium Batteries", "", geo="Europe", location="Sweden", category="Academia",
                seniority="PostDoc", date="2026-11-21", first_seen="2026-11-21", url="https://example.org/2",
                company="JobRxiv", source="JobRxiv"),
        ]
        archived = [job(f"Computational Biologist {i}", "single-cell", geo="USA", location="Boston, MA",
                        category="Pharma/Biotech", seniority="Mid", date=f"2026-08-{i + 1:02d}",
                        first_seen=f"2026-08-{i + 1:02d}", url=f"https://example.org/a{i}", company="Flatiron Health",
                        source="Flatiron Health (Greenhouse)", archived=True) for i in range(30)]
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            (docs / "jobs.json").write_text(json.dumps({"updated": "2026-11-23T08:00:00+00:00", "jobs": jobs}))
            (docs / "archive.json").write_text(json.dumps({"jobs": archived}))
            old = (bp.DOCS, bp.JOBS_PATH, bp.ARCHIVE_PATH, bp.DESCRIPTIONS_PATH)
            bp.DOCS, bp.JOBS_PATH, bp.ARCHIVE_PATH = docs, docs / "jobs.json", docs / "archive.json"
            bp.DESCRIPTIONS_PATH = docs / "descriptions.json"
            try:
                bp.main()
                first = {p: p.read_text() for p in docs.rglob("*") if p.is_file()}
                bp.main()   # second run without new data changes nothing
                second = {p: p.read_text() for p in docs.rglob("*") if p.is_file()}
            finally:
                bp.DOCS, bp.JOBS_PATH, bp.ARCHIVE_PATH, bp.DESCRIPTIONS_PATH = old
            self.assertEqual(first, second)
            wro = (docs / "browse" / "wroclaw.html").read_text()
            self.assertIn("Senior Bioinformatician", wro)
            self.assertNotIn("noindex", wro)
            self.assertIn("noindex", (docs / "browse" / "krakow.html").read_text())   # no offers there
            self.assertTrue((docs / "companies" / "roche.html").exists())
            self.assertFalse((docs / "companies" / "jobrxiv.html").exists())         # a board, not an employer
            self.assertTrue((docs / "reports" / "2026-q3.html").exists())            # 30 archived offers
            self.assertFalse((docs / "reports" / "2026-q4.html").exists())           # only 2 offers
            data = json.loads((docs / "jobs.json").read_text())
            self.assertIn("relevance", data["jobs"][0])
            self.assertEqual(data["jobs"][0]["title"], "Senior Bioinformatician")
            sitemap = (docs / "sitemap.xml").read_text()
            self.assertIn("browse/wroclaw.html", sitemap)
            self.assertNotIn("browse/krakow.html", sitemap)


if __name__ == "__main__":
    unittest.main()
