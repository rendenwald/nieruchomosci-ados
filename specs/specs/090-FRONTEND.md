# 090 — FRONTEND / SvelteKit Portal & TypeScript Interfaces

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 080-API.md, 110-I18N-CURRENCY.md
- **AI Context:** Complete SvelteKit frontend specification. AI agent should generate `real-estate-portal/`.

---

## Repository Structure

```
real-estate-portal/
├── src/
│   ├── lib/
│   │   ├── i18n/                 ← paraglide-js
│   │   │   ├── messages/
│   │   │   │   ├── pl.json
│   │   │   │   ├── en.json
│   │   │   │   ├── de.json
│   │   │   │   └── ua.json
│   │   │   └── runtime.js
│   │   ├── api/                  ← API client
│   │   ├── stores/               ← Svelte stores (filters, currency)
│   │   └── types/                ← TypeScript interfaces
│   ├── routes/
│   │   ├── [lang]/               ← i18n routing
│   │   │   ├── +layout.svelte
│   │   │   ├── +page.svelte      ← Home
│   │   │   ├── oferty/
│   │   │   │   ├── +page.svelte  ← Search results
│   │   │   │   └── [id]/
│   │   │   │       └── +page.svelte ← Details
│   │   │   └── mapa/
│   │   │       └── +page.svelte  ← MapLibre map view
│   └── hooks.server.ts           ← i18n middleware
├── Dockerfile
└── k8s/deployment.yaml
```

---

## TypeScript Interfaces

```typescript
// lib/types/index.ts

export type PortalSource =
  | 'otodom' | 'nieruchomosci-online' | 'gratka'
  | 'morizon' | 'domiporta' | 'olx' | 'gumtree';

export type PropertyType =
  | 'flat' | 'house' | 'plot' | 'venue'
  | 'garage' | 'magazine' | 'investment' | 'room';

export type AuctionType = 'sale' | 'rent';
export type Language = 'pl' | 'en' | 'de' | 'ua';
export type Currency = 'PLN' | 'EUR' | 'USD' | 'GBP' | 'UAH';

export interface PortalLink {
  portal: PortalSource;
  url: string;
  logoUrl: string;
  label: string;
}

export interface PropertyCard {
  id: number;
  title: string;
  propertyType: PropertyType;
  auctionType: AuctionType;
  price: number;
  priceCurrency: Currency;
  priceConverted?: number;
  priceDisplayCurrency?: Currency;
  pricePerM2?: number;
  area?: number;
  plotArea?: number;
  rooms?: string;
  city: string;
  district?: string;
  latitude?: number;
  longitude?: number;
  thumbnail?: string;
  isPromoted: boolean;
  isNew: boolean;
  portalLinks: PortalLink[];
  totalPortals: number;
  scrapedAt: string;
  duplicateGroupId?: string;
}

export interface PropertyDetail extends PropertyCard {
  description?: string;
  photos: string[];
  floor?: string;
  floorsTotal?: number;
  yearBuilt?: number;
  constructionStatus?: string;
  condition?: string;
  heating?: string;
  extras?: string[];
  securityTypes?: string[];
  parking?: string;
  marketType?: string;
  offeredBy?: 'private' | 'agency';
  agencyName?: string;
  building?: {
    type?: string;
    floors?: number;
    buildYear?: number;
  };
}

export interface MapMarker {
  id: number;
  lat: number;
  lng: number;
  price: number;
  currency: Currency;
  propertyType: PropertyType;
  isPromoted: boolean;
  thumbnail?: string;
}

export interface MapCluster {
  lat: number;
  lng: number;
  count: number;
  avgPrice: number;
}

export interface BoundingBox {
  minLat: number;
  minLng: number;
  maxLat: number;
  maxLng: number;
}

export interface SearchParams {
  city?: string;
  propertyType?: PropertyType | 'all';
  auctionType?: AuctionType | 'all';
  priceMin?: number;
  priceMax?: number;
  areaMin?: number;
  areaMax?: number;
  rooms?: number | 'any';
  marketType?: 'primary' | 'secondary' | 'all';
  bbox?: BoundingBox;
  page?: number;
  limit?: number;
  sortBy?: SortOption;
  lang?: Language;
  currency?: Currency;
}

export type SortOption =
  | 'price_asc' | 'price_desc'
  | 'date_desc' | 'area_desc'
  | 'promoted_first';

export interface UserAlert {
  id: number;
  city?: string;
  propertyType?: PropertyType;
  auctionType?: AuctionType;
  priceMin?: number;
  priceMax?: number;
  areaMin?: number;
  areaMax?: number;
  rooms?: number;
  isActive: boolean;
  createdAt: string;
  lastTriggered?: string;
}

export interface CreateAlertRequest {
  city?: string;
  propertyType?: PropertyType;
  priceMin?: number;
  priceMax?: number;
  areaMin?: number;
}

export interface ExchangeRates {
  base: 'PLN';
  date: string;
  rates: Record<Currency, number>;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: {
    total: number;
    page: number;
    limit: number;
    pages: number;
  };
}

export type SearchResponse = PaginatedResponse<PropertyCard>;

export interface ApiError {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
}
```

---

## Routes Overview

| Route | Page | Description |
|-------|------|-------------|
| `/[lang]/` | Home | Landing page with hero, search bar |
| `/[lang]/oferty` | Search results | Property list + filters + map |
| `/[lang]/oferty/[id]` | Detail | Full property detail with gallery |
| `/[lang]/mapa` | Map | Full-screen map with clusters/filter |

---

## AI Implementation Notes

**Files to generate:**
- `real-estate-portal/package.json` — SvelteKit + paraglide-js + MapLibre deps
- `real-estate-portal/src/lib/types/index.ts` — all interfaces above
- `real-estate-portal/src/lib/api/` — API client wrapping 080-API.md endpoints
- `real-estate-portal/src/lib/stores/` — filter, currency, auth stores
- `real-estate-portal/src/routes/[lang]/+layout.svelte` — i18n layout
- `real-estate-portal/src/routes/[lang]/+page.svelte` — home page
- `real-estate-portal/src/routes/[lang]/oferty/+page.svelte` — search results
- `real-estate-portal/src/routes/[lang]/oferty/[id]/+page.svelte` — detail
- `real-estate-portal/src/routes/[lang]/mapa/+page.svelte` — map view (see 100-MAP.md)
- `real-estate-portal/src/hooks.server.ts` — i18n middleware
- `real-estate-portal/Dockerfile`
- `real-estate-portal/k8s/deployment.yaml`

**Verification:**
- `npm run dev` — dev server starts
- `npm run build` — production build succeeds
- `npm run lint` — no lint errors
- Page renders at `localhost:5173/pl/`

**Related modules:** 100-MAP.md (map view), 110-I18N-CURRENCY.md (i18n + currency), 080-API.md (API client).

---

## FIX-6: Security headers & XSS protection

### Content Security Policy (SvelteKit hooks)

```typescript
// src/hooks.server.ts — add security headers to every response
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
    const response = await resolve(event);

    response.headers.set(
        'Content-Security-Policy',
        [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",           // MapLibre needs inline styles
            "img-src 'self' data: blob: https://*.maptiler.com",
            "worker-src blob:",                            // MapLibre GL workers
            "connect-src 'self' https://api.maptiler.com https://api.maplibre.org",
            "frame-ancestors 'none'",
        ].join('; ')
    );
    response.headers.set('X-Frame-Options', 'DENY');
    response.headers.set('X-Content-Type-Options', 'nosniff');
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
    response.headers.set('Permissions-Policy', 'geolocation=(), camera=()');

    return response;
};
```

### DOMPurify sanitization for property descriptions

```typescript
// src/lib/utils/sanitize.ts
import DOMPurify from 'dompurify';

/** Sanitize HTML from external portals before rendering with {@html ...} */
export function sanitizeHtml(dirty: string): string {
    return DOMPurify.sanitize(dirty, {
        ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'li', 'ol'],
        ALLOWED_ATTR: [],   // no href, no onclick, no style
    });
}
```

```svelte
<!-- src/routes/[lang]/oferty/[id]/+page.svelte -->
<script>
    import { sanitizeHtml } from '$lib/utils/sanitize';
</script>

<!-- NEVER: {@html property.description} -->
<!-- ALWAYS: -->
{@html sanitizeHtml(property.description ?? '')}
```

Install: `npm install dompurify @types/dompurify`

### AGENTS.md rule addition

Add to Hard Rules table:
```
| NEVER render raw HTML from external sources — always sanitize with DOMPurify | XSS |
```

## FIX-11: RTL language support preparation

```typescript
// src/hooks.server.ts — set dir attribute per locale
const RTL_LANGUAGES: Language[] = [];   // extend with 'ar' | 'he' when needed

export const handle: Handle = async ({ event, resolve }) => {
    const lang = event.params.lang as Language ?? 'pl';
    const dir = RTL_LANGUAGES.includes(lang) ? 'rtl' : 'ltr';

    const response = await resolve(event, {
        transformPageChunk: ({ html }) =>
            html.replace('<html', `<html lang="${lang}" dir="${dir}"`),
    });
    // ... security headers ...
    return response;
};
```

```json
// paraglide config (project.inlang/settings.json)
{
  "languageTags": ["pl", "en", "de", "ua"],
  "rtlLanguageTags": []
}
```

> Cost to add RTL language later: change `RTL_LANGUAGES = ['ar']` + translate `ar.json`.
> Without `dir` attribute in the template, the cost becomes a full layout audit.
