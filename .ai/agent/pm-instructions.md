# PM Instructions — Local Markdown Backlog

> **Role:** Instructions for AI agents managing the project backlog and work items.
> **Tracker type:** Local (markdown files in repository)
> **Reference:** `doc/guides/change-lifecycle.md` for the standard ADOS change lifecycle.

---

## 1. Tracker Configuration

- **Type:** Local markdown
- **Backlog source of truth:** `doc/planning/backlog.md`
- **Epics directory:** `doc/planning/epics/`
- **Archive directory:** `doc/planning/archive/`
- **Git platform:** GitHub (`github.com/rendenwald/nieruchomosci-ados`)

---

## 2. Workflow States

Work items flow through these states (tracked in the backlog table):

| State | Description |
|-------|-------------|
| `todo` | Not started, ready to pick up |
| `in-progress` | Currently being worked on |
| `review` | Implementation done, awaiting review |
| `done` | Completed and merged |
| `blocked` | Cannot proceed (note reason) |

---

## 3. Label Taxonomy

Labels are applied to work items in the backlog table:

| Label | Purpose |
|-------|---------|
| `change` | Any work item that follows the ADOS change lifecycle |
| `story` | User-facing feature work |
| `bug` | Defect fix |
| `task` | Technical work (refactoring, config, CI) |
| `epic` | Grouping label for related stories |
| `priority` | High-priority item |

---

## 4. Work Item Identification

Work items use sequential IDs with type prefixes:

- `STORY-1`, `STORY-2`, ... — user stories
- `BUG-1`, `BUG-2`, ... — bugs
- `TASK-1`, `TASK-2`, ... — tasks/chores

**Numbering is sequential across all time** (never reset per sprint or per type).

Work item ID format in commit messages: `STORY-14`, `BUG-3`, `TASK-7`.

---

## 5. Backlog Conventions

### 5.1 Backlog Table (`doc/planning/backlog.md`)

The backlog is an ordered markdown table. Columns:

| ID | Title | Type | Priority | Status | Epic | Labels |
|----|-------|------|----------|--------|------|--------|

- **Order** = priority within the table (higher rows = higher priority)
- **Status** = one of: `todo`, `in-progress`, `review`, `done`, `blocked`
- Assignment not tracked (solo developer)

### 5.2 Epic Files (`doc/planning/epics/`)

Each epic folder is named `<EPIC-ID>--<slug>/` containing:

- `<EPIC-ID>--<slug>.md` — Epic overview (goals, scope, success criteria)
- Individual work item files (`STORY-1--slug.md`, etc.) — description, acceptance criteria

### 5.3 Archiving

When approximately 20 items are `done`, the completed items (excluding the last sprint's work) are moved to `doc/planning/archive/` to keep the main backlog lean.

---

## 6. Branch Naming Convention

```
feature/{module-id}-{kebab-name}
```

Examples:
- `feature/070-property-model`
- `feature/060-scrapper-base-pipeline`
- `feature/080-api-properties-endpoint`

See `doc/guides/unified-change-convention-tracker-agnostic-specification.md` for details.

---

## 7. Sprints

This project does **not** use strict sprints. Work items are prioritized in the backlog table and picked up in order. The sprint plan in `specs/160-SPRINT-PLAN.md` is a rough roadmap, not a schedule.

---

## 8. Estimation

This project does **not** use story points or estimation. Work items are ordered by priority only.

---

## 9. Quality Gates

Before marking a work item as `done`, verify:

- Code lints with `ruff check .`
- Type checks with `mypy . --strict`
- Tests pass with `pytest tests/ -v --cov=. --cov-fail-under=80`
- All spec acceptance criteria are met
- Verification checklist in `AGENTS.md` section 11 is complete

---

## 10. Multi-Repo Coordination

Not yet applicable — all code lives in this repo for now. If future repos are split out, use `todo-<repo>` / `done-<repo>` labels to track cross-repo work.
