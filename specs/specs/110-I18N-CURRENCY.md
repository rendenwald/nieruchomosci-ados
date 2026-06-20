# 110 — I18N-CURRENCY / Internationalization & Multi-Currency

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 090-FRONTEND.md, 120-CACHING-STORAGE.md
- **AI Context:** Implements Epic 7 (I18N-1 through I18N-5) — multi-language UI and ECB-based currency conversion.

---

## User Stories Implemented

| ID | Description | Points |
|----|-------------|--------|
| I18N-1 | **When** user selects language, **shall** display all UI in PL/EN/DE/UA | 8 |
| I18N-2 | **When** user selects currency, **shall** convert prices using daily ECB rates | 8 |
| I18N-3 | **When** URL accessed with `/en/`, **shall** serve English version with hreflang | 5 |
| I18N-4 | **When** price displayed, **shall** format according to locale | 3 |
| I18N-5 | **When** search performed, **shall** normalize Polish diacritics in city names | 3 |

---

## Architecture

```mermaid
graph TB
    subgraph "URL Structure"
        PL["/pl/oferty - Polish (default)"]
        EN["/en/properties - English"]
        DE["/de/immobilien - Deutsch"]
        UA["/ua/neruhomist - Ukrainian"]
    end

    subgraph "i18n Stack"
        LIB[paraglide-js]
        MSGS[messages/ pl.json en.json de.json ua.json]
        LIB --> MSGS
    end

    subgraph "Currency Service"
        ECB[ECB API Daily rates fetch]
        STORE[Redis Cache rates:ecb:YYYY-MM-DD]
        CONV[formatCurrency() Intl.NumberFormat]
        ECB --> STORE --> CONV
    end

    subgraph "SEO"
        HREFLANG[hreflang tags pl/en/de/ua]
        SITEMAP[sitemap.xml per language]
        OG[OpenGraph locale-specific]
    end
```

---

## Supported Languages & Currencies

| Language | Code | Currency | Price Format | URL Prefix |
|----------|------|----------|-------------|------------|
| Polish | `pl` | PLN | `1 250 000 zł` | `/pl/` (default) |
| English | `en` | EUR/GBP/USD | `€312,500` | `/en/` |
| Deutsch | `de` | EUR | `312.500 €` | `/de/` |
| Ukrainian | `ua` | UAH/PLN | `₴12 500 000` | `/ua/` |

---

## Translation File Structure

```json
{
  "nav.offers": "Oferty",
  "nav.map": "Mapa",
  "nav.add": "Dodaj ogłoszenie",
  "search.location.placeholder": "np. Warszawa, Mokotów",
  "search.type.all": "Wszystkie typy",
  "property.price": "{price} {currency}",
  "property.area": "{area} m²",
  "property.rooms": "{count, plural, one {# pokój} few {# pokoje} many {# pokoi} other {# pokoi}}",
  "property.available_on": "Dostępne na {count, plural, one {# portalu} other {# portalach}}",
  "alert.created": "Alert utworzony! Powiadomimy Cię gdy pojawi się nowa oferta.",
  "currency.disclaimer": "Przeliczone wg kursu ECB z dnia {date}",
  "map.cluster": "{count} ofert",
  "portal.otodom": "Otodom",
  "portal.gratka": "Gratka",
  "portal.nieruchomosci-online": "Nieruchomości Online"
}
```

---

## Acceptance Criterion: I18N-2

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

---

## AI Implementation Notes

**Files to generate:**
- Translation files: `real-estate-portal/src/lib/i18n/messages/{pl,en,de,ua}.json`
- i18n configuration with paraglide-js
- Currency service in `real-estate-api/app/services/currency.py`
- ECB rate fetcher CronJob (daily update to Redis)
- `formatCurrency()` utility with `Intl.NumberFormat`
- Diacritics normalization utility for Polish city search
- hreflang tags in SvelteKit layout
- sitemap.xml generation per language

**Verification:**
- Navigate to `/pl/oferty` and `/en/properties` — same content different language
- Change currency — prices update with tooltip
- ECB rate fetch: `curl http://localhost:8000/api/v1/exchange-rates`
- `npm run build` succeeds

**Related modules:** 090-FRONTEND.md (component integration), 120-CACHING-STORAGE.md (Redis cache for rates), 080-API.md (exchange-rates endpoint).

---

## FIX-11: RTL language preparation

See `090-FRONTEND.md` for the `hooks.server.ts` implementation. Spec-level decisions:

- `RTL_LANGUAGES` list maintained in `src/hooks.server.ts` — currently empty
- Adding any RTL language requires: (1) add to `languageTags`, (2) add to `RTL_LANGUAGES`, (3) add `.json` translation file, (4) test form layouts (inputs, selectors) and MapLibre controls
- MapLibre GL does not natively flip for RTL; use `maplibre-gl-rtl-text` plugin when needed

```typescript
// Future: when adding Arabic
import 'maplibre-gl/dist/maplibre-gl-rtl-text.js';
maplibregl.setRTLTextPlugin('/maplibre-gl-rtl-text.js', null, true);
```
