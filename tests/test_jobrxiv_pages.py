"""JobRxiv full-page reading: parser, caching and request budget (no network)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_jobs as fj  # noqa: E402

REQS = ("We expect strong programming skills in Python and R, experience with Nextflow or Snakemake "
        "pipelines on an HPC cluster, and version control with Git. ") * 3

PAGE = f"""<html><body><div class="single_job_listing">
<ul class="job-listing-meta meta"><li class="job-type full-time">Full Time</li>
<li class="location"><a class="google_map_link" href="#">Heidelberg, Germany</a></li></ul>
<div class="company"><img class="company_logo" src="x.png"><p class="name">
<a class="website" href="https://dkfz.de">Website</a><strong>German Cancer Research Center (DKFZ)</strong></p></div>
<div class="job_description"><p>The group studies tumour evolution with single-cell genomics.</p>
<div class="inner"><h3>Your profile</h3><ul><li>{REQS}</li><li>PhD in bioinformatics</li></ul></div>
<p>Apply by 31 January.</p></div>
<div class="sidebar">Similar jobs: Lab manager</div></div></body></html>"""


class Parser(unittest.TestCase):
    def test_reads_description_location_employer(self):
        p = fj.parse_jobrxiv_page(PAGE)
        self.assertIn("Nextflow", p["text"])
        self.assertIn("Apply by 31 January", p["text"])
        self.assertNotIn("Similar jobs", p["text"])          # stops at the end of the description
        self.assertEqual(p["location"], "Heidelberg, Germany")
        self.assertEqual(p["employer"], "German Cancer Research Center (DKFZ)")

    def test_unknown_layout_returns_nothing_instead_of_junk(self):
        p = fj.parse_jobrxiv_page("<html><body><p>Cookie banner</p></body></html>")
        self.assertEqual(p, {"text": "", "location": "", "employer": ""})


def feed_entry(title, link):
    return {"title": title, "summary": "Short teaser about a bioinformatics role in genomics.", "link": link,
            "published_parsed": None}


class FetchRss(unittest.TestCase):
    def run_feed(self, entries, known=None, budget=None):
        resp = mock.Mock(status_code=200, content=b"", text=PAGE)
        empty = mock.Mock(entries=[])
        pages = iter([mock.Mock(entries=entries)])
        with mock.patch.object(fj, "RSS_FEEDS", [{"name": "JobRxiv", "url": "https://jobrxiv.org/?feed=rss2", "paginate": True}]), \
             mock.patch.object(fj.requests, "get", return_value=resp) as get, \
             mock.patch.object(fj.feedparser, "parse", side_effect=lambda _c: next(pages, empty)), \
             mock.patch.object(fj, "JOBRXIV_MAX_PAGES", budget or fj.JOBRXIV_MAX_PAGES):
            out = fj.fetch_rss(set(), {"User-Agent": "test"}, set(), known=known, sleep=lambda _s: None)
        page_calls = [c for c in get.call_args_list if "/job/" in c.args[0]]
        return out, page_calls

    def test_new_offer_is_read_in_full(self):
        out, calls = self.run_feed([feed_entry("Bioinformatician", "https://jobrxiv.org/job/a-1/")])
        self.assertEqual(len(calls), 1)
        j = out[0]
        self.assertTrue(j["full_text"])
        self.assertTrue({"Python", "R", "Nextflow"} <= set(j["tags"]), j["tags"])
        self.assertEqual(j["employer"], "German Cancer Research Center (DKFZ)")
        self.assertEqual(j["location"], "Heidelberg, Germany")
        self.assertLessEqual(len(j["description"]), 800)

    def test_offer_read_before_is_not_fetched_again(self):
        link = "https://jobrxiv.org/job/a-1/"
        known = {fj.url_key(link): {"full_text": True, "description": "x" * 400, "tags": ["Python", "Nextflow"],
                                    "location": "Heidelberg, Germany", "employer": "DKFZ"}}
        out, calls = self.run_feed([feed_entry("Bioinformatician", link)], known=known)
        self.assertEqual(calls, [])
        self.assertEqual(out[0]["tags"], ["Python", "Nextflow"])
        self.assertEqual(out[0]["employer"], "DKFZ")

    def test_page_cap(self):
        entries = [feed_entry(f"Bioinformatician {i}", f"https://jobrxiv.org/job/a-{i}/") for i in range(5)]
        out, calls = self.run_feed(entries, budget=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sum(1 for j in out if j.get("full_text")), 2)
        self.assertEqual(len(out), 5)      # the rest still listed, from the feed text


if __name__ == "__main__":
    unittest.main()
