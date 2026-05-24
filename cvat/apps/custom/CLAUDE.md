# cvat/apps/custom — Guide for Claude (and humans)

> Auto-loaded by any Claude Code session that opens this folder. Read once at session start; mistakes documented here have already happened — don't repeat them.

## Where this app is mounted

**Critical:** all routes registered in `urls.py` are mounted at `/api/custom/` by the project root:

```python
# cvat/urls.py line 60
urlpatterns.append(path("api/custom/", include("cvat.apps.custom.urls")))
```

So a route `path("foo/", ...)` becomes **`/api/custom/foo/`** at runtime, NOT `/api/foo/`. Tests must use `/api/custom/...` URLs; the Angular frontend must too. Verify the include() statement before hard-coding any URL anywhere.

## File inventory (post 2026-05-24 train-group work)

### Models & migrations
- `models.py` — `TaskTrainMetadata`, `TaskComment`, `TrainGroupMapping`, `TrainGroupMappingVersion`
- `migrations/0001_initial.py` — TaskTrainMetadata
- `migrations/0002_taskcomment.py` — TaskComment
- `migrations/0003_tasktrainmetadata_server_files_path.py` — added S3 prefix field
- `migrations/0004_train_group_schedule.py` — TrainGroupMapping + Version + partial unique on is_current

### Pure logic (Django-free, safe to unit-test)
- `train_group_parser.py` — CSV / xlsx / paste parsers, `compute_diff`, `apply_upload` (only the last needs Django)
- `train_group_query.py` — `annotate_train_group`, `filter_by_group`, `UNGROUPED_SENTINEL`

### Serializers (`serializers.py`)
- `TaskTrainMetadataSerializer`, `TaskWithTrainMetadataSerializer`
- `TaskCommentSerializer` family — **excluded from OpenAPI schema** (`TaskCommentAuthor` breaks SDK gen)
- `TrainGroupMappingSerializer`, `TrainGroupMappingVersionListSerializer`, `TrainGroupMappingVersionDetailSerializer`

### Views
| File | Purpose | Schema status | Returns `group`? |
|---|---|---|---|
| `views.py` | Frame downloads | APIView, no schema | n/a |
| `views_optimized.py` | Optimized frame downloads | APIView, no schema | n/a |
| `views_cvat_integrated.py` | Task export, formats list | APIView, no schema | n/a |
| `views_task_analysis.py` | `task-analysis/?task_id=` (used by Task Details page) | APIView, no schema | ✅ `group` in basic_info |
| `views_train_metadata.py` | Original train metadata CRUD | APIView, no schema | ✅ `group` at top level |
| `views_task_extension.py` | `ExtendedTaskViewSet` (DRF router, **no trailing slash**), task-level train metadata APIs | ViewSet — schema-tracked | ✅ `group` in retrieve + list |
| `views_analytics.py` | `tasks-paginated`, `tasks-summary`, `tasks-quick-stats` | APIView | ✅ `group` per row + `available_groups` |
| `views_task_comments.py` | Task comments (existing user code) | **excluded from schema** via `@extend_schema_view(... exclude=True)` | n/a |
| `views_frame_data.py` | Per-frame data | APIView, no schema | n/a |
| `views_s3_videos.py` | S3 video presigned URLs | APIView, no schema | n/a |
| `views_train_groups.py` | **NEW** Train group schedule — mappings list/template/export/upload, versions list/detail/rollback | mixed; CSV-download views excluded via `@extend_schema(exclude=True)` | n/a (it IS the mapping) |

> **Rule of thumb:** any view that returns task-level data with a `train_metadata` field MUST also expose a `group` field. Use direct PK lookup on `TrainGroupMapping.objects.filter(train_id=...).only("group").first()` (cheap, no annotation gymnastics) for single-task endpoints; use `annotate_train_group(queryset)` from `train_group_query.py` for list endpoints (avoids N+1).

### URL routing (`urls.py`)
- `ExtendedTaskViewSet` registered via `DefaultRouter(trailing_slash=False)` → `/api/custom/tasks-extended/<pk>` (NO trailing slash)
- TaskCommentViewSet registered the same way → `/api/custom/comments/<pk>`
- All other routes use trailing slashes

### Tests (`tests/`)
- `test_train_group_parser.py` — 27 tests, pure Python (parsers + dataclasses)
- `test_train_group_diff_apply.py` — Django ORM tests for diff + transactional apply
- `test_train_group_endpoints.py` — DRF APIClient integration tests
- `test_train_group_query.py` — annotate_train_group + filter_by_group, including prefetch_related regression

## Permissions model

Centralized in `views_train_groups.py`:

```python
MAPPING_ADMIN_PERMISSIONS = [permissions.IsAdminUser]   # i.e. user.is_staff
```

All write endpoints (upload, rollback) and admin reads (versions list/detail) use this. Read endpoints (mappings list, template, export) use `[IsAuthenticated]`. **`ExtendedTaskViewSet` extends CVAT's `BaseTaskViewSet`** which enforces the full CVAT IAM stack — non-owners get 403 even if authenticated.

To swap permission scope (e.g., custom Django Group), change that one constant.

## 6 GOTCHAS — every one of these has already bitten us once

### 1. URL prefix must be `/api/custom/`, never `/api/`

```python
# WRONG
client.get('/api/train-groups/mappings/')   # 404

# RIGHT
client.get('/api/custom/train-groups/mappings/')
```

Frontend (Orochi-UI Angular) too. Before writing any new test URL: `grep -n "include.*custom" cvat/urls.py` to confirm the mount.

### 2. `tasks-extended` and `comments` have NO trailing slash

DRF router uses `trailing_slash=False`. Other train-group routes DO use trailing slashes (template.csv, export.csv, upload/, versions/, rollback/).

```python
# WRONG
client.get('/api/custom/tasks-extended/123/')   # 404

# RIGHT
client.get('/api/custom/tasks-extended/123')
```

### 3. DRF APIClient file uploads need `SimpleUploadedFile`

```python
# WRONG — requests library tuple syntax; APIClient silently misinterprets
data={"file": ("schedule.csv", csv_bytes, "text/csv")}

# RIGHT
from django.core.files.uploadedfile import SimpleUploadedFile
data={"file": SimpleUploadedFile("schedule.csv", csv_bytes, content_type="text/csv")}
```

### 4. URLs with file extensions (`.csv`, `.xml`) MUST be excluded from schema

drf-spectacular preserves the dot in operationId (`template.csv`), CVAT's SDK postprocess normalizes dots to underscores during lookup → KeyError → build fails.

```python
class MappingTemplateCsvView(APIView):
    @extend_schema(exclude=True)
    def get(self, request):
        ...
```

If you add a new file-download endpoint, decorate it.

### 5. Never hand-write migration index names

```python
# WRONG
models.Index(fields=["a", "b"], name="custom_xyz_b3e02a_idx")   # made-up hash

# RIGHT
models.Index(fields=["a", "b"])   # let Django auto-name
# OR write migrations only via `python manage.py makemigrations`
```

If you must hand-write one (CI doesn't have Django readily available), accept that `makemigrations --check` may fail on the first CI run with a "Rename index ..." message — fix it by copying Django's expected hash from that message.

### 6. `OuterRef('relation__field')` returns NULL silently with `prefetch_related` — AND nested Subqueries cause type mismatches

Two related traps:

**6a — `OuterRef('rel__field')` is silent NULL when the outer queryset uses `prefetch_related`** (because prefetch doesn't add a JOIN; there's no `rel` to reference in the outer SQL):

```python
# WRONG — silently returns NULL in views that prefetch_related
sq = OtherModel.objects.filter(field=OuterRef('rel__field')).values('x')[:1]
```

**6b — Don't fix it by nesting Subqueries**. `OuterRef("pk")` inside a nested Subquery refers to the IMMEDIATE parent subquery, not the outermost query. If that parent model has a non-integer primary_key (like `TrainGroupMapping.train_id` which is `primary_key=True`), Postgres will throw `operator does not exist: integer = character varying`:

```python
# WRONG — nests OuterRef one level too deep
group_sq = TrainGroupMapping.objects.filter(
    train_id=Subquery(
        TaskTrainMetadata.objects.filter(
            task_id=OuterRef("pk")  # ← "pk" here is TrainGroupMapping.train_id (varchar), NOT Task.pk
        ).values("train_id")[:1]
    )
).values("group")[:1]
queryset.annotate(train_group=Subquery(group_sq))
```

**RIGHT — chain annotations on the OUTER queryset**:

```python
queryset = queryset.annotate(
    _train_id=Subquery(
        TaskTrainMetadata.objects
        .filter(task_id=OuterRef("pk"))  # OuterRef → Task.pk (correct)
        .values("train_id")[:1]
    )
)
queryset = queryset.annotate(
    train_group=Subquery(
        TrainGroupMapping.objects
        .filter(train_id=OuterRef("_train_id"))  # OuterRef → Task._train_id (correct)
        .values("group")[:1]
    )
)
```

Each subquery's OuterRef refers directly to a column on the outer Task query — no nesting, no type drift.

When writing tests for any annotation helper, **always** test it against:
1. A queryset shape mirroring the real view (with `prefetch_related` if used there)
2. The real database backend (Postgres), not just SQLite — SQLite is permissive about cross-type comparisons; Postgres isn't. CI does run Postgres; just make sure the test actually exercises the annotated value.

## The meta-rule under all 6 gotchas

**Test the call site, not the unit.** Every one of the bugs above passed an isolated unit test and then broke when the real view called the helper differently. Before writing a test:
1. Open the file(s) that will call this code
2. Note their queryset shape, URL prefix, request format, permissions wrapping, etc.
3. Make the test mirror that shape — not the minimal repro

## Deployment notes

- Production image is `ghcr.io/prabaljainn/cvat-server:<tag>` (pin via `CVAT_IMAGE_TAG` in `.env`)
- `docker-compose.smtp.yml` overrides `cvat_server.command` — **must end with `exec ./backend_entrypoint.sh run server nginx`**. Forgetting `nginx` = no port 8080 listener = traefik 502
- After modifying anything that affects the OpenAPI schema, run `gh workflow run regenerate-schema.yml --ref <branch>` to update `cvat/schema.yml` before the next Full CI run
- DNS: keep AAAA record DELETED on `okkunsys.tokyu.co.jp` / test domains; Let's Encrypt prefers IPv6 if AAAA exists, will fail if AAAA points elsewhere

## CSV format for train-group schedule

```csv
train_id,group
3101F,A
3102F,B
```

- UTF-8 with optional BOM
- Header row required, exact text `train_id,group` (case-sensitive)
- `train_id`: 1–100 chars, `^[A-Za-z0-9_-]+$` (no spaces — that's what bit our test case)
- `group`: 1–50 chars (case-sensitive: `A` ≠ `a`)
- Duplicate `train_id` in same file → rejected
- Empty body (just header) → accepted as "clear schedule"
- Extra columns silently ignored

xlsx and pasted-from-Excel modes route through the same validator. See `train_group_parser.py`.

## CI workflows (in `.github/workflows/`)

- `full.yml` — `workflow_dispatch`, builds image + runs unit/REST/e2e tests
- `regenerate-schema.yml` — `workflow_dispatch`, pulls GHCR image, runs spectacular, commits `cvat/schema.yml` back to branch. **Run this after any endpoint addition or schema-affecting change before triggering full.yml.**
- `custom-build-push-ghcr.yml` — push trigger on `prabal-is-testing`; builds + pushes server + ui images
- The full CVAT upstream workflows (main.yml etc.) also exist; we use full.yml for our manual validation runs

## Related docs

- `docs/superpowers/specs/2026-05-24-train-group-mapping-design.md` — design rationale + non-goals
- `docs/superpowers/plans/2026-05-24-train-group-mapping-backend.md` — the 20-task TDD plan that built this
- `docs/superpowers/specs/train-group-api-for-orochi-ui.md` — API reference for the Angular frontend integrators
