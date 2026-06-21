---
id: chg-STORY-2-concurrent-upsert
status: Draft
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
- [ ] 1.1 Add dialect detection in `PropertyService.__init__()`:
      ```python
      self._dialect: str = "sqlite"
      self._db_bind = getattr(self.session, "bind", None)
      if self._db_bind is not None:
          self._dialect = self._db_bind.dialect.name
      ```
- [ ] 1.2 Refactor `upsert_property()` into two code paths:
      - PostgreSQL path: `INSERT ... ON CONFLICT DO UPDATE` with `RETURNING`
      - SQLite path: Keep existing SELECT-then-INSERT/UPDATE
- [ ] 1.3 For PostgreSQL path, handle `RETURNING` result to determine `is_new`:
      - `xmax` = 0 means INSERT, `xmax` > 0 means UPDATE
      - Or use `RETURNING (CASE WHEN ...)` as a boolean flag
      - Alternative: use `session.refresh()` after the upsert
- [ ] 1.4 Remove `max(id)+1` fallback from PostgreSQL path (identity column handles it)
- [ ] 1.5 Keep `max(id)+1` fallback in SQLite path (unchanged)
- [ ] 1.6 Update docstring to remove TOCTOU warning (race condition is fixed)

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
- [ ] 2.1 Update `test_concurrent_upsert_same_key` to run on PostgreSQL:
      The test currently skips on SQLite. For PostgreSQL (CI), it must
      assert both upserts succeed. For SQLite (local dev), keep skip.
- [ ] 2.2 Add test for dialect detection: verify `_dialect` is set correctly
- [ ] 2.3 Run full test suite and verify no regressions

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
- [ ] 3.1 Remove the TOCTOU Note from `upsert_property()` docstring in `services.py`
- [ ] 3.2 Update `AGENTS.md` anchored summary to reflect STORY-1 completion
- [ ] 3.3 Update backlog: move STORY-2 to in-progress

**Files:**
- `src/scrapper-base/src/scraper_base/services.py`
- `AGENTS.md`
- `doc/planning/backlog.md`

### Phase 4: Verification

**Goal:** Final quality gates before PR.

**Tasks:**
- [ ] 4.1 Run full verification checklist:
      ```bash
      uv run ruff check src/scrapper-base/
      uv run mypy src/scrapper-base/src/scraper_base/ --strict
      uv run pytest src/scrapper-base/tests/ -v
      ```
- [ ] 4.2 Manual check: verify is_new behavior with a simple script or REPL

**Acceptance criteria:**
- [ ] All lint, type check, and test gates pass
- [ ] `test_concurrent_upsert_same_key` verified on PostgreSQL

### Phase 5: Pull Request

**Goal:** Merge STORY-2 into main.

**Tasks:**
- [ ] 5.1 Create feature branch: `feature/STORY-2-concurrent-upsert`
- [ ] 5.2 Commit all changes with conventional commit message
- [ ] 5.3 Create PR with title: `[STORY-2] Atomic upsert with ON CONFLICT DO UPDATE`
- [ ] 5.4 Request review
- [ ] 5.5 Squash merge into main

## Revision Log

| Date | Author | Change |
|------|--------|--------|
| 2026-06-21 | rendenwald | Initial plan |

## Open Questions

1. **RETURNING vs refresh()**: PostgreSQL `INSERT ... ON CONFLICT DO UPDATE RETURNING *` returns the upserted row directly. But we need to distinguish INSERT vs UPDATE. Options:
   - Check `Result.rowcount` (1 = INSERT, 2 = UPDATE on PostgreSQL)
   - Use `RETURNING (CASE WHEN xmax = 0 THEN true ELSE false END) AS is_new`
   - Use `session.refresh()` after the upsert and check `is_new` via a second query
   
   **Decision**: Use PostgreSQL's `RETURNING` with `xmax` check for the is_new flag.
   **Fallback**: `session.refresh()` for SQLite.

2. **SQLite ON CONFLICT**: SQLite 3.24+ supports `ON CONFLICT DO UPDATE` with the same syntax as PostgreSQL. Should we use it for SQLite too, or keep the existing SELECT-then-INSERT pattern?
   
   **Decision**: Keep the existing pattern for SQLite. The race condition only matters under concurrent load, which SQLite tests don't have.
