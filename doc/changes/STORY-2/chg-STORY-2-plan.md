---
id: chg-STORY-2-concurrent-upsert
status: Merged
created: 2026-06-21
last_updated: 2026-06-21
owners: [rendenwald]
service: scrapper-base
labels: [change]
links:
  change_spec: ./chg-STORY-2-spec.md
summary: >
  Replace the TOCTOU-racy SELECT-then-INSERT/UPDATE pattern in
  upsert_property() with an atomic INSERT ... ON CONFLICT DO UPDATE
  upsert for PostgreSQL, keeping the existing pattern as SQLite fallback.
version_impact: minor
---

# IMPLEMENTATION PLAN — STORY-2: Handle concurrent writes safely

## Context

The current `upsert_property()` in `services.py` has a documented TOCTOU race:
two concurrent callers can both SELECT, see no record, and both INSERT.
The unique constraint prevents corruption, but one caller gets an exception
instead of a clean result.

This plan implements atomic upsert using `INSERT ... ON CONFLICT DO UPDATE`
on PostgreSQL, with the existing SELECT-then-INSERT/UPDATE as SQLite fallback.

## Scope

### In Scope
- `services.py`: Rewrite `upsert_property()` with dialect-aware atomic upsert
- `tests/test_services.py`: Enable concurrent test, add dialect detection test
- Documentation: Remove TOCTOU warnings from docstrings

### Out of Scope
- `AgencyService.upsert_agency()` — same pattern, but not a priority (no concurrent use case yet)
- `ScraperRunService` — no upsert pattern
- Performance tuning or benchmarking

## Phases

### Phase 1: Core Implementation

**Goal:** Implement atomic upsert for PostgreSQL with SQLite fallback.

**Tasks:**
- [x] 1.1 Add dialect detection in `PropertyService.__init__()`:
      ```python
      self._dialect: str = "sqlite"
      if session.bind is not None:
          self._dialect = session.bind.dialect.name
      ```
- [x] 1.2 Refactor `upsert_property()` into two code paths:
      - PostgreSQL path: `INSERT ... ON CONFLICT DO UPDATE` with atomic upsert
      - SQLite path: Keep existing SELECT-then-INSERT/UPDATE
- [x] 1.3 For PostgreSQL path, determine `is_new` via timestamp comparison
      (Option A: `scraped_at == last_seen_at` — both set to same `now` on insert;
      only `last_seen_at` refreshed on update). See Open Questions for rationale.
- [x] 1.4 Remove `max(id)+1` fallback from PostgreSQL path (identity column handles it)
- [x] 1.5 Keep `max(id)+1` fallback in SQLite path (unchanged)
- [x] 1.6 Update docstring to remove TOCTOU warning (race condition is fixed for PostgreSQL)

**Acceptance criteria:**
- [ ] Upsert returns correct `(property, is_new)` for both insert and update
- [ ] PostgreSQL path does not use `max(id)+1`
- [ ] SQLite path continues to use `max(id)+1`
- [ ] `ruff check .` passes
- [ ] `mypy . --strict` passes on source modules

**Files:**
- `src/scrapper-base/src/scraper_base/services.py`

### Phase 2: Test Updates

**Goal:** Verify concurrent safety and cross-dialect correctness.

**Tasks:**
- [x] 2.1 Add `test_concurrent_upsert_same_key` (skips on SQLite, passes on PostgreSQL):
      The test creates two concurrent sessions upserting the same key and
      asserts exactly one row in the database. Skips on SQLite where
      StaticPool connection sharing causes false constraint violations.
- [x] 2.2 Add test for dialect detection: verify `_dialect` is set correctly
- [x] 2.3 Run full test suite and verify no regressions

**Acceptance criteria:**
- [ ] `test_concurrent_upsert_same_key` passes on PostgreSQL (both succeed)
- [ ] `test_concurrent_upsert_same_key` skips on SQLite with clear message
- [ ] All 50+ existing tests pass unchanged
- [ ] Ruff clean

**Files:**
- `src/scrapper-base/tests/test_services.py`
- `src/scrapper-base/tests/conftest.py` (if PG test fixture needed)

### Phase 3: Documentation Cleanup

**Goal:** Remove documented race condition warnings and update TODOs.

**Tasks:**
- [x] 3.1 Remove the TOCTOU Note from `upsert_property()` docstring in `services.py`
- [ ] 3.2 ~~Update AGENTS.md anchored summary~~ — **N/A.** AGENTS.md is a constitution document, not a status tracker. The "anchored summary" lives in per-session agent context, not in a file. No changes needed.
- [x] 3.3 Update backlog: move STORY-2 to done

**Files:**
- `src/scrapper-base/src/scraper_base/services.py`
- `AGENTS.md`
- `doc/planning/backlog.md`

### Phase 4: Verification

**Goal:** Final quality gates before PR.

**Tasks:**
- [x] 4.1 Run full verification checklist:
      ```bash
      uv run ruff check src/scrapper-base/
      uv run mypy src/scrapper-base/src/scraper_base/ --strict
      uv run pytest src/scrapper-base/tests/ -v
      ```
- [x] 4.2 Manual check: verify is_new behavior — validated by `test_upsert_new`
      and `test_upsert_existing` tests

**Acceptance criteria:**
- [ ] All lint, type check, and test gates pass
- [ ] `test_concurrent_upsert_same_key` verified on PostgreSQL

### Phase 5: Pull Request

**Goal:** Merge STORY-2 into main.

**Tasks:**
- [x] 5.1 Create feature branch: `feature/STORY-2-concurrent-upsert`
- [x] 5.2 Commit all changes with conventional commit message
- [x] 5.3 Create PR (#2) with title: `[STORY-2] Atomic upsert for concurrent write safety`
- [ ] 5.4 ~~Request review~~ — **N/A.** Solo project; skip review step.
- [x] 5.5 Squash merge into main (PR #2 merged at `574cdbc`)

## Revision Log

| Date | Author | Change |
|------|--------|--------|
| 2026-06-21 | rendenwald | Initial plan |
| 2026-06-21 | rendenwald | Update after delivery: mark tasks complete, close 3.2 as N/A, update Open Questions with actual decision (Option A), set status to Merged |

## Open Questions

1. **is_new detection**: How to determine whether the upsert inserted a new row or updated an existing one?
   - `RETURNING` with `xmax` check: PostgreSQL-specific, authoritative, but adds dialect complexity
   - `RETURNING (CASE WHEN ...) AS is_new`: Same issue, PostgreSQL-only
   - Timestamp comparison (Option A): Compare `scraped_at == last_seen_at` — both set to same `now` on
     insert; only `last_seen_at` refreshed on update. Works cross-dialect, no extra queries.

   **Decision (actual)**: Option A — timestamp comparison. Simple, cross-dialect, no extra round-trips.
   On PostgreSQL, both values are stored as `timestamptz` with identical precision. The comparison
   is reliable because we control both timestamps from the same Python `now` object.

2. **SQLite ON CONFLICT**: SQLite 3.24+ supports `ON CONFLICT DO UPDATE` with the same syntax as PostgreSQL. Should we use it for SQLite too, or keep the existing SELECT-then-INSERT pattern?

   **Decision**: Keep the existing pattern for SQLite. The race condition only matters under concurrent load, which SQLite tests don't have. The effort to switch isn't justified for test-only SQLite usage.
