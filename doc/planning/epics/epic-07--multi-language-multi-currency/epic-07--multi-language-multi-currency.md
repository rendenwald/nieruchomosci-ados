# Epic 07: Multi-language + Multi-currency

> **Goal:** Support Polish, English, German, and Ukrainian languages with currency conversion using daily ECB exchange rates.

## Scope

- paraglide-js i18n integration in SvelteKit
- Translation files for PL/EN/DE/UA
- URL-based language routing (`/pl/`, `/en/`, `/de/`, `/ua/`)
- ECB rate fetching (daily CronJob)
- Price conversion and locale-aware formatting
- Polish diacritics normalization in search

## Success Criteria

- UI switches language based on URL prefix or user selection
- Prices display in selected currency with ECB rates
- Locale-appropriate number formatting
- hreflang tags for SEO

## Related Spec Modules

- `specs/110-I18N-CURRENCY.md`
- `specs/090-FRONTEND.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-33 | Display all UI in PL/EN/DE/UA based on user selection |
| STORY-34 | Convert prices using daily ECB rates |
| STORY-35 | Serve English version with hreflang when `/en/` accessed |
| STORY-36 | Format prices according to locale |
| STORY-37 | Normalize Polish diacritics in city names during search |
