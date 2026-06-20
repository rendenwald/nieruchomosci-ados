# 040 — ACCEPTANCE-CRITERIA / Key Gherkin Scenarios

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 030-USER-STORIES.md
- **AI Context:** Gherkin acceptance criteria for the most critical user stories. Use as test specifications.

---

### MT-5: Grafana Dashboard — Scraper Metrics

```gherkin
Given scraper uruchomiony dla portalu "otodom"
And scraper zakończył sesję scrapowania

When admin otwiera Grafana dashboard "Scrapers Overview"

Then widzi wykres listings_scraped_total z podziałem per portal
And widzi histogram scrape_duration_seconds (p50, p95, p99)
And widzi alert jeśli error_rate > 5% przez ostatnie 15 minut
And dane są odświeżane co 30 sekund
```

### MAP-4: Geographic Filtering on Map

```gherkin
Given użytkownik jest na stronie /mapa
And mapa pokazuje 500 ofert w Polsce

When użytkownik rysuje polygon na mapie obejmujący dzielnicę Krzyki we Wrocławiu

Then lista ofert po prawej aktualizuje się do ofert w narysowanym obszarze
And URL aktualizuje się do /oferty?bbox=17.01,51.08,17.07,51.12
And licznik pokazuje "Znaleziono X ofert w wybranym obszarze"
And mapa pokazuje tylko markery w narysowanym obszarze
```

### I18N-2: Currency Conversion

```gherkin
Given oferta ma cenę 620 000 PLN
And użytkownik wybrał walutę EUR
And dzisiejszy kurs ECB: 1 EUR = 4.25 PLN

When karta oferty jest wyświetlona

Then cena wyświetla się jako "145 882 €"
And format liczby jest zgodny z locale (145 882 € dla PL, €145,882 dla EN)
And tooltip pokazuje "Przeliczone wg kursu ECB z dnia 2026-06-15"
And cena w PLN jest dostępna po najechaniu na wartość
```

### ALT-2: Email Alert for New Property

```gherkin
Given użytkownik "jan@example.com" ma aktywny alert:
  city="Wrocław", property_type="flat",
  price_max=600000, area_min=50

When scraper zapisuje nową ofertę spełniającą kryteria

Then system wysyła email do jan@example.com w ciągu 5 minut
And email zawiera: zdjęcie, cenę, metraż, link do oferty
And email jest wysłany w języku wybranym przez użytkownika
And użytkownik może wypisać się linkiem w stopce emaila
```

---

## AI Implementation Notes

- These scenarios should be converted to automated tests (Playwright or pytest).
- Create test files matching each scenario ID: `test_mt5.py`, `test_map4.py`, `test_i18n2.py`, `test_alt2.py`.
- Verify with: `pytest tests/ -v`.
- Related: 060-SCRAPER-BASE.md, 100-MAP.md, 110-I18N-CURRENCY.md, 130-MONITORING-ALERTS.md.
