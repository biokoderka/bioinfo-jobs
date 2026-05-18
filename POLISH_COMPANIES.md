# 🇵🇱 Polskie firmy biotech/bioinformatyka — research ATS

## Jak sprawdzić ręcznie (skopiuj URL do przeglądarki)

Dla każdej firmy sprawdź poniższe URL-e. Jeśli zwróci JSON → można dodać do skryptu.

---

## Ardigen (Kraków)
```
https://boards.greenhouse.io/ardigen/jobs.json
https://api.lever.co/v0/postings/ardigen?mode=json
https://apply.workable.com/api/v1/widget/accounts/ardigen/jobs
https://app.traffit.com/public-api/offers/?company=ardigen
https://ardigen.teamtailor.com/jobs.json
```
**Strona kariery:** https://ardigen.com/careers/

---

## Selvita (Kraków)
```
https://boards.greenhouse.io/selvita/jobs.json
https://api.lever.co/v0/postings/selvita?mode=json
https://apply.workable.com/api/v1/widget/accounts/selvita/jobs
https://app.traffit.com/public-api/offers/?company=selvita
```
**Strona kariery:** https://selvita.com/careers/

---

## Ryvu Therapeutics (Kraków)
```
https://boards.greenhouse.io/ryvu/jobs.json
https://api.lever.co/v0/postings/ryvu?mode=json
https://apply.workable.com/api/v1/widget/accounts/ryvu/jobs
https://apply.workable.com/api/v1/widget/accounts/ryvu-therapeutics/jobs
```
**Strona kariery:** https://ryvu.com/careers/

---

## Molecure (Łódź / Wrocław)
```
https://boards.greenhouse.io/molecure/jobs.json
https://apply.workable.com/api/v1/widget/accounts/molecure/jobs
https://api.lever.co/v0/postings/molecure?mode=json
```
**Strona kariery:** https://molecure.com/career/

---

## Captor Therapeutics (Wrocław)
```
https://boards.greenhouse.io/captortherapeutics/jobs.json
https://apply.workable.com/api/v1/widget/accounts/captor-therapeutics/jobs
https://api.lever.co/v0/postings/captor-therapeutics?mode=json
```
**Strona kariery:** https://captortherapeutics.com/careers/

---

## Pure Biologics (Wrocław)
```
https://boards.greenhouse.io/purebiologics/jobs.json
https://apply.workable.com/api/v1/widget/accounts/pure-biologics/jobs
https://api.lever.co/v0/postings/pure-biologics?mode=json
```
**Strona kariery:** https://purebiologics.com/careers/

---

## Intelliseq (Kraków)
```
https://boards.greenhouse.io/intelliseq/jobs.json
https://apply.workable.com/api/v1/widget/accounts/intelliseq/jobs
https://api.lever.co/v0/postings/intelliseq?mode=json
```
**Strona kariery:** https://intelliseq.com/careers/

---

## Sano Centre for Computational Personalised Medicine (Kraków)
```
https://boards.greenhouse.io/sano/jobs.json
https://apply.workable.com/api/v1/widget/accounts/sano-centre/jobs
https://sano.science/careers/
```
**Strona kariery:** https://sano.science/careers/

---

## OncoArendi Therapeutics (Warszawa)
```
https://boards.greenhouse.io/oncoarendi/jobs.json
https://apply.workable.com/api/v1/widget/accounts/oncoarendi/jobs
```
**Strona kariery:** https://oncoarendi.com/careers/

---

## Łukasiewicz – PORT (Wrocław)
```
https://www.port.org.pl/praca/feed/
https://boards.greenhouse.io/port/jobs.json
```
**Strona kariery:** https://www.port.org.pl/kariera/

---

## Sygnature Discovery (Nottingham + Kraków)
```
https://boards.greenhouse.io/sygnature/jobs.json
https://apply.workable.com/api/v1/widget/accounts/sygnature-discovery/jobs
https://api.lever.co/v0/postings/sygnature-discovery?mode=json
```
**Strona kariery:** https://www.sygnature.com/careers/

---

## Polpharma Biologics (Warszawa)
```
https://apply.workable.com/api/v1/widget/accounts/polpharma-biologics/jobs
https://boards.greenhouse.io/polpharmabio/jobs.json
```
**Strona kariery:** https://polpharmabio.eu/careers/

---

## Mabion (Łódź)
```
https://apply.workable.com/api/v1/widget/accounts/mabion/jobs
https://boards.greenhouse.io/mabion/jobs.json
```
**Strona kariery:** https://mabion.eu/kariera/

---

## Genomed (Warszawa)
```
https://apply.workable.com/api/v1/widget/accounts/genomed/jobs
https://boards.greenhouse.io/genomed/jobs.json
```
**Strona kariery:** https://genomed.pl/praca/

---

## Curiosity Diagnostics (Warszawa)
```
https://boards.greenhouse.io/curiositydiagnostics/jobs.json
https://apply.workable.com/api/v1/widget/accounts/curiosity-diagnostics/jobs
https://api.lever.co/v0/postings/curiosity-diagnostics?mode=json
```
**Strona kariery:** https://curiositydiagnostics.com/careers/

---

## BioInfoBank Institute (Poznań)
```
https://bioinfobank.pl/praca/feed/
```
**Strona kariery:** https://bioinfobank.pl/

---

## ProteinTech Group / HuBMAP Partners
- Często zatrudniają remote bioinformatyków z Polski

---

## Jak dodać działające firmy do skryptu

Jeśli URL z JSON zadziała, wklej do `fetch_jobs.py`:

### Workable:
```python
WORKABLE_COMPANIES = [
    ("Ardigen",   "ardigen"),       # jeśli działa
    ("Selvita",   "selvita"),
    # ...
]
```

I dodaj funkcję:
```python
def fetch_workable(seen, headers):
    results = []
    for company, slug in WORKABLE_COMPANIES:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}/jobs"
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200: continue
            for job in r.json().get("jobs", []):
                title = job.get("title", "")
                loc   = job.get("location", {}).get("city", "")
                link  = f"https://apply.workable.com/{slug}/j/{job.get('shortcode','')}"
                desc  = job.get("description", "")[:800]
                if not is_relevant(title, desc): continue
                uid = job_id(title, company)
                if uid in seen: continue
                seen.add(uid)
                results.append({
                    "id": uid, "title": title, "company": company,
                    "location": loc or "See listing",
                    "source": f"{company} (Workable)",
                    "date": today(), "url": link, "description": desc,
                    "geo": detect_geo(title, loc, desc),
                    "tags": [], "category": None, "summary": None,
                })
        except Exception as e:
            print(f"  ⚠ {company}: {e}")
    return results
```

### Traffit (polski ATS):
```python
TRAFFIT_COMPANIES = [
    ("Ardigen",   "ardigen"),
    # ...
]

def fetch_traffit(seen, headers):
    for company, slug in TRAFFIT_COMPANIES:
        url = f"https://app.traffit.com/public-api/offers/?company={slug}&format=json"
        # ... analogicznie
```
