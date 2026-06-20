# Epic 03: Interactive Map

> **Goal:** Provide an interactive map view using MapLibre GL showing property clusters, individual markers, and polygon-based filtering.

## Scope

- MapLibre GL integration in SvelteKit
- Property clustering at zoom levels
- Marker popups with property card
- Polygon drawing for geographic filtering
- Dynamic filter updates without page reload

## Success Criteria

- Map loads with clustered markers
- Zooming expands clusters to individual markers
- Clicking a marker shows property details
- Drawing a polygon filters results to that area

## Related Spec Modules

- `specs/100-MAP.md`
- `specs/090-FRONTEND.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-13 | Display property clusters with counts on map |
| STORY-14 | Expand clusters into individual markers on zoom |
| STORY-15 | Show property card popup on marker click |
| STORY-16 | Filter results to polygon drawn on map |
| STORY-17 | Update map markers without page reload on filter change |
