# Train Group Schedule — API Reference for Orochi-UI

> Backend version: `prabal-is-testing` branch, commit `eac430ff7` (or later)
> All endpoints documented here are live in `cvat/apps/custom/`.

## Base URL & Auth

- **Base:** `https://your-cvat-host/api/custom/`
- **Auth:** Same as the rest of CVAT — Token (Authorization header), Session cookie, or Basic. Existing Angular auth wrapper works as-is.
- **Permissions:**
  - **Read** (list/template/export/group field on tasks): any authenticated user.
  - **Write** (upload, rollback) + **version history** access: `is_staff=True` (Django admin). Easy to swap to a CVAT IAM group later — single constant on the backend.

## Error format (all endpoints)

```json
{
  "errors": [
    { "line": 14, "reason": "train_id contains invalid characters (allowed: A-Z a-z 0-9 _ -)", "train_id": "3101 F" }
  ]
}
```
- `line: 0` indicates a file-level error (wrong format, too big, non-UTF-8).
- For unauthorized requests: standard DRF `{"detail": "..."}` body.

---

# Section 1 — Endpoints YOU CALL FROM ANGULAR

## 1.1 `GET /api/custom/train-groups/mappings/`

List the current `train_id → group` mapping. Paginated.

**Query params:**
- `search` (string, optional) — substring match on `train_id` OR `group`.
- `group` (string, optional) — exact match on group name.
- `page` (int, default 1)
- `page_size` (int, default 50, max 500)

**Response 200:**
```json
{
  "count": 72,
  "next": "?page=2",
  "previous": null,
  "results": [
    {
      "train_id": "3101F",
      "group": "A",
      "updated_by_username": "alice",
      "updated_at": "2026-05-24T11:42:31.123456Z"
    },
    ...
  ]
}
```

**Use in Angular:**
```ts
this.http.get<MappingPage>('/api/custom/train-groups/mappings/', {
  params: { search: '3101', page: '1', page_size: '50' }
});
```

---

## 1.2 `GET /api/custom/train-groups/mappings/template.csv`

Returns a starter CSV file admins can download, edit, and re-upload.

**Response 200:**
- `Content-Type: text/csv`
- `Content-Disposition: attachment; filename="train_group_template.csv"`
- Body:
  ```csv
  train_id,group
  3101F,A
  3102F,B
  3103F,C
  ```

**Use in Angular:**
```html
<a href="/api/custom/train-groups/mappings/template.csv" download>Download template</a>
```
(Standard `<a download>` — no JS needed.)

---

## 1.3 `GET /api/custom/train-groups/mappings/export.csv`

Returns the **current** mapping as a downloadable CSV (round-trip with the template format).

**Response 200:** same headers as template; body is the live data:
```csv
train_id,group
3101F,A
3102F,A
3121F,A
...
```

**Use in Angular:**
```html
<a href="/api/custom/train-groups/mappings/export.csv" download>Export current schedule</a>
```

---

## 1.4 `POST /api/custom/train-groups/mappings/upload/` 🔒 admin only

Upload a new mapping. **Replaces the entire schedule.** Three input modes — pick one:

### Mode A: CSV file (multipart)
```ts
const fd = new FormData();
fd.append('file', csvFile, 'schedule.csv');  // csvFile: File or Blob
fd.append('comment', 'Tuesday slot added');
fd.append('dry_run', 'false');  // omit or set to true to preview without applying
this.http.post('/api/custom/train-groups/mappings/upload/', fd);
```

### Mode B: Excel file (multipart, .xlsx)
Same as CSV but file extension must end in `.xlsx`. First sheet is read.
```ts
const fd = new FormData();
fd.append('file', xlsxFile, 'schedule.xlsx');
```

### Mode C: Pasted from Excel (JSON)
```ts
this.http.post('/api/custom/train-groups/mappings/upload/', {
  text: "3101F\tA\n3102F\tB\n3103F\tA\n",  // tab-separated (Excel clipboard default)
  comment: 'pasted from Tuesday meeting',
  dry_run: false
});
```

### Response 200 (success or dry-run):
```json
{
  "version": 18,                  // null if dry_run=true
  "diff": {
    "added":   [{ "train_id": "3104F", "group": "A" }],
    "removed": [{ "train_id": "9999Z", "group": "X" }],
    "changed": [{ "train_id": "3101F", "old_group": "A", "new_group": "B" }],
    "counts":  { "added": 1, "removed": 1, "changed": 1, "unchanged": 69 }
  },
  "warnings": [
    {
      "code": "trains_with_no_tasks",
      "message": "5 trains in CSV have no tasks yet",
      "sample": ["3105F", "3106F", "3107F", "3108F", "3109F"]
    },
    {
      "code": "tasks_becoming_ungrouped",
      "message": "12 tasks will become Ungrouped",
      "sample": ["9999Z", "9998Y"]
    }
  ]
}
```

### Response 400 (validation failure — NO writes happened):
```json
{
  "errors": [
    { "line": 2, "reason": "train_id is empty", "train_id": "" },
    { "line": 14, "reason": "train_id contains invalid characters (allowed: A-Z a-z 0-9 _ -)", "train_id": "3101 F" },
    { "line": 22, "reason": "duplicate train_id (first seen on line 5)", "train_id": "3101F" }
  ]
}
```

### Response 403:
User is not `is_staff`.

### UX pattern (recommended):
1. User picks file or pastes text + writes comment.
2. Frontend submits with `dry_run: true` first.
3. Show the **Preview** screen: counts (Added 5 · Changed 2 · Removed 3 · Unchanged 62) + warnings + the changed/removed lists.
4. User clicks **Apply** → frontend re-submits with `dry_run: false`.
5. Success → refresh the schedule view and the version history.

### Limits
- File: max **5 MB**, max **50,000 rows**.
- Pasted text: max **1 MB**.

---

## 1.5 `GET /api/custom/train-groups/versions/` 🔒 admin only

Paginated version history (newest first).

**Query params:** `page`, `page_size` (same as 1.1).

**Response 200:**
```json
{
  "count": 18,
  "results": [
    {
      "version_no": 18,
      "uploaded_by_username": "alice",
      "uploaded_at": "2026-05-24T11:42:31.123456Z",
      "comment": "Added Tuesday slot",
      "source_format": "csv",     // "csv" | "xlsx" | "paste" | "rollback"
      "row_count": 72,
      "is_current": true,
      "source_version": null,     // version_no of rollback source, if any
      "counts": { "added": 1, "removed": 0, "changed": 0, "unchanged": 71 }
    },
    {
      "version_no": 17,
      "uploaded_by_username": "bob",
      "uploaded_at": "2026-05-23T09:11:08.000000Z",
      "comment": "",
      "source_format": "xlsx",
      "row_count": 71,
      "is_current": false,
      "source_version": null,
      "counts": { "added": 5, "removed": 2, "changed": 0, "unchanged": 64 }
    },
    ...
  ]
}
```

Use this to render the **Version History** table on the admin page.

---

## 1.6 `GET /api/custom/train-groups/versions/<version_no>/` 🔒 admin only

Single version with full detail — used for the "View diff" modal.

**Response 200:**
```json
{
  "version_no": 18,
  "uploaded_by_username": "alice",
  "uploaded_at": "2026-05-24T11:42:31.123456Z",
  "comment": "Added Tuesday slot",
  "source_format": "csv",
  "row_count": 72,
  "is_current": true,
  "source_version": null,
  "counts": { "added": 1, "removed": 0, "changed": 0, "unchanged": 71 },
  "csv_text": "train_id,group\n3101F,A\n3102F,A\n...",       // full original CSV
  "diff_summary": {                                          // full diff payload (same shape as upload response)
    "added":   [{ "train_id": "3104F", "group": "A" }],
    "removed": [],
    "changed": [],
    "counts":  { "added": 1, "removed": 0, "changed": 0, "unchanged": 71 }
  }
}
```

**Response 404:** version_no doesn't exist.

---

## 1.7 `POST /api/custom/train-groups/versions/<version_no>/rollback/` 🔒 admin only

Re-apply a past version. **Creates a new version** with the rolled-back mapping; previous versions are never mutated.

**Request:**
```json
{ "comment": "back to v17 — Tuesday slot was wrong" }    // body optional; defaults to "Rollback to v<n>"
```

**Response 200:**
```json
{
  "version": 19,           // newly created version_no
  "source_version": 17,    // the version we rolled back to
  "diff": { ... }          // diff vs the state just before this rollback (same shape)
}
```

**Response 404:** source version_no doesn't exist.

### UX:
Confirm dialog: *"Roll back to v17 (Bob, 2026-05-23)? This creates v19 with the same mapping as v17. Current v18 stays in history."*

---

# Section 2 — Existing endpoints, NEW fields

These three endpoints **already exist** and your Angular app already calls them. They now have two additions:

## 2.1 `GET /api/custom/tasks-paginated/`

### New query param: `group`
- `?group=A` — only tasks whose `train_id` maps to group A.
- `?group=__ungrouped__` — only tasks whose `train_id` has no mapping (or whose train_id isn't in the current schedule).

### New field on every result row: `group`
```json
{
  "results": [
    {
      "task_id": 1763,
      "task_name": "T051763",
      "status": "annotation",
      "group": "A",                  // ⬅ NEW: string or null
      "train_metadata": { ... },
      "annotation_stats": { ... },
      ...
    }
  ]
}
```

### Angular wiring:
- Add a new `Group` column to the dashboard table next to `Train ID`.
- Add a `GROUP` filter dropdown — populate from `available_groups` on `tasks-summary/` (see 2.2). Selecting `A` appends `&group=A` to the existing call.
- Special option `Ungrouped` → send `group=__ungrouped__`.

---

## 2.2 `GET /api/custom/tasks-summary/`

### New query param: `group` (same semantics as 2.1)
Scopes the Verdicts cards (Total / Accepted / Rejected / Not Annotated) to the selected group.

### New field in response: `available_groups`
```json
{
  "total_tasks": 4,
  "verdict_counts": { "AC": 0, "RJ": 0, "NA": 4 },
  ...
  "available_groups": [             // ⬅ NEW
    { "name": "A", "count": 12 },
    { "name": "B", "count": 8 },
    { "name": "C", "count": 5 }
  ]
}
```

- `count` = number of tasks whose `train_id` maps to that group (totals across **all** tasks, NOT scoped to the current `?group=` filter — so the dropdown always shows every option with its full count).
- Counts respect other filters (date range, project, etc.).
- Empty groups (no tasks) are omitted.

### Angular wiring:
On dashboard load, the existing `tasks-summary` call now also gives you the data needed to populate the filter dropdown — **no extra HTTP call**.

---

## 2.3 `GET /api/custom/tasks-extended/<task_id>` (task detail)

> ⚠️ **No trailing slash** — the router uses `trailing_slash=False`.

### New field in response: `group`
```json
{
  "id": 1763,
  "name": "T051763",
  "owner": { "id": 4, "username": "alice", ... },
  "train_metadata": { "train_id": "3101F", "verdict": "NA", ... },
  "train_id": "3101F",
  "group": "A",                     // ⬅ NEW: string or null
  "has_train_metadata": true,
  ...
}
```

### Angular wiring:
On the task detail page, render `Group: A` (chip) next to `Train ID` and `Verdict`. If `group === null`, render `"Not assigned to a group"`.

---

# Section 3 — TypeScript types

Drop these into your Angular project (e.g., `train-group.types.ts`):

```ts
// === Mapping ===
export interface TrainGroupMapping {
  train_id: string;
  group: string;
  updated_by_username: string | null;
  updated_at: string;  // ISO 8601
}

// === Paginated response wrapper (matches DRF default) ===
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// === Diff ===
export interface DiffSummary {
  added: Array<{ train_id: string; group: string }>;
  removed: Array<{ train_id: string; group: string }>;
  changed: Array<{ train_id: string; old_group: string; new_group: string }>;
  counts: { added: number; removed: number; changed: number; unchanged: number };
}

// === Version ===
export type SourceFormat = 'csv' | 'xlsx' | 'paste' | 'rollback';

export interface VersionListItem {
  version_no: number;
  uploaded_by_username: string | null;
  uploaded_at: string;
  comment: string;
  source_format: SourceFormat;
  row_count: number;
  is_current: boolean;
  source_version: number | null;
  counts: { added: number; removed: number; changed: number; unchanged: number };
}

export interface VersionDetail extends VersionListItem {
  csv_text: string;
  diff_summary: DiffSummary;
}

// === Upload ===
export interface UploadWarning {
  code: 'trains_with_no_tasks' | 'tasks_becoming_ungrouped';
  message: string;
  sample: string[];
}

export interface UploadResponse {
  version: number | null;   // null when dry_run=true
  diff: DiffSummary;
  warnings: UploadWarning[];
}

export interface ValidationErrorItem {
  line: number;
  reason: string;
  train_id?: string;
}

export interface ValidationErrorResponse {
  errors: ValidationErrorItem[];
}

// === Tasks-summary additions ===
export interface AvailableGroup {
  name: string;
  count: number;
}
```

---

# Section 4 — Angular service skeleton

```ts
import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class TrainGroupService {
  private base = '/api/custom/train-groups';

  constructor(private http: HttpClient) {}

  listMappings(opts: { search?: string; group?: string; page?: number; pageSize?: number } = {}):
      Observable<PaginatedResponse<TrainGroupMapping>> {
    let params: any = {};
    if (opts.search)   params.search    = opts.search;
    if (opts.group)    params.group     = opts.group;
    if (opts.page)     params.page      = opts.page.toString();
    if (opts.pageSize) params.page_size = opts.pageSize.toString();
    return this.http.get<PaginatedResponse<TrainGroupMapping>>(`${this.base}/mappings/`, { params });
  }

  /** Direct download URL — use with <a download> instead of HttpClient if possible. */
  templateUrl(): string { return `${this.base}/mappings/template.csv`; }
  exportUrl():   string { return `${this.base}/mappings/export.csv`; }

  uploadFile(file: File, comment = '', dryRun = false): Observable<UploadResponse> {
    const fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('comment', comment);
    if (dryRun) fd.append('dry_run', 'true');
    return this.http.post<UploadResponse>(`${this.base}/mappings/upload/`, fd);
  }

  uploadPasted(text: string, comment = '', dryRun = false): Observable<UploadResponse> {
    return this.http.post<UploadResponse>(`${this.base}/mappings/upload/`,
      { text, comment, dry_run: dryRun });
  }

  listVersions(opts: { page?: number; pageSize?: number } = {}):
      Observable<PaginatedResponse<VersionListItem>> {
    let params: any = {};
    if (opts.page)     params.page      = opts.page.toString();
    if (opts.pageSize) params.page_size = opts.pageSize.toString();
    return this.http.get<PaginatedResponse<VersionListItem>>(`${this.base}/versions/`, { params });
  }

  getVersion(versionNo: number): Observable<VersionDetail> {
    return this.http.get<VersionDetail>(`${this.base}/versions/${versionNo}/`);
  }

  rollback(versionNo: number, comment?: string):
      Observable<{ version: number; source_version: number; diff: DiffSummary }> {
    return this.http.post<any>(`${this.base}/versions/${versionNo}/rollback/`,
      comment ? { comment } : {});
  }
}
```

---

# Section 5 — Notes & gotchas

1. **URL prefix is `/api/custom/`**, NOT `/api/`. Easy mistake — the existing `tasks-paginated/`, `tasks-summary/`, `tasks-extended/` are all under `/api/custom/`.
2. **`tasks-extended/<id>` has NO trailing slash** (router uses `trailing_slash=False`). Adding `/` returns 404. The other train-group routes DO use trailing slashes.
3. **Upload semantics: replace-all.** Anything not in the uploaded CSV becomes "Ungrouped." Use the dry-run preview every time.
4. **Versions are immutable.** Rollback creates a NEW version that happens to equal an old one — past versions are never edited.
5. **`group` is free text** — case-sensitive. `"A"` and `"a"` are distinct groups. Frontend should not auto-normalize.
6. **Ungrouped sentinel**: send `?group=__ungrouped__` (two underscores either side) — never URL-encode the underscores.
7. **Permissions are deferred**: currently `is_staff` (Django admin). If you need a custom CVAT IAM group later, it's a one-line backend change. Plan for the frontend to gracefully degrade — show the Train Schedule menu item only if the user has `is_staff`.

---

# Section 6 — Sequence diagrams (for the admin Train Schedule page)

### Upload + preview + apply

```
Admin              Angular              Backend
  |                  |                    |
  | pick file        |                    |
  |─────────────────>|                    |
  | click Preview    |                    |
  |─────────────────>|                    |
  |                  | POST /upload/      |
  |                  |   dry_run=true     |
  |                  |───────────────────>|
  |                  |        200 + diff  |
  |                  |<───────────────────|
  | review counts +  |                    |
  | warnings         |                    |
  | click Apply      |                    |
  |─────────────────>|                    |
  |                  | POST /upload/      |
  |                  |   dry_run=false    |
  |                  |───────────────────>|
  |                  |   200 + version 19 |
  |                  |<───────────────────|
  | success toast    |                    |
  | refresh tables   |                    |
```

### Rollback

```
Admin              Angular              Backend
  |                  |                    |
  | click Rollback   |                    |
  | on v17 row       |                    |
  |─────────────────>|                    |
  | confirm dialog   |                    |
  |─────────────────>|                    |
  |                  | POST /versions/17/ |
  |                  |   rollback/        |
  |                  |───────────────────>|
  |                  |    200 + version=  |
  |                  |    20, source=17   |
  |                  |<───────────────────|
  | refresh history  |                    |
```
