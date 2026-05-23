# Train Group Schedule Mapping — Design

**Status:** Draft for review
**Author:** prabal
**Date:** 2026-05-24
**Scope:** `cvat/apps/custom/` only — no changes to upstream CVAT modules

---

## 1. Summary

Introduce a schedule that maps each `train_id` to a single group (e.g., `A`, `B`, `C`). Admins update the schedule by uploading a CSV, uploading an Excel `.xlsx` file, or pasting rows directly from Excel. Every change is versioned with a full audit trail and exposed throughout the dashboard so users can filter and view tasks by group.

The mapping is a property of the **train**, not the task. Many tasks can share one train_id; uploading a CSV does not touch task records.

---

## 2. Background

The annotation workflow is organised around a recurring train-inspection schedule (the `列検回帰※9日` table). Each train belongs to a group on that schedule. Today CVAT has no concept of "group" — annotators and reviewers cannot filter the dashboard or task list by their group, and there is no source of truth for which trains belong to which group.

The schedule is currently maintained in an external spreadsheet, edited by a small set of admins, and changes periodically.

---

## 3. Goals

- **G1.** Admins can upload a CSV that defines the `train_id → group` mapping.
- **G2.** Uploads are versioned; every upload stores the original CSV, who uploaded it, when, and a diff vs the previous version. Admins can roll back to any past version.
- **G3.** Every task in the dashboard shows its group. The dashboard table and task detail page surface the group.
- **G4.** Users can filter the dashboard task list and Verdicts cards by group, including an `Ungrouped` bucket for tasks whose train_id has no mapping.
- **G5.** Lookup performance is constant per list request (no N+1; single JOIN/annotation per query).

## 4. Non-goals

- Excel (`.xlsx`) upload — CSV only. Admins save-as CSV from Excel.
- Inline single-row editing in the admin UI — CSV is the editing mechanism for v1.
- Group metadata beyond a name (no description/color/icon).
- Group hierarchy or sub-groups — flat string namespace.
- Per-organization or multi-tenant schedules — single global schedule per CVAT instance.
- Automatic import from an external system — manual CSV upload only.
- Soft-delete of old versions — versions are kept forever (data is tiny).
- Changing where train_id originates — it remains the `train_id` field on `TaskTrainMetadata`.

---

## 5. Key decisions (captured from brainstorming)

| Question | Decision |
|---|---|
| Group semantics | One free-text group name per train (e.g., `A`). One train belongs to exactly one group. Many trains per group. |
| Input format | Long format, two columns: `train_id,group`. One row per train. Accepted as **CSV file**, **`.xlsx` file** (first sheet), or **pasted text** (tab- or comma-separated). All three paths run through the same parser → same validation → same diff → same versioning. |
| Upload semantics | **Replace all** (full sync). Anything not in the CSV becomes Ungrouped. Versioning + rollback covers mistakes. |
| Edit UX | CSV upload + read-only paginated table in admin UI. No inline edits. |
| Permissions | Deferred. Centralised in one constant (`MAPPING_ADMIN_PERMISSIONS`), defaulting to Django `is_staff`/superuser. Easy to swap to a custom Group or CVAT IAM later. |
| Unmapped tasks | Shown as `Ungrouped`. Frontend offers explicit `Ungrouped` filter option. |
| Storage model | **Approach A** — separate `TrainGroupMapping` table (current state) + `TrainGroupMappingVersion` table (immutable snapshots). Joined via `train_id`. |
| Lookup mechanism | Subquery annotation on the existing `tasks-paginated/`, `tasks-summary/`, `tasks-extended/` querysets. One extra JOIN per list call, indexed PK lookup. |
| Group list for filter dropdown | Folded into the existing `tasks-summary/` response as `available_groups: [{name, count}, ...]`. No extra round-trip. |
| Audit | Each version row stores `csv_text` + computed `diff_summary` JSON (added/removed/changed/counts). |

---

## 6. Data model

Two new models in `cvat/apps/custom/models.py`.

### 6.1 `TrainGroupMapping`

Current source of truth for which group each train_id belongs to. One row per train. Fully rebuilt on every CSV upload (inside a transaction).

```python
class TrainGroupMapping(models.Model):
    train_id = models.CharField(max_length=100, primary_key=True)
    group = models.CharField(max_length=50, db_index=True)
    updated_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL,
        related_name="train_group_mappings_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "custom_train_group_mapping"
        indexes = [models.Index(fields=["group", "train_id"])]
```

### 6.2 `TrainGroupMappingVersion`

Immutable snapshot of each upload (or rollback). Exactly one row has `is_current=True` at any time.

```python
class TrainGroupMappingVersion(models.Model):
    version_no = models.PositiveIntegerField(unique=True)  # monotonic 1,2,3...
    uploaded_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL,
        related_name="train_group_mapping_versions",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    comment = models.CharField(max_length=500, blank=True)
    csv_text = models.TextField()           # canonical CSV form (UTF-8) —
                                            # xlsx uploads are normalized to CSV
                                            # before storing, so every version
                                            # is reproducible as text
    source_format = models.CharField(       # "csv" | "xlsx" | "paste" | "rollback"
        max_length=16, default="csv",
    )
    row_count = models.PositiveIntegerField()
    is_current = models.BooleanField(default=False)
    source_version = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="rollbacks",
    )  # set when this version was created by rolling back to source_version

    diff_summary = models.JSONField(default=dict)
    # {
    #   "added":   [{"train_id": "X", "group": "A"}, ...],
    #   "removed": [{"train_id": "Y", "group": "B"}, ...],
    #   "changed": [{"train_id": "Z", "old_group": "C", "new_group": "D"}, ...],
    #   "counts":  {"added": 12, "removed": 3, "changed": 5, "unchanged": 52}
    # }

    class Meta:
        db_table = "custom_train_group_mapping_version"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="only_one_current_version",
            ),
        ]
```

### 6.3 `TaskTrainMetadata` is untouched

No new field. `group` is exposed via serializer lookup against `TrainGroupMapping` by `train_id`.

### 6.4 Migration

New file: `cvat/apps/custom/migrations/0004_train_group_mapping.py` — creates both tables. No data migration needed; initial state is empty.

---

## 7. Lookup strategy — preventing N+1

A queryset helper, used by every list endpoint that includes `group` in its response:

```python
from django.db.models import Subquery, OuterRef

def annotate_train_group(queryset):
    group_sq = TrainGroupMapping.objects.filter(
        train_id=OuterRef("train_metadata__train_id"),
    ).values("group")[:1]
    return queryset.annotate(train_group=Subquery(group_sq))
```

- One SQL statement per list call regardless of page size
- Indexed PK lookup on `TrainGroupMapping.train_id`
- Measured cost expected to be sub-millisecond at our scale

A CI test (`CaptureQueriesContext`) asserts the dashboard list endpoint stays at its current query count + 1 after the change.

---

## 8. API surface

### 8.1 Changes to existing endpoints

| Endpoint | Change |
|---|---|
| `GET /api/tasks-paginated/` | New query param `?group=<name>` and `?group=__ungrouped__`. Each row in `results` gains a `group: string \| null` field. |
| `GET /api/tasks-summary/` | New query param `?group=<name>`. Response gains `available_groups: [{name: string, count: number}]` listing every known group with the total number of tasks whose `train_id` maps to that group. **The list and counts are independent of the current `?group=` filter** so the filter dropdown always shows every option. Counts do respect the other filters (date range etc.) so they reflect what the user would see after switching groups. |
| `GET /api/tasks-quick-stats/` | Accepts `?group=<name>` (optional). |
| `GET /api/tasks-extended/<id>/` | Response gains a `group: string \| null` field. |

### 8.2 New endpoints (admin schedule manager only)

Base path: `/api/train-groups/`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `mappings/` | Any auth user | Paginated current mappings. Query: `?search=` (matches train_id or group), `?group=`, `?page=`, `?page_size=`. |
| `GET` | `mappings/template.csv` | Any auth user | Downloads a blank CSV with header + a few example rows. |
| `GET` | `mappings/export.csv` | Any auth user | Downloads the current mapping as CSV (round-trip with template format). |
| `POST` | `mappings/upload/` | `MAPPING_ADMIN` | Accepts: multipart `file` (`.csv` or `.xlsx`) + optional `comment` + optional `dry_run`; **or** JSON `{text, comment, dry_run}` for pasted-from-Excel. Returns `{version, diff, warnings}`. |
| `GET` | `versions/` | `MAPPING_ADMIN` | Paginated audit list (version_no, uploaded_by, uploaded_at, comment, counts, is_current). |
| `GET` | `versions/<id>/` | `MAPPING_ADMIN` | Full version detail: `csv_text` + `diff_summary`. |
| `POST` | `versions/<id>/rollback/` | `MAPPING_ADMIN` | Re-apply that version. Body: optional `comment`. Creates a new version with `source_version=<id>` set. |

All new view code lives in a new file `cvat/apps/custom/views_train_groups.py`. Routes registered in `cvat/apps/custom/urls.py`.

### 8.3 Permission constant

In `views_train_groups.py`:

```python
MAPPING_ADMIN_PERMISSIONS = [permissions.IsAdminUser]
# DRF's IsAdminUser passes when user.is_staff is True. Superusers created
# via `createsuperuser` are also is_staff, so both groups pass.
```

Every write endpoint references this constant. Swapping to a custom group/IAM check later is a one-line change.

---

## 9. Input formats & validation

### 9.1 Three accepted input modes (one parser)

All three paths normalize to the same internal `list[ParsedRow]`, then run through the same validation, diff computation, and apply step.

**Mode A — CSV file (`.csv`)**
```csv
train_id,group
3101F,A
3102F,B
3103F,A
```

**Mode B — Excel file (`.xlsx`)**
- Read the **first sheet** via `openpyxl`
- Same two-column schema: header row `train_id,group`, then data
- Empty trailing rows tolerated
- Other sheets in the workbook are ignored (workbook with hidden working sheets is fine)
- `openpyxl` is added to `requirements/base.txt` (used elsewhere in the Python data ecosystem; ~600 KB; pure Python, no native deps)

**Mode C — Paste from Excel (textarea)**
- Frontend posts the pasted text directly
- Parser auto-detects separator: tab if any line contains `\t`, otherwise comma
- Excel's clipboard format is tab-separated by default → "select two columns, copy, paste" just works
- Header row optional in this mode (we accept either with or without header for convenience; if first line looks like data, treat it as data)

### 9.2 Common validation rules (apply to all modes)

- UTF-8, optional BOM tolerated (CSV/paste)
- For CSV/xlsx: header row required, exactly `train_id,group` (case-sensitive)
- Extra columns are ignored silently (forward compatibility)
- Trailing blank rows/lines tolerated
- `train_id`: non-empty, max 100 chars, regex `^[A-Za-z0-9_-]+$` (whitespace trimmed first)
- `group`: non-empty, max 50 chars (whitespace trimmed first)
- Duplicate `train_id` within a file → rejection with line/row numbers
- Empty input (header only / blank paste) → accepted as "clear all", flagged with a large warning in dry-run

### 9.3 Parser module

`cvat/apps/custom/train_group_parser.py` — no Django imports beyond `transaction`:

```python
def parse_csv(text: str) -> tuple[list[ParsedRow], list[ValidationError]]
def parse_xlsx(file_bytes: bytes) -> tuple[list[ParsedRow], list[ValidationError]]
def parse_pasted(text: str) -> tuple[list[ParsedRow], list[ValidationError]]
    # Auto-detects \t vs , separator; tolerates missing header

def compute_diff(new_rows, current_mapping_qs) -> DiffSummary
def apply_upload(rows, user, comment, raw_input_text: str,
                 source_format: str, source_version=None) -> Version
```

`raw_input_text` is what we store in `TrainGroupMappingVersion.csv_text` — for .xlsx uploads we normalize to CSV first (so the stored snapshot is always reproducible as text). `source_format` (one of `"csv"`, `"xlsx"`, `"paste"`) is also stored on the version for the audit log.

### 9.4 Limits

- Max file size: 5 MB (raised slightly to accommodate Excel files with formatting overhead)
- Max rows: 50,000 (configurable via Django setting `TRAIN_GROUP_MAX_ROWS`)
- Pasted text capped at 1 MB to keep request bodies sane

---

## 10. Upload flow

The same endpoint accepts all three input modes — the request body shape tells us which:

```
POST /api/train-groups/mappings/upload/
  # Mode A — CSV file:
  multipart: file=<file.csv>, comment="<optional>", dry_run=<bool, default false>

  # Mode B — Excel file:
  multipart: file=<file.xlsx>, comment="<optional>", dry_run=<bool>
  # (file extension + magic-byte check determines parser)

  # Mode C — Pasted text:
  application/json: {"text": "<pasted text>", "comment": "<optional>", "dry_run": <bool>}
```

1. **Detect mode & parse** in memory: dispatch to `parse_csv` / `parse_xlsx` / `parse_pasted`. If any row error, return `400` with `{errors: [{line, train_id, reason}, ...]}` and apply nothing.
2. **Compute diff** vs `TrainGroupMapping` (added / removed / changed / unchanged).
3. **Generate warnings** (non-blocking):
   - Train IDs in CSV with no matching `TaskTrainMetadata` ("N trains in CSV have no tasks yet")
   - Train IDs being dropped that have existing tasks ("N tasks will become Ungrouped")
4. **If `dry_run=true`**: return diff + warnings, no writes.
5. **Apply** inside `transaction.atomic()`:
   - `TrainGroupMappingVersion.objects.filter(is_current=True).update(is_current=False)`
   - `TrainGroupMappingVersion.objects.create(...new version, is_current=True, diff_summary=...)`
   - `TrainGroupMapping.objects.all().delete()`
   - `TrainGroupMapping.objects.bulk_create([...], batch_size=1000)`
6. Return `{version, diff_summary, warnings}`.

Concurrent uploads serialised via a row-level lock on `TrainGroupMappingVersion`. Second concurrent uploader receives `409 Conflict` with a clear message.

---

## 11. Rollback flow

```
POST /api/train-groups/versions/42/rollback/
  body: {"comment": "<optional, defaults to 'Rollback to v42'>"}
```

Parses `version_42.csv_text` and runs the same upload flow with `source_version=42` set on the new version. Past versions are never mutated. Result: a new version `vN+1` whose mapping equals `v42`'s mapping, traceable in audit.

---

## 12. Frontend changes

Three surfaces. The first two are additive changes to existing screens; only the third is a new page.

### 12.1 Dashboard (existing)

- **`Group` column** in the task table, inserted right after `TRAIN ID`. Rendered as a neutral chip matching the existing badge style. Null mappings render as a muted `—`.
- **`GROUP` filter dropdown** next to the existing `FILTER BY`. Options populated from `available_groups` on `tasks-summary/`. Each option shows `{name} ({count})`. Pseudo-options at top: `All`, `Ungrouped` (sent as `?group=__ungrouped__`).
- Selecting a group calls the same `tasks-paginated/` and `tasks-summary/` with `&group=...`. Verdicts cards automatically reflect the scope.
- No new API calls beyond the existing two.

### 12.2 Task detail (existing)

- Add a `Group` field to the task header alongside `Train ID` / `Verdict`. Renders as a chip when mapped, "Not assigned to a group" when null.
- Source: existing `tasks-extended/<id>/` response now includes `group`.

### 12.3 NEW page — `Train Schedule` (admin)

Route: `/train-groups` (frontend). Sidebar entry visible only to `MAPPING_ADMIN` users. Suggested icon: calendar/schedule glyph.

Two main cards:

**Current Schedule card**
- Header: active version metadata (`v18 · uploaded by alice · 2026-05-24 18:42 · 72 trains · "Added Tuesday slot"`)
- Search box (filters by train_id or group)
- `Export CSV` link
- Paginated table: `TRAIN ID | GROUP`
- Empty state when no version exists: "No schedule uploaded yet" + `[Download template]` `[Upload]`

**Version History card**
- Reverse-chronological list of versions
- Each row: `v{n}  USER  TIMESTAMP  "{comment}"  +added ~changed -removed  [View] [Rollback (if not current)]`
- `View` → modal with full diff + collapsible raw CSV
- `Rollback` → confirmation dialog: "Roll back to v17 (Bob, 2026-05-23)? This will create v19 with the same mapping as v17. Current v18 will remain in history."

**Upload dialog** — three input modes via tabs:

```
┌─ Update schedule ─────────────────────────────────────────────┐
│ [ Upload file ]  [ Paste from Excel ]                         │
│                                                               │
│ (Upload file tab)                                             │
│   Drop a .csv or .xlsx file here, or [Choose file]            │
│   Accepted: .csv, .xlsx                                       │
│                                                               │
│ (Paste from Excel tab)                                        │
│   Copy two columns (train_id, group) from Excel and paste:    │
│   ┌────────────────────────────────────────────────┐          │
│   │ 3101F<TAB>A                                    │          │
│   │ 3102F<TAB>B                                    │          │
│   │ ...                                            │          │
│   └────────────────────────────────────────────────┘          │
│                                                               │
│ Comment (optional): [_____________________________]           │
│                                                               │
│                                  [Cancel]  [Preview changes]  │
└───────────────────────────────────────────────────────────────┘
```

- "Upload file" tab: file picker accepts `.csv` and `.xlsx`. File extension determines parser.
- "Paste from Excel" tab: large textarea; user pastes copied cells (Excel's clipboard format is tab-separated by default, so this just works).
- Optional `Comment` field shared by both tabs.
- On submit, first calls `?dry_run=true` and shows preview screen with counts (Added / Changed / Removed / Unchanged), expandable lists, and warnings.
- User clicks `Apply` → second call without `dry_run` → success → both cards refresh.

**Validation error display**
- If upload returns 400 with row-level errors, render a scrollable list inside the dialog (`Line 14: invalid train_id "3101 F" (whitespace not allowed)`).

**Visual language**
- Match the existing dashboard: light gray background, white cards with subtle shadow, dark sidebar, neutral chips
- Reuse existing button styles (primary dark, secondary outlined)
- Reuse the dashboard's pagination control

---

## 13. Edge cases

| Scenario | Behavior |
|---|---|
| Duplicate train_id in uploaded CSV | Reject with line numbers |
| Empty CSV (header only) | Accepted = "clear schedule", large warning in dry-run |
| Whitespace/BOM in cells | Stripped silently |
| Group case differences (`A` vs `a`) | Treated as different groups (no auto-normalization) |
| Train_id with no `TaskTrainMetadata` | Mapping stored; warning issued |
| Task whose train_id is dropped | Task becomes Ungrouped; warning lists count |
| Concurrent uploads | Second one returns 409 with "another upload in progress" |
| Rollback to v0 / empty | Allowed; wipes mapping |
| `?group=A` with no mapping | Returns empty page, not 500 |
| `?group=__ungrouped__` | Returns tasks with no mapping row |
| User deleted that uploaded a version | `uploaded_by` becomes NULL; version still readable |
| Non-UTF-8 CSV | 400 with clear error |
| File over 50,000 rows | 400; limit configurable |
| `.xlsx` with multiple sheets | Only the first sheet is read; others ignored silently (admins may keep working sheets in the workbook) |
| `.xlsx` with merged cells in the data range | Reject with 400 — "merged cells in data area not supported" |
| `.xlsx` with formulas instead of values | Read the cached value (`openpyxl` default behavior); if no cached value (file never opened in Excel), reject with clear error |
| Pasted text with no separator detected | Reject — "could not detect column separator; ensure two columns" |
| Pasted text with only one column | Reject — "expected two columns (train_id and group)" |

---

## 14. Testing

**Unit** (`cvat/apps/custom/tests/test_train_group_parser.py`)
- `parse_csv`: happy path, missing header, duplicate train_id, whitespace/BOM, case sensitivity, max rows, non-UTF-8, ignored extra columns
- `parse_xlsx`: happy path, first-sheet-only behavior, merged-cells rejection, formula-cached-value reading, formula-with-no-cache rejection
- `parse_pasted`: tab-separated happy path, comma-separated fallback, with-and-without-header tolerance, no-separator rejection, one-column rejection
- All three parsers produce identical `ParsedRow` output for the same logical data — assert byte-for-byte equality
- `compute_diff`: across base states (empty / populated / subset / superset)

**Integration** (`cvat/apps/custom/tests/test_train_group_endpoints.py`)
- Upload happy path for **each input mode**: CSV file, .xlsx file, pasted JSON — all produce the same final state
- `source_format` correctly recorded on `TrainGroupMappingVersion`
- Upload validation failures → 400, no DB writes
- Dry-run → no writes, returns diff
- `mappings/` pagination + search
- `versions/` list and detail
- Rollback creates new version with `source_version` set, mapping reverted
- Permission checks: non-admin → 403 on every write endpoint
- Concurrent uploads → 409

**Filter integration** (extends `cvat/apps/custom/tests.py`)
- `tasks-paginated/?group=A` returns only matching tasks
- `tasks-paginated/?group=__ungrouped__` returns unmapped tasks
- `tasks-summary/` includes `available_groups` with correct counts
- `tasks-summary/?group=A` scopes Verdicts counts
- `tasks-extended/<id>/` includes `group`

**Performance regression**
- Create 1,000 tasks + 1,000 mappings, call `tasks-paginated/?page_size=50`, assert query count ≤ baseline + 1 using `CaptureQueriesContext`.

---

## 15. Rollout

1. Deploy code with new models + new endpoints; no UI changes yet — backend ready, no users impacted.
2. Run migration → both new tables created empty.
3. First CSV upload by an admin via API/curl establishes v1.
4. Deploy dashboard + task-detail frontend changes.
5. Deploy admin Train Schedule page.

Each step is independently reversible.

---

## 16. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Admin uploads wrong file, breaks dashboard view | Mandatory dry-run preview before apply; one-click rollback |
| Performance regression from JOIN | Subquery annotation + CI query-count test |
| Format drift (extra columns) | Parser ignores unknown columns; only `train_id,group` required |
| Group dropdown grows long | Searchable dropdown component |
| Two admins overwrite each other | DB lock + 409 response; UI warns "v18 was just uploaded by Bob — refresh?" |
| Permission decision deferred | Centralised constant — one-line change to swap |
| `openpyxl` dependency surface | Pinned version in `requirements/base.txt`; pure-Python with no native deps; battle-tested library |
| `.xlsx` files with formulas not recalculated | Reject with clear "file has unevaluated formulas — open in Excel and save" error |

---

## 17. Open questions (resolve before implementation plan is locked)

- **Permission scope:** default is `is_staff`. Final decision (custom Group? CVAT IAM?) deferred — captured in constant.
- **Sidebar icon choice** for the admin page — visual decision during frontend implementation.
- **Frontend file locations** in CVAT React UI — needs grep during implementation kickoff.

---

## 18. Out of scope (reaffirmed)

- Inline single-row admin edits in UI
- Group metadata beyond name
- Group hierarchy
- Multi-tenant schedules
- Auto-import / Google Sheets sync
- Old-version cleanup
