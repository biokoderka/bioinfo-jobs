# Panel admina — jak obsługiwać BioInfoJobs

## Dodawanie oferty (zgłoszenie z formularza albo coś, co sama znalazłaś)

Zgłoszenia z `submit.html` przychodzą mailem przez Formspree. Na końcu maila jest pole **`admin_json`** — gotowy blok do wklejenia.

1. GitHub → repo `bioinfo-jobs` → **Actions** → **Add job** → **Run workflow**
   (działa też w aplikacji GitHub na telefonie)
2. Wklej `admin_json` w pole **job_json** — albo zostaw je puste i wypełnij pola title / company / url / location / deadline.
3. **Run workflow**. Po ok. minucie oferta jest na stronie.

Skrypt sam uzupełnia region, sektor, poziom, tagi technologiczne i widełki (jeśli są w opisie), pilnuje duplikatów i odrzuca oferty z minionym terminem.

**Jak długo oferta wisi:** do deadline'u, a bez deadline'u — 60 dni. Cotygodniowy scraper jej nie rusza.

## Zdejmowanie oferty

Actions → **Add job** → w polu **archive_id** wpisz id oferty (np. `manual_2abef4b283`; id widać w `docs/jobs.json`). Oferta trafia do archiwum.

## Lokalnie (opcjonalnie)

```bash
git pull origin main
python3 scripts/add_job.py --title "Bioinformatician" --company "Ardigen" \
  --url "https://..." --location "Kraków, Poland" --deadline 2026-11-30
git add docs/*.json && git commit -m "Add job" && git push
```

Zawsze najpierw `git pull` — Actions commitują prosto na GitHuba.

## Statystyki wyszukiwań w Job Match (opcjonalnie, ~5 min)

`match.html` może anonimowo logować, czego ludzie szukają (umiejętności, zainteresowania, region — bez żadnych danych osobowych) do Arkusza Google. Instrukcja jest na górze `scripts/search_log_apps_script.gs`. Po wdrożeniu wklej URL kończący się na `/exec` do stałej `SEARCH_LOG_ENDPOINT` w `docs/match.html`.

## Google Search Console (jednorazowo)

1. https://search.google.com/search-console → **Dodaj usługę** → *Prefiks URL* → `https://biokoderka.github.io/bioinfo-jobs/`
2. Weryfikacja metodą **Tag HTML** — wklej podany `<meta name="google-site-verification" …>` do `<head>` w `docs/index.html`, wypchnij, kliknij *Zweryfikuj*.
3. **Mapy witryn** → dodaj `sitemap.xml`.

## Co zostało usunięte w październiku 2026

Stary przepływ „GitHub Issue + `/approve` + admin.html z tokenem w JS” nigdy nie był podpięty (formularz wysyłał do Formspree), więc `approve-job.yml` został usunięty. Trzymanie tokena GitHuba w publicznym JS i tak nie byłoby bezpieczne.
