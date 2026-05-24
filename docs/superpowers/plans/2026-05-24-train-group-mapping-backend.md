# Train Group Schedule — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for a versioned, CSV/xlsx/paste-driven `train_id → group` schedule, plus integrate the new `group` field and filter into the existing tasks endpoints — so the Orochi-UI Angular frontend can consume it.

**Architecture:** Two new Django models in `cvat/apps/custom/` (`TrainGroupMapping` + `TrainGroupMappingVersion`); one pure parser module that accepts CSV, xlsx, and pasted text; one new view module exposing `/api/train-groups/*` endpoints for upload/list/versions/rollback; non-invasive additions to `views_analytics.py` (`?group=` filter + `available_groups` in summary response); read-only `group` field added to task serializers via Subquery annotation (no N+1).

**Tech Stack:** Python 3.10+, Django 4.2, Django REST Framework, openpyxl (new dep), SQLite/Postgres (existing). Tests use Django's `TestCase`.

**Reference:** Full design in `docs/superpowers/specs/2026-05-24-train-group-mapping-design.md`.

**Out of scope for this plan:** Frontend (separate Angular repo `Orochi-UI`); Admin UI per se — backend endpoints make this admin-tool reachable via curl until the Angular work lands.

---

## Phase 1 — Foundation: dependency, models, migration

### Task 1: Add `openpyxl` dependency

**Files:**
- Modify: `cvat/requirements/base.in`

- [ ] **Step 1.1: Add the dep line**

Open `cvat/requirements/base.in`. Find the alphabetically-sorted section near other `o*` packages. Add this line preserving alphabetical order:

```
openpyxl==3.1.5
```

- [ ] **Step 1.2: Regenerate the pinned txt files**

Run from repo root:

```bash
bash cvat/requirements/regenerate.sh
```

If `regenerate.sh` requires tools not installed locally, fall back to a manual `pip-compile`:

```bash
pip-compile --strip-extras --output-file=cvat/requirements/base.txt cvat/requirements/base.in
pip-compile --strip-extras --output-file=cvat/requirements/all.txt cvat/requirements/all.in
```

Expected: both `base.txt` and `all.txt` show `openpyxl==3.1.5` added.

- [ ] **Step 1.3: Install locally for development**

```bash
pip install openpyxl==3.1.5
```

- [ ] **Step 1.4: Commit**

```bash
git add cvat/requirements/base.in cvat/requirements/base.txt cvat/requirements/all.txt
git commit -m "deps: add openpyxl for train-group xlsx parsing"
```

---

### Task 2: Add `TrainGroupMapping` and `TrainGroupMappingVersion` models

**Files:**
- Modify: `cvat/apps/custom/models.py`

- [ ] **Step 2.1: Append the new models to `models.py`**

At the end of `cvat/apps/custom/models.py`, append:

```python


# ==========================================
# Train Group Schedule Models
# ==========================================

class TrainGroupMapping(models.Model):
    """
    Current source of truth: which group each train_id belongs to.
    One row per train. Fully rebuilt atomically on every upload.
    """

    train_id = models.CharField(max_length=100, primary_key=True)
    group = models.CharField(max_length=50, db_index=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="train_group_mappings_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Train Group Mapping"
        verbose_name_plural = "Train Group Mappings"
        db_table = "custom_train_group_mapping"
        indexes = [models.Index(fields=["group", "train_id"])]

    def __str__(self):
        return f"{self.train_id} -> {self.group}"


class TrainGroupMappingVersion(models.Model):
    """
    Immutable snapshot of each upload (or rollback).
    Exactly one row has is_current=True at any time.
    """

    version_no = models.PositiveIntegerField(unique=True)
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="train_group_mapping_versions",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    comment = models.CharField(max_length=500, blank=True)
    csv_text = models.TextField(
        help_text="Canonical CSV form (xlsx/paste uploads normalized to CSV)."
    )
    source_format = models.CharField(
        max_length=16,
        default="csv",
        help_text="One of: csv, xlsx, paste, rollback",
    )
    row_count = models.PositiveIntegerField()
    is_current = models.BooleanField(default=False)
    source_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rollbacks",
        help_text="Set when this version was produced by rolling back to source_version.",
    )
    diff_summary = models.JSONField(
        default=dict,
        help_text=(
            "Pre-computed diff vs previous current version: "
            "{added: [...], removed: [...], changed: [...], counts: {...}}"
        ),
    )

    class Meta:
        verbose_name = "Train Group Mapping Version"
        verbose_name_plural = "Train Group Mapping Versions"
        db_table = "custom_train_group_mapping_version"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="only_one_current_train_group_version",
            ),
        ]

    def __str__(self):
        marker = " (current)" if self.is_current else ""
        return f"v{self.version_no}{marker}"
```

- [ ] **Step 2.2: Generate the migration**

```bash
python manage.py makemigrations custom
```

Expected: a file `cvat/apps/custom/migrations/0004_<auto-name>.py` is created.

- [ ] **Step 2.3: Inspect the migration**

Open the generated file. Verify it contains:
- `CreateModel` for `TrainGroupMapping`
- `CreateModel` for `TrainGroupMappingVersion`
- The unique constraint `only_one_current_train_group_version`
- No accidental edits to existing models

If the auto-name is ugly (e.g., contains a long hash), rename the file to `0004_train_group_schedule.py` and update its `dependencies` list if needed.

- [ ] **Step 2.4: Apply locally and verify**

```bash
python manage.py migrate custom
python manage.py showmigrations custom
```

Expected: `[X] 0004_train_group_schedule` (or auto-name).

- [ ] **Step 2.5: Smoke test the models in a Django shell**

```bash
python manage.py shell -c "
from cvat.apps.custom.models import TrainGroupMapping, TrainGroupMappingVersion
m = TrainGroupMapping.objects.create(train_id='3101F', group='A')
print(repr(m))
v = TrainGroupMappingVersion.objects.create(
    version_no=1, comment='smoke', csv_text='train_id,group\n3101F,A',
    source_format='csv', row_count=1, is_current=True,
)
print(repr(v))
# cleanup
m.delete(); v.delete()
print('ok')
"
```

Expected: prints two reprs and `ok`. No exception.

- [ ] **Step 2.6: Commit**

```bash
git add cvat/apps/custom/models.py cvat/apps/custom/migrations/0004_*.py
git commit -m "models: add TrainGroupMapping and TrainGroupMappingVersion"
```

---

## Phase 2 — Parser: CSV, xlsx, paste

We build the parser as a **pure module** (no Django queries). It returns a normalized list of `ParsedRow` objects and a list of `ValidationError` records. This makes it cheap to unit-test exhaustively.

### Task 3: Set up the test package & write parser data classes

**Files:**
- Create: `cvat/apps/custom/tests/__init__.py`
- Create: `cvat/apps/custom/tests/test_train_group_parser.py`
- Create: `cvat/apps/custom/train_group_parser.py`
- Delete: `cvat/apps/custom/tests.py` (existing placeholder — superseded by the new package)

- [ ] **Step 3.1: Convert `tests.py` placeholder into a `tests/` package**

```bash
rm cvat/apps/custom/tests.py
mkdir -p cvat/apps/custom/tests
touch cvat/apps/custom/tests/__init__.py
```

- [ ] **Step 3.2: Write the first failing test (ParsedRow & ValidationError dataclasses exist)**

Create `cvat/apps/custom/tests/test_train_group_parser.py`:

```python
from django.test import SimpleTestCase

from cvat.apps.custom.train_group_parser import ParsedRow, ValidationError


class DataClassesTest(SimpleTestCase):
    def test_parsed_row_holds_train_id_and_group(self):
        row = ParsedRow(train_id="3101F", group="A", line_no=2)
        self.assertEqual(row.train_id, "3101F")
        self.assertEqual(row.group, "A")
        self.assertEqual(row.line_no, 2)

    def test_validation_error_holds_line_train_id_reason(self):
        err = ValidationError(line=14, train_id="3101 F", reason="whitespace not allowed")
        self.assertEqual(err.line, 14)
        self.assertEqual(err.reason, "whitespace not allowed")
```

- [ ] **Step 3.3: Run and verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: `ImportError` (the module doesn't exist yet).

- [ ] **Step 3.4: Create the parser module with just the dataclasses**

Create `cvat/apps/custom/train_group_parser.py`:

```python
# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
Pure parser/validation logic for train-group CSV/xlsx/paste uploads.
No Django ORM access; safe to unit-test without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedRow:
    """One validated (train_id, group) pair from an uploaded source."""
    train_id: str
    group: str
    line_no: int  # 1-based; for paste mode without a header, first data row = line 1


@dataclass(frozen=True)
class ValidationError:
    """One row-level rejection reason; safe to serialize back to the client."""
    line: int
    reason: str
    train_id: Optional[str] = None
```

- [ ] **Step 3.5: Re-run and verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: 2 tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/
git rm cvat/apps/custom/tests.py
git commit -m "parser: scaffold train_group_parser with data classes"
```

---

### Task 4: Implement `parse_csv` (happy path + validation)

**Files:**
- Modify: `cvat/apps/custom/tests/test_train_group_parser.py`
- Modify: `cvat/apps/custom/train_group_parser.py`

- [ ] **Step 4.1: Add the failing tests for `parse_csv`**

Append to `tests/test_train_group_parser.py`:

```python
from cvat.apps.custom.train_group_parser import parse_csv


class ParseCsvHappyPathTest(SimpleTestCase):
    def test_basic_three_rows(self):
        csv = "train_id,group\n3101F,A\n3102F,B\n3103F,A\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                ParsedRow("3101F", "A", line_no=2),
                ParsedRow("3102F", "B", line_no=3),
                ParsedRow("3103F", "A", line_no=4),
            ],
        )

    def test_tolerates_bom_and_trailing_blank_lines(self):
        csv = "﻿train_id,group\n3101F,A\n\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101F", "A", line_no=2)])

    def test_trims_whitespace_from_cells(self):
        csv = "train_id,group\n  3101F  ,  A  \n"
        rows, errors = parse_csv(csv)
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101F", "A", line_no=2)])

    def test_ignores_unknown_extra_columns(self):
        csv = "train_id,group,notes\n3101F,A,hello\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101F", "A", line_no=2)])


class ParseCsvValidationTest(SimpleTestCase):
    def test_rejects_missing_header(self):
        csv = "3101F,A\n3102F,B\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].line, 1)
        self.assertIn("header", errors[0].reason.lower())

    def test_rejects_wrong_header(self):
        csv = "trainid,grp\n3101F,A\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("header", errors[0].reason.lower())

    def test_rejects_empty_train_id(self):
        csv = "train_id,group\n,A\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(errors, [ValidationError(line=2, reason="train_id is empty", train_id="")])

    def test_rejects_empty_group(self):
        csv = "train_id,group\n3101F,\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(errors, [ValidationError(line=2, reason="group is empty", train_id="3101F")])

    def test_rejects_invalid_train_id_chars(self):
        csv = "train_id,group\n3101 F,A\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid characters", errors[0].reason)

    def test_rejects_duplicate_train_id(self):
        csv = "train_id,group\n3101F,A\n3101F,B\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("duplicate", errors[0].reason.lower())
        self.assertEqual(errors[0].train_id, "3101F")

    def test_empty_csv_accepted_as_clear(self):
        csv = "train_id,group\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(errors, [])

    def test_collects_multiple_errors(self):
        csv = "train_id,group\n,A\n3102F,\n3101 F,A\n"
        rows, errors = parse_csv(csv)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 3)
```

- [ ] **Step 4.2: Run to verify they fail**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: `ImportError: cannot import name 'parse_csv'`.

- [ ] **Step 4.3: Implement `parse_csv`**

Append to `cvat/apps/custom/train_group_parser.py`:

```python

import csv
import io
import re

_TRAIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_TRAIN_ID_LEN = 100
_MAX_GROUP_LEN = 50
_EXPECTED_HEADER = ("train_id", "group")


def parse_csv(text: str) -> tuple[list[ParsedRow], list[ValidationError]]:
    """
    Parse a CSV string into ParsedRow objects.

    Tolerates: UTF-8 BOM, trailing blank lines, leading/trailing whitespace in cells,
    extra columns beyond train_id,group.

    Rejects: missing/wrong header, empty fields, invalid train_id chars,
    duplicate train_id within the file. All errors collected; partial success is not returned.
    """

    text = text.lstrip("﻿")  # strip BOM if present
    reader = csv.reader(io.StringIO(text))

    rows: list[ParsedRow] = []
    errors: list[ValidationError] = []
    seen_train_ids: dict[str, int] = {}

    try:
        header = next(reader)
    except StopIteration:
        errors.append(ValidationError(line=1, reason="file is empty"))
        return [], errors

    header_normalized = tuple(c.strip().lower() for c in header[:2])
    if header_normalized != _EXPECTED_HEADER:
        errors.append(ValidationError(
            line=1,
            reason=f"expected header 'train_id,group' but got {','.join(header[:2])!r}",
        ))
        return [], errors

    for raw in reader:
        line_no = reader.line_num
        if not raw or all(not c.strip() for c in raw):
            continue  # skip blank line

        train_id = (raw[0] if len(raw) > 0 else "").strip()
        group = (raw[1] if len(raw) > 1 else "").strip()

        row_errors: list[ValidationError] = []

        if not train_id:
            row_errors.append(ValidationError(
                line=line_no, reason="train_id is empty", train_id="",
            ))
        elif len(train_id) > _MAX_TRAIN_ID_LEN:
            row_errors.append(ValidationError(
                line=line_no,
                reason=f"train_id exceeds {_MAX_TRAIN_ID_LEN} characters",
                train_id=train_id,
            ))
        elif not _TRAIN_ID_PATTERN.match(train_id):
            row_errors.append(ValidationError(
                line=line_no,
                reason="train_id contains invalid characters (allowed: A-Z a-z 0-9 _ -)",
                train_id=train_id,
            ))

        if not group:
            row_errors.append(ValidationError(
                line=line_no, reason="group is empty", train_id=train_id,
            ))
        elif len(group) > _MAX_GROUP_LEN:
            row_errors.append(ValidationError(
                line=line_no,
                reason=f"group exceeds {_MAX_GROUP_LEN} characters",
                train_id=train_id,
            ))

        if row_errors:
            errors.extend(row_errors)
            continue

        if train_id in seen_train_ids:
            errors.append(ValidationError(
                line=line_no,
                reason=f"duplicate train_id (first seen on line {seen_train_ids[train_id]})",
                train_id=train_id,
            ))
            continue

        seen_train_ids[train_id] = line_no
        rows.append(ParsedRow(train_id=train_id, group=group, line_no=line_no))

    # If any errors at all, return nothing parsed (all-or-nothing semantics)
    if errors:
        return [], errors
    return rows, []
```

- [ ] **Step 4.4: Re-run and verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: all CSV tests pass.

- [ ] **Step 4.5: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/test_train_group_parser.py
git commit -m "parser: implement parse_csv with full validation"
```

---

### Task 5: Implement `parse_xlsx`

**Files:**
- Modify: `cvat/apps/custom/tests/test_train_group_parser.py`
- Modify: `cvat/apps/custom/train_group_parser.py`

- [ ] **Step 5.1: Write failing tests for `parse_xlsx`**

Append to `tests/test_train_group_parser.py`:

```python
from io import BytesIO
from openpyxl import Workbook

from cvat.apps.custom.train_group_parser import parse_xlsx


def _xlsx_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ParseXlsxTest(SimpleTestCase):
    def test_basic_happy_path(self):
        data = _xlsx_bytes([
            ["train_id", "group"],
            ["3101F", "A"],
            ["3102F", "B"],
        ])
        rows, errors = parse_xlsx(data)
        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                ParsedRow("3101F", "A", line_no=2),
                ParsedRow("3102F", "B", line_no=3),
            ],
        )

    def test_tolerates_trailing_empty_rows(self):
        data = _xlsx_bytes([
            ["train_id", "group"],
            ["3101F", "A"],
            [None, None],
            ["", ""],
        ])
        rows, errors = parse_xlsx(data)
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101F", "A", line_no=2)])

    def test_rejects_wrong_header(self):
        data = _xlsx_bytes([
            ["foo", "bar"],
            ["3101F", "A"],
        ])
        rows, errors = parse_xlsx(data)
        self.assertEqual(rows, [])
        self.assertIn("header", errors[0].reason.lower())

    def test_first_sheet_only(self):
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Schedule"
        ws1.append(["train_id", "group"])
        ws1.append(["3101F", "A"])
        ws2 = wb.create_sheet("Notes")
        ws2.append(["this should be ignored", "really"])
        buf = BytesIO()
        wb.save(buf)
        rows, errors = parse_xlsx(buf.getvalue())
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101F", "A", line_no=2)])

    def test_integer_cell_values_stringified(self):
        # openpyxl returns ints for numeric cells; parser should str() them
        data = _xlsx_bytes([
            ["train_id", "group"],
            [3101, 1],
        ])
        rows, errors = parse_xlsx(data)
        self.assertEqual(errors, [])
        self.assertEqual(rows, [ParsedRow("3101", "1", line_no=2)])

    def test_corrupt_bytes_returns_error(self):
        rows, errors = parse_xlsx(b"not a real xlsx")
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].line, 0)
```

- [ ] **Step 5.2: Run to verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: `ImportError: cannot import name 'parse_xlsx'`.

- [ ] **Step 5.3: Implement `parse_xlsx`**

Append to `cvat/apps/custom/train_group_parser.py`:

```python


def parse_xlsx(file_bytes: bytes) -> tuple[list[ParsedRow], list[ValidationError]]:
    """
    Parse the FIRST worksheet of an xlsx file (passed as raw bytes).

    Reads cached values for formulas; if no cached value is present (file never
    opened in Excel), the cell is read as None.

    Normalizes to CSV semantics and then re-uses parse_csv for validation so
    the rules stay identical across input modes.
    """
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError, ValueError) as exc:
        return [], [ValidationError(line=0, reason=f"could not read xlsx: {exc}")]

    ws = wb.worksheets[0]

    # Convert to CSV text — easier than threading line numbers through
    csv_lines: list[str] = []
    for row in ws.iter_rows(values_only=True):
        # Treat all-empty rows as blank
        if not row or all(c is None or (isinstance(c, str) and not c.strip()) for c in row):
            csv_lines.append("")
            continue
        cells = []
        for c in row[:2]:  # only first two columns matter
            if c is None:
                cells.append("")
            else:
                cells.append(str(c).strip())
        csv_lines.append(",".join(cells))

    csv_text = "\n".join(csv_lines)
    return parse_csv(csv_text)
```

Also add the `BytesIO` import at the top of the file if not present — find the existing `import io` line near the top and update it:

```python
import csv
import io
from io import BytesIO
import re
```

- [ ] **Step 5.4: Re-run and verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: all xlsx tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/test_train_group_parser.py
git commit -m "parser: implement parse_xlsx using parse_csv as final validator"
```

---

### Task 6: Implement `parse_pasted`

**Files:**
- Modify: `cvat/apps/custom/tests/test_train_group_parser.py`
- Modify: `cvat/apps/custom/train_group_parser.py`

- [ ] **Step 6.1: Write failing tests**

Append to `tests/test_train_group_parser.py`:

```python
from cvat.apps.custom.train_group_parser import parse_pasted


class ParsePastedTest(SimpleTestCase):
    def test_tab_separated_with_header(self):
        text = "train_id\tgroup\n3101F\tA\n3102F\tB\n"
        rows, errors = parse_pasted(text)
        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                ParsedRow("3101F", "A", line_no=2),
                ParsedRow("3102F", "B", line_no=3),
            ],
        )

    def test_tab_separated_without_header(self):
        # Excel's clipboard copy of two columns won't include a header
        text = "3101F\tA\n3102F\tB\n"
        rows, errors = parse_pasted(text)
        self.assertEqual(errors, [])
        self.assertEqual(
            rows,
            [
                ParsedRow("3101F", "A", line_no=1),
                ParsedRow("3102F", "B", line_no=2),
            ],
        )

    def test_comma_separated_without_header(self):
        text = "3101F,A\n3102F,B\n"
        rows, errors = parse_pasted(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)

    def test_rejects_single_column(self):
        text = "3101F\n3102F\n"
        rows, errors = parse_pasted(text)
        self.assertEqual(rows, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("two columns", errors[0].reason)

    def test_empty_pasted_text_clears(self):
        rows, errors = parse_pasted("")
        self.assertEqual(rows, [])
        self.assertEqual(errors, [])

    def test_carriage_returns_normalized(self):
        text = "3101F\tA\r\n3102F\tB\r\n"
        rows, errors = parse_pasted(text)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2)
```

- [ ] **Step 6.2: Run to verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: import error.

- [ ] **Step 6.3: Implement `parse_pasted`**

Append to `cvat/apps/custom/train_group_parser.py`:

```python


def parse_pasted(text: str) -> tuple[list[ParsedRow], list[ValidationError]]:
    """
    Parse text pasted from a spreadsheet.

    Excel's default clipboard format is tab-separated and includes NO header.
    We auto-detect the separator (tab if any line contains a tab, else comma)
    and tolerate both header-present and header-absent input.

    Returns the same shape as parse_csv. All-or-nothing on errors.
    """
    if not text.strip():
        return [], []

    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lines = [ln for ln in text.split("\n") if ln.strip()]

    # Determine separator
    has_tab = any("\t" in ln for ln in lines)
    sep = "\t" if has_tab else ","

    first_cells = [c.strip().lower() for c in lines[0].split(sep)[:2]]
    has_header = first_cells == list(_EXPECTED_HEADER)

    # Validate at least two columns
    sample = lines[0].split(sep)
    if len(sample) < 2:
        return [], [ValidationError(
            line=1,
            reason="expected two columns (train_id and group); could not detect separator",
        )]

    # Re-emit as canonical CSV with header so parse_csv handles validation
    body_lines = lines[1:] if has_header else lines
    csv_lines = ["train_id,group"]
    for ln in body_lines:
        cells = ln.split(sep)
        train_id = cells[0].strip() if len(cells) > 0 else ""
        group = cells[1].strip() if len(cells) > 1 else ""
        # Naive CSV quoting: if either cell contains a comma, wrap it
        if "," in train_id:
            train_id = '"' + train_id.replace('"', '""') + '"'
        if "," in group:
            group = '"' + group.replace('"', '""') + '"'
        csv_lines.append(f"{train_id},{group}")

    csv_text = "\n".join(csv_lines)

    # Re-run through parse_csv, then offset line numbers if the user pasted
    # data-only (no header) so that errors point at the actual pasted line
    rows, errors = parse_csv(csv_text)
    if has_header:
        return rows, errors

    # parse_csv reports line_no relative to the CSV (header = line 1, first
    # data row = line 2). For paste-without-header we want first data row = line 1.
    offset = -1
    fixed_rows = [ParsedRow(r.train_id, r.group, line_no=r.line_no + offset) for r in rows]
    fixed_errors = [ValidationError(line=e.line + offset if e.line > 1 else e.line,
                                    reason=e.reason, train_id=e.train_id) for e in errors]
    return fixed_rows, fixed_errors
```

- [ ] **Step 6.4: Run and verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_parser -v 2
```

Expected: all parser tests pass (CSV + xlsx + paste).

- [ ] **Step 6.5: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/test_train_group_parser.py
git commit -m "parser: implement parse_pasted with separator auto-detection"
```

---

## Phase 3 — Diff computation & atomic apply

### Task 7: Implement `compute_diff`

**Files:**
- Create: `cvat/apps/custom/tests/test_train_group_diff_apply.py`
- Modify: `cvat/apps/custom/train_group_parser.py`

- [ ] **Step 7.1: Write failing tests**

Create `cvat/apps/custom/tests/test_train_group_diff_apply.py`:

```python
from django.test import TestCase

from cvat.apps.custom.models import TrainGroupMapping
from cvat.apps.custom.train_group_parser import ParsedRow, compute_diff


class ComputeDiffTest(TestCase):
    def test_added_removed_changed_unchanged(self):
        # Seed current state
        TrainGroupMapping.objects.create(train_id="A1", group="X")  # changed → Y
        TrainGroupMapping.objects.create(train_id="A2", group="X")  # removed
        TrainGroupMapping.objects.create(train_id="A3", group="Y")  # unchanged

        new_rows = [
            ParsedRow("A1", "Y", line_no=2),  # changed
            ParsedRow("A3", "Y", line_no=3),  # unchanged
            ParsedRow("A4", "Z", line_no=4),  # added
        ]
        diff = compute_diff(new_rows, TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"], {
            "added": 1, "removed": 1, "changed": 1, "unchanged": 1,
        })
        self.assertEqual(diff["added"], [{"train_id": "A4", "group": "Z"}])
        self.assertEqual(diff["removed"], [{"train_id": "A2", "group": "X"}])
        self.assertEqual(diff["changed"], [{
            "train_id": "A1", "old_group": "X", "new_group": "Y",
        }])

    def test_diff_against_empty_current_state(self):
        new_rows = [ParsedRow("A1", "X", line_no=2)]
        diff = compute_diff(new_rows, TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"]["added"], 1)
        self.assertEqual(diff["counts"]["removed"], 0)

    def test_diff_clearing_all(self):
        TrainGroupMapping.objects.create(train_id="A1", group="X")
        TrainGroupMapping.objects.create(train_id="A2", group="Y")
        diff = compute_diff([], TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"]["removed"], 2)
        self.assertEqual(diff["counts"]["added"], 0)
```

- [ ] **Step 7.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_diff_apply -v 2
```

Expected: `ImportError: cannot import name 'compute_diff'`.

- [ ] **Step 7.3: Implement `compute_diff`**

Append to `cvat/apps/custom/train_group_parser.py`:

```python


def compute_diff(new_rows: list[ParsedRow], current_qs) -> dict:
    """
    Compute the diff between a proposed mapping (new_rows) and the current state.

    `current_qs` should be any iterable of objects exposing `train_id` and `group`
    attributes (typically TrainGroupMapping.objects.all() or .values()).

    Returns:
        {
            "added":   [{"train_id": "X", "group": "A"}, ...],
            "removed": [{"train_id": "Y", "group": "B"}, ...],
            "changed": [{"train_id": "Z", "old_group": "C", "new_group": "D"}, ...],
            "counts":  {"added": int, "removed": int, "changed": int, "unchanged": int},
        }
    """
    new_map: dict[str, str] = {r.train_id: r.group for r in new_rows}

    current_map: dict[str, str] = {}
    for obj in current_qs:
        # Support both model instances and dicts from .values()
        if isinstance(obj, dict):
            current_map[obj["train_id"]] = obj["group"]
        else:
            current_map[obj.train_id] = obj.group

    added: list[dict] = []
    removed: list[dict] = []
    changed: list[dict] = []
    unchanged_count = 0

    new_keys = set(new_map.keys())
    current_keys = set(current_map.keys())

    for tid in sorted(new_keys - current_keys):
        added.append({"train_id": tid, "group": new_map[tid]})

    for tid in sorted(current_keys - new_keys):
        removed.append({"train_id": tid, "group": current_map[tid]})

    for tid in sorted(new_keys & current_keys):
        if new_map[tid] != current_map[tid]:
            changed.append({
                "train_id": tid,
                "old_group": current_map[tid],
                "new_group": new_map[tid],
            })
        else:
            unchanged_count += 1

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": unchanged_count,
        },
    }
```

- [ ] **Step 7.4: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_diff_apply -v 2
```

- [ ] **Step 7.5: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/test_train_group_diff_apply.py
git commit -m "parser: implement compute_diff against current mapping state"
```

---

### Task 8: Implement `apply_upload` (transactional)

**Files:**
- Modify: `cvat/apps/custom/tests/test_train_group_diff_apply.py`
- Modify: `cvat/apps/custom/train_group_parser.py`

- [ ] **Step 8.1: Write failing tests**

Append to `tests/test_train_group_diff_apply.py`:

```python
from django.contrib.auth.models import User
from django.db import transaction

from cvat.apps.custom.models import TrainGroupMappingVersion
from cvat.apps.custom.train_group_parser import apply_upload


class ApplyUploadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice")

    def test_first_upload_creates_v1_and_populates_mapping(self):
        rows = [ParsedRow("A1", "X", 2), ParsedRow("A2", "Y", 3)]
        version = apply_upload(
            rows=rows, user=self.user, comment="initial",
            raw_input_text="train_id,group\nA1,X\nA2,Y\n",
            source_format="csv",
        )
        self.assertEqual(version.version_no, 1)
        self.assertTrue(version.is_current)
        self.assertEqual(version.source_format, "csv")
        self.assertEqual(version.row_count, 2)
        self.assertEqual(version.uploaded_by, self.user)
        self.assertEqual(TrainGroupMapping.objects.count(), 2)
        self.assertEqual(version.diff_summary["counts"]["added"], 2)

    def test_second_upload_bumps_version_and_replaces_mapping(self):
        apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="",
            raw_input_text="train_id,group\nA1,X\n", source_format="csv",
        )
        v2 = apply_upload(
            rows=[ParsedRow("A2", "Y", 2)], user=self.user, comment="",
            raw_input_text="train_id,group\nA2,Y\n", source_format="csv",
        )
        self.assertEqual(v2.version_no, 2)
        self.assertTrue(v2.is_current)

        # Only one is_current row
        self.assertEqual(
            TrainGroupMappingVersion.objects.filter(is_current=True).count(), 1,
        )
        # Mapping replaced: A1 gone, A2 present
        self.assertFalse(TrainGroupMapping.objects.filter(train_id="A1").exists())
        self.assertTrue(TrainGroupMapping.objects.filter(train_id="A2").exists())
        # Diff reflects swap
        self.assertEqual(v2.diff_summary["counts"]["added"], 1)
        self.assertEqual(v2.diff_summary["counts"]["removed"], 1)

    def test_source_version_recorded_on_rollback(self):
        v1 = apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="initial",
            raw_input_text="train_id,group\nA1,X\n", source_format="csv",
        )
        v2 = apply_upload(
            rows=[ParsedRow("A2", "Y", 2)], user=self.user, comment="oops",
            raw_input_text="train_id,group\nA2,Y\n", source_format="csv",
        )
        v3 = apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="rollback to v1",
            raw_input_text="train_id,group\nA1,X\n",
            source_format="rollback", source_version=v1,
        )
        self.assertEqual(v3.source_version_id, v1.pk)
        # Past versions never mutated
        v1.refresh_from_db(); v2.refresh_from_db()
        self.assertFalse(v1.is_current)
        self.assertFalse(v2.is_current)
        self.assertTrue(v3.is_current)
```

- [ ] **Step 8.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_diff_apply -v 2
```

Expected: `ImportError: cannot import name 'apply_upload'`.

- [ ] **Step 8.3: Implement `apply_upload`**

Append to `cvat/apps/custom/train_group_parser.py`:

```python


def apply_upload(
    rows: list[ParsedRow],
    user,
    comment: str,
    raw_input_text: str,
    source_format: str,
    source_version=None,
):
    """
    Apply a parsed mapping atomically.

    Steps inside a single transaction:
      1. Lock and clear `is_current` on the existing current version (if any).
      2. Create the new Version row with computed diff_summary and is_current=True.
      3. Delete all existing TrainGroupMapping rows.
      4. Bulk-insert the new rows.

    Returns the new TrainGroupMappingVersion instance.
    """
    # Imported lazily so this module stays importable in test contexts that
    # haven't configured Django apps yet.
    from django.db import transaction
    from django.db.models import Max
    from .models import TrainGroupMapping, TrainGroupMappingVersion

    with transaction.atomic():
        # Lock current rows (no-op when none exist; on the first upload there's
        # nothing to lock). select_for_update on an empty result is fine.
        current = (
            TrainGroupMappingVersion.objects
            .select_for_update()
            .filter(is_current=True)
            .first()
        )

        diff = compute_diff(rows, TrainGroupMapping.objects.all())

        if current is not None:
            current.is_current = False
            current.save(update_fields=["is_current"])

        next_no = (
            TrainGroupMappingVersion.objects.aggregate(m=Max("version_no"))["m"] or 0
        ) + 1

        version = TrainGroupMappingVersion.objects.create(
            version_no=next_no,
            uploaded_by=user,
            comment=comment,
            csv_text=raw_input_text,
            source_format=source_format,
            row_count=len(rows),
            is_current=True,
            source_version=source_version,
            diff_summary=diff,
        )

        # Replace mapping table contents
        TrainGroupMapping.objects.all().delete()
        TrainGroupMapping.objects.bulk_create(
            [
                TrainGroupMapping(train_id=r.train_id, group=r.group, updated_by=user)
                for r in rows
            ],
            batch_size=1000,
        )

    return version
```

- [ ] **Step 8.4: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_diff_apply -v 2
```

- [ ] **Step 8.5: Commit**

```bash
git add cvat/apps/custom/train_group_parser.py cvat/apps/custom/tests/test_train_group_diff_apply.py
git commit -m "parser: implement transactional apply_upload with version + diff"
```

---

## Phase 4 — REST endpoints

### Task 9: Add serializers for mappings & versions

**Files:**
- Modify: `cvat/apps/custom/serializers.py`

- [ ] **Step 9.1: Append serializers to `serializers.py`**

At the end of `cvat/apps/custom/serializers.py`, append:

```python


# ==========================================
# Train Group Schedule Serializers
# ==========================================

from .models import TrainGroupMapping, TrainGroupMappingVersion


class TrainGroupMappingSerializer(serializers.ModelSerializer):
    """Read-only representation of one train_id → group row."""

    updated_by_username = serializers.CharField(
        source="updated_by.username", read_only=True, default=None,
    )

    class Meta:
        model = TrainGroupMapping
        fields = ["train_id", "group", "updated_by_username", "updated_at"]
        read_only_fields = fields


class TrainGroupMappingVersionListSerializer(serializers.ModelSerializer):
    """Light serializer for the version-history list endpoint."""

    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True, default=None,
    )
    counts = serializers.SerializerMethodField()

    class Meta:
        model = TrainGroupMappingVersion
        fields = [
            "version_no",
            "uploaded_by_username",
            "uploaded_at",
            "comment",
            "source_format",
            "row_count",
            "is_current",
            "source_version",
            "counts",
        ]
        read_only_fields = fields

    def get_counts(self, obj):
        return obj.diff_summary.get("counts", {}) if obj.diff_summary else {}


class TrainGroupMappingVersionDetailSerializer(TrainGroupMappingVersionListSerializer):
    """Includes the full csv_text and diff_summary for a single version."""

    class Meta(TrainGroupMappingVersionListSerializer.Meta):
        fields = TrainGroupMappingVersionListSerializer.Meta.fields + [
            "csv_text", "diff_summary",
        ]
        read_only_fields = fields
```

- [ ] **Step 9.2: Quick smoke import**

```bash
python -c "from cvat.apps.custom.serializers import TrainGroupMappingSerializer, TrainGroupMappingVersionListSerializer, TrainGroupMappingVersionDetailSerializer; print('ok')"
```

Expected: `ok`.

- [ ] **Step 9.3: Commit**

```bash
git add cvat/apps/custom/serializers.py
git commit -m "serializers: add train group mapping + version serializers"
```

---

### Task 10: Create `views_train_groups.py` shell + permission constant + URL wiring

**Files:**
- Create: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`

- [ ] **Step 10.1: Create the views module skeleton**

Create `cvat/apps/custom/views_train_groups.py`:

```python
# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
REST endpoints for the train_id → group schedule:
  GET    /api/train-groups/mappings/
  GET    /api/train-groups/mappings/template.csv
  GET    /api/train-groups/mappings/export.csv
  POST   /api/train-groups/mappings/upload/
  GET    /api/train-groups/groups/                 (alias for tasks-summary.available_groups)
  GET    /api/train-groups/versions/
  GET    /api/train-groups/versions/<id>/
  POST   /api/train-groups/versions/<id>/rollback/
"""

from __future__ import annotations

from rest_framework import permissions

# --- Permission policy (single source of truth — swap one line to change scope) ---
# DRF's IsAdminUser passes when user.is_staff is True. Superusers created via
# `createsuperuser` are also is_staff, so both groups pass. To restrict further
# (e.g., to a custom Django Group or a CVAT IAM role), replace this list.
MAPPING_ADMIN_PERMISSIONS = [permissions.IsAdminUser]
```

- [ ] **Step 10.2: Wire empty routes in `urls.py`**

Open `cvat/apps/custom/urls.py`. Find the `urlpatterns = [` block. Add an import at the top of the file alongside the other `views_*` imports:

```python
from . import views_train_groups
```

Then add this group of URL entries near the bottom of `urlpatterns` (right before `# Add the router URLs`):

```python
    # Train group schedule endpoints (Task 11–17 will fill in views)
    # path('train-groups/mappings/', views_train_groups.MappingsListView.as_view(),
    #      name='train-groups-mappings'),
    # (intentionally commented until views land in later tasks)
```

- [ ] **Step 10.3: Confirm Django still boots**

```bash
python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 10.4: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py
git commit -m "views: scaffold views_train_groups.py and permission constant"
```

---

### Task 11: Implement `MappingsListView` (paginated, searchable)

**Files:**
- Modify: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`
- Create: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 11.1: Write failing endpoint test**

Create `cvat/apps/custom/tests/test_train_group_endpoints.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from cvat.apps.custom.models import TrainGroupMapping


class MappingsListViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        TrainGroupMapping.objects.bulk_create([
            TrainGroupMapping(train_id="3101F", group="A"),
            TrainGroupMapping(train_id="3102F", group="B"),
            TrainGroupMapping(train_id="3103F", group="A"),
        ])

    def test_lists_all_mappings(self):
        resp = self.client.get("/api/train-groups/mappings/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

    def test_filters_by_group(self):
        resp = self.client.get("/api/train-groups/mappings/?group=A")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

    def test_searches_train_id(self):
        resp = self.client.get("/api/train-groups/mappings/?search=3102")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.get("/api/train-groups/mappings/")
        self.assertEqual(resp.status_code, 401)
```

- [ ] **Step 11.2: Run, verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

Expected: 404s (URL not registered yet).

- [ ] **Step 11.3: Implement view**

Append to `cvat/apps/custom/views_train_groups.py`:

```python


from django.db.models import Q
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from .models import TrainGroupMapping
from .serializers import TrainGroupMappingSerializer


class _MappingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class MappingsListView(ListAPIView):
    """GET /api/train-groups/mappings/?search=&group=&page=&page_size="""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TrainGroupMappingSerializer
    pagination_class = _MappingPagination

    def get_queryset(self):
        qs = TrainGroupMapping.objects.select_related("updated_by").order_by("train_id")
        search = self.request.query_params.get("search", "").strip()
        group = self.request.query_params.get("group", "").strip()
        if group:
            qs = qs.filter(group=group)
        if search:
            qs = qs.filter(Q(train_id__icontains=search) | Q(group__icontains=search))
        return qs
```

- [ ] **Step 11.4: Wire the URL**

In `cvat/apps/custom/urls.py`, replace the commented-out placeholder block with:

```python
    # Train group schedule endpoints
    path('train-groups/mappings/', views_train_groups.MappingsListView.as_view(),
         name='train-groups-mappings'),
```

- [ ] **Step 11.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

- [ ] **Step 11.6: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "endpoints: GET /api/train-groups/mappings/ with search & group filter"
```

---

### Task 12: Implement template & export CSV endpoints

**Files:**
- Modify: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 12.1: Write failing tests**

Append to `tests/test_train_group_endpoints.py`:

```python
class TemplateAndExportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_template_returns_csv_with_header(self):
        resp = self.client.get("/api/train-groups/mappings/template.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode()
        self.assertIn("train_id,group", body.splitlines()[0])

    def test_export_returns_current_mapping_as_csv(self):
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        TrainGroupMapping.objects.create(train_id="3102F", group="B")
        resp = self.client.get("/api/train-groups/mappings/export.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode().splitlines()
        self.assertEqual(body[0], "train_id,group")
        self.assertIn("3101F,A", body)
        self.assertIn("3102F,B", body)
```

- [ ] **Step 12.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.TemplateAndExportTest -v 2
```

- [ ] **Step 12.3: Implement the two views**

Append to `cvat/apps/custom/views_train_groups.py`:

```python


import csv as _csv
from io import StringIO

from django.http import HttpResponse
from rest_framework.views import APIView


_TEMPLATE_CSV = (
    "train_id,group\n"
    "3101F,A\n"
    "3102F,B\n"
    "3103F,C\n"
)


class MappingTemplateCsvView(APIView):
    """GET /api/train-groups/mappings/template.csv — blank example CSV."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        resp = HttpResponse(_TEMPLATE_CSV, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="train_group_template.csv"'
        return resp


class MappingExportCsvView(APIView):
    """GET /api/train-groups/mappings/export.csv — current mapping as CSV."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        buf = StringIO()
        writer = _csv.writer(buf)
        writer.writerow(["train_id", "group"])
        for m in TrainGroupMapping.objects.order_by("train_id").values_list("train_id", "group"):
            writer.writerow(m)
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="train_group_mapping.csv"'
        return resp
```

- [ ] **Step 12.4: Add URLs**

In `cvat/apps/custom/urls.py`, add right after the `mappings/` route:

```python
    path('train-groups/mappings/template.csv', views_train_groups.MappingTemplateCsvView.as_view(),
         name='train-groups-template-csv'),
    path('train-groups/mappings/export.csv', views_train_groups.MappingExportCsvView.as_view(),
         name='train-groups-export-csv'),
```

- [ ] **Step 12.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

- [ ] **Step 12.6: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "endpoints: template.csv and export.csv for train group mapping"
```

---

### Task 13: Implement `UploadView` (multipart + JSON, dry_run, permissions)

**Files:**
- Modify: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 13.1: Write failing tests**

Append to `tests/test_train_group_endpoints.py`:

```python
from io import BytesIO
from openpyxl import Workbook

from cvat.apps.custom.models import TrainGroupMappingVersion


def _make_admin():
    return User.objects.create_user("admin", password="pw", is_staff=True)


class UploadViewTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_csv_upload_creates_version_and_mapping(self):
        csv = b"train_id,group\n3101F,A\n3102F,B\n"
        resp = self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("schedule.csv", csv, "text/csv"), "comment": "first"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["version"], 1)
        self.assertEqual(resp.data["diff"]["counts"]["added"], 2)
        self.assertEqual(TrainGroupMapping.objects.count(), 2)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "csv")
        self.assertTrue(v.is_current)

    def test_xlsx_upload_creates_version(self):
        wb = Workbook(); ws = wb.active
        ws.append(["train_id", "group"]); ws.append(["3101F", "A"])
        buf = BytesIO(); wb.save(buf)
        resp = self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("schedule.xlsx", buf.getvalue(),
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "xlsx")

    def test_pasted_upload_json(self):
        resp = self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"text": "3101F\tA\n3102F\tB\n", "comment": "pasted"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "paste")

    def test_dry_run_does_not_write(self):
        csv = b"train_id,group\n3101F,A\n"
        resp = self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("schedule.csv", csv, "text/csv"), "dry_run": "true"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNone(resp.data["version"])
        self.assertEqual(TrainGroupMapping.objects.count(), 0)
        self.assertEqual(TrainGroupMappingVersion.objects.count(), 0)

    def test_invalid_csv_returns_400_no_writes(self):
        csv = b"train_id,group\n,A\n"
        resp = self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("bad.csv", csv, "text/csv")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("errors", resp.data)
        self.assertEqual(TrainGroupMapping.objects.count(), 0)

    def test_non_admin_rejected(self):
        regular = User.objects.create_user("bob", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("x.csv", b"train_id,group\n", "text/csv")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 13.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.UploadViewTest -v 2
```

- [ ] **Step 13.3: Implement `UploadView`**

Append to `cvat/apps/custom/views_train_groups.py`:

```python


from dataclasses import asdict

from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response

from .train_group_parser import (
    parse_csv, parse_xlsx, parse_pasted, compute_diff, apply_upload,
)

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_PASTED_BYTES = 1 * 1024 * 1024  # 1 MB


def _is_truthy(val) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


class UploadView(APIView):
    """POST /api/train-groups/mappings/upload/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        comment = (request.data.get("comment") or "").strip()
        dry_run = _is_truthy(request.data.get("dry_run"))

        # ---- 1. Resolve input mode and parse ----
        if "file" in request.FILES:
            upload = request.FILES["file"]
            if upload.size > _MAX_FILE_BYTES:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": f"file exceeds {_MAX_FILE_BYTES // 1024 // 1024} MB"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            data = upload.read()
            name = (upload.name or "").lower()

            if name.endswith(".xlsx"):
                rows, errors = parse_xlsx(data)
                source_format = "xlsx"
                # Normalize raw_input to canonical CSV for storage
                raw_input_text = "train_id,group\n" + "".join(
                    f"{r.train_id},{r.group}\n" for r in rows
                )
            elif name.endswith(".csv") or name == "":
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    return Response(
                        {"errors": [{"line": 0, "reason": "file is not valid UTF-8"}]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                rows, errors = parse_csv(text)
                source_format = "csv"
                raw_input_text = text
            else:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": "unsupported file extension; expected .csv or .xlsx"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        elif "text" in request.data:
            text = request.data.get("text") or ""
            if len(text.encode("utf-8")) > _MAX_PASTED_BYTES:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": f"pasted text exceeds {_MAX_PASTED_BYTES // 1024} KB"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows, errors = parse_pasted(text)
            source_format = "paste"
            raw_input_text = "train_id,group\n" + "".join(
                f"{r.train_id},{r.group}\n" for r in rows
            )

        else:
            return Response(
                {"errors": [{"line": 0,
                             "reason": "expected multipart 'file' or JSON 'text'"}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if errors:
            return Response(
                {"errors": [asdict(e) for e in errors]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- 2. Diff for warnings ----
        diff = compute_diff(rows, TrainGroupMapping.objects.all())
        warnings = self._generate_warnings(rows, diff)

        # ---- 3. Dry-run short-circuit ----
        if dry_run:
            return Response({
                "version": None,
                "diff": diff,
                "warnings": warnings,
            })

        # ---- 4. Apply ----
        try:
            version = apply_upload(
                rows=rows, user=request.user, comment=comment,
                raw_input_text=raw_input_text, source_format=source_format,
            )
        except Exception as exc:
            return Response(
                {"errors": [{"line": 0, "reason": f"apply failed: {exc}"}]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "version": version.version_no,
            "diff": version.diff_summary,
            "warnings": warnings,
        })

    def _generate_warnings(self, rows, diff):
        """Non-blocking informational warnings shown to the admin."""
        from .models import TaskTrainMetadata

        warnings = []
        train_ids_in_csv = {r.train_id for r in rows}

        # Trains in CSV with no existing task metadata yet
        existing_with_meta = set(
            TaskTrainMetadata.objects.filter(train_id__in=train_ids_in_csv)
            .values_list("train_id", flat=True)
        )
        unused_in_csv = train_ids_in_csv - existing_with_meta
        if unused_in_csv:
            warnings.append({
                "code": "trains_with_no_tasks",
                "message": f"{len(unused_in_csv)} trains in CSV have no tasks yet",
                "sample": sorted(unused_in_csv)[:10],
            })

        # Tasks that will become Ungrouped (their train_id is being removed)
        removed_train_ids = {r["train_id"] for r in diff["removed"]}
        affected_task_count = TaskTrainMetadata.objects.filter(
            train_id__in=removed_train_ids,
        ).count()
        if affected_task_count:
            warnings.append({
                "code": "tasks_becoming_ungrouped",
                "message": f"{affected_task_count} tasks will become Ungrouped",
                "sample": sorted(removed_train_ids)[:10],
            })

        return warnings
```

- [ ] **Step 13.4: Add URL**

In `cvat/apps/custom/urls.py`, append after the export route:

```python
    path('train-groups/mappings/upload/', views_train_groups.UploadView.as_view(),
         name='train-groups-upload'),
```

- [ ] **Step 13.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

- [ ] **Step 13.6: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "endpoints: POST upload (csv/xlsx/paste) with dry-run and warnings"
```

---

### Task 14: Implement version-history list & detail views

**Files:**
- Modify: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 14.1: Write failing tests**

Append to `tests/test_train_group_endpoints.py`:

```python
class VersionHistoryTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin2", password="pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        # Use the upload endpoint to create two versions
        self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("v1.csv", b"train_id,group\n3101F,A\n", "text/csv")},
            format="multipart",
        )
        self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("v2.csv", b"train_id,group\n3101F,A\n3102F,B\n", "text/csv"),
                  "comment": "added 3102F"},
            format="multipart",
        )

    def test_list_versions_descending(self):
        resp = self.client.get("/api/train-groups/versions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["results"][0]["version_no"], 2)
        self.assertTrue(resp.data["results"][0]["is_current"])
        self.assertFalse(resp.data["results"][1]["is_current"])

    def test_detail_includes_csv_text_and_diff(self):
        resp = self.client.get("/api/train-groups/versions/2/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csv_text", resp.data)
        self.assertIn("3101F,A", resp.data["csv_text"])
        self.assertEqual(resp.data["diff_summary"]["counts"]["added"], 1)

    def test_non_admin_rejected(self):
        regular = User.objects.create_user("eve", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.get("/api/train-groups/versions/")
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 14.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.VersionHistoryTest -v 2
```

- [ ] **Step 14.3: Implement views**

Append to `cvat/apps/custom/views_train_groups.py`:

```python


from rest_framework.generics import RetrieveAPIView

from .models import TrainGroupMappingVersion
from .serializers import (
    TrainGroupMappingVersionListSerializer,
    TrainGroupMappingVersionDetailSerializer,
)


class VersionsListView(ListAPIView):
    """GET /api/train-groups/versions/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    serializer_class = TrainGroupMappingVersionListSerializer
    pagination_class = _MappingPagination

    def get_queryset(self):
        return (
            TrainGroupMappingVersion.objects
            .select_related("uploaded_by")
            .order_by("-version_no")
        )


class VersionDetailView(RetrieveAPIView):
    """GET /api/train-groups/versions/<version_no>/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    serializer_class = TrainGroupMappingVersionDetailSerializer
    queryset = TrainGroupMappingVersion.objects.all()
    lookup_field = "version_no"
```

- [ ] **Step 14.4: Add URLs**

In `cvat/apps/custom/urls.py`:

```python
    path('train-groups/versions/', views_train_groups.VersionsListView.as_view(),
         name='train-groups-versions'),
    path('train-groups/versions/<int:version_no>/', views_train_groups.VersionDetailView.as_view(),
         name='train-groups-version-detail'),
```

- [ ] **Step 14.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

- [ ] **Step 14.6: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "endpoints: list and detail views for train-group versions"
```

---

### Task 15: Implement rollback endpoint

**Files:**
- Modify: `cvat/apps/custom/views_train_groups.py`
- Modify: `cvat/apps/custom/urls.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 15.1: Write failing test**

Append to `tests/test_train_group_endpoints.py`:

```python
class RollbackTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin3", password="pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("v1.csv", b"train_id,group\n3101F,A\n", "text/csv")},
            format="multipart",
        )
        self.client.post(
            "/api/train-groups/mappings/upload/",
            data={"file": ("v2.csv", b"train_id,group\n3102F,B\n", "text/csv")},
            format="multipart",
        )

    def test_rollback_creates_new_version_with_old_mapping(self):
        resp = self.client.post(
            "/api/train-groups/versions/1/rollback/",
            data={"comment": "back to v1"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["version"], 3)
        # Mapping is back to v1 state
        self.assertTrue(TrainGroupMapping.objects.filter(train_id="3101F", group="A").exists())
        self.assertFalse(TrainGroupMapping.objects.filter(train_id="3102F").exists())
        # New version row records source_version=1 and source_format=rollback
        v3 = TrainGroupMappingVersion.objects.get(version_no=3)
        self.assertEqual(v3.source_version_id, 1)
        self.assertEqual(v3.source_format, "rollback")
        self.assertTrue(v3.is_current)

    def test_rollback_nonexistent_version_404(self):
        resp = self.client.post("/api/train-groups/versions/999/rollback/", format="json")
        self.assertEqual(resp.status_code, 404)

    def test_rollback_requires_admin(self):
        regular = User.objects.create_user("user1", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.post("/api/train-groups/versions/1/rollback/", format="json")
        self.assertEqual(resp.status_code, 403)
```

- [ ] **Step 15.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.RollbackTest -v 2
```

- [ ] **Step 15.3: Implement view**

Append to `cvat/apps/custom/views_train_groups.py`:

```python


from django.shortcuts import get_object_or_404


class RollbackView(APIView):
    """POST /api/train-groups/versions/<version_no>/rollback/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS

    def post(self, request, version_no: int):
        source = get_object_or_404(TrainGroupMappingVersion, version_no=version_no)
        comment = (request.data.get("comment") or f"Rollback to v{source.version_no}").strip()

        # Re-parse the stored csv_text — it's always canonical CSV
        rows, errors = parse_csv(source.csv_text)
        if errors:
            return Response(
                {"errors": [asdict(e) for e in errors]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        version = apply_upload(
            rows=rows, user=request.user, comment=comment,
            raw_input_text=source.csv_text, source_format="rollback",
            source_version=source,
        )
        return Response({
            "version": version.version_no,
            "source_version": source.version_no,
            "diff": version.diff_summary,
        })
```

- [ ] **Step 15.4: Add URL**

In `cvat/apps/custom/urls.py`:

```python
    path('train-groups/versions/<int:version_no>/rollback/',
         views_train_groups.RollbackView.as_view(),
         name='train-groups-rollback'),
```

- [ ] **Step 15.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints -v 2
```

- [ ] **Step 15.6: Commit**

```bash
git add cvat/apps/custom/views_train_groups.py cvat/apps/custom/urls.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "endpoints: POST rollback creates new version from stored snapshot"
```

---

## Phase 5 — Integrate `group` into existing endpoints

### Task 16: Add `annotate_train_group` helper

**Files:**
- Create: `cvat/apps/custom/train_group_query.py`
- Create: `cvat/apps/custom/tests/test_train_group_query.py`

- [ ] **Step 16.1: Write failing test**

Create `cvat/apps/custom/tests/test_train_group_query.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from cvat.apps.engine.models import Task
from cvat.apps.custom.models import TaskTrainMetadata, TrainGroupMapping
from cvat.apps.custom.train_group_query import annotate_train_group


class AnnotateTrainGroupTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner")
        self.task_a = Task.objects.create(name="t_a", owner=owner)
        self.task_b = Task.objects.create(name="t_b", owner=owner)
        TaskTrainMetadata.objects.create(task=self.task_a, train_id="3101F")
        TaskTrainMetadata.objects.create(task=self.task_b, train_id="3199Z")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        # 3199Z deliberately unmapped

    def test_annotates_group_or_none(self):
        qs = annotate_train_group(Task.objects.all().order_by("id"))
        results = {t.id: t.train_group for t in qs}
        self.assertEqual(results[self.task_a.id], "A")
        self.assertIsNone(results[self.task_b.id])

    def test_single_query_no_n_plus_1(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            list(annotate_train_group(Task.objects.all().order_by("id")))
        # One SELECT — the Subquery is inlined; no N+1
        self.assertLessEqual(len(ctx.captured_queries), 2)
```

- [ ] **Step 16.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_query -v 2
```

- [ ] **Step 16.3: Implement helper**

Create `cvat/apps/custom/train_group_query.py`:

```python
# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
Query helpers for annotating Task querysets with the train's group label.

Centralizes the JOIN so every view that exposes `group` uses the same
single-query pattern. Prevents N+1 regressions in the dashboard endpoints.
"""

from django.db.models import OuterRef, Subquery

from .models import TrainGroupMapping


UNGROUPED_SENTINEL = "__ungrouped__"


def annotate_train_group(queryset):
    """
    Annotate a Task queryset with a `train_group` attribute (string or None).

    Uses a correlated subquery on TrainGroupMapping; one SELECT regardless
    of result size.
    """
    sq = TrainGroupMapping.objects.filter(
        train_id=OuterRef("train_metadata__train_id"),
    ).values("group")[:1]
    return queryset.annotate(train_group=Subquery(sq))


def filter_by_group(queryset, group_param: str | None):
    """
    Apply `?group=...` filter (with `__ungrouped__` sentinel) to an
    already-annotated queryset.
    """
    if not group_param:
        return queryset
    group_param = group_param.strip()
    if group_param == UNGROUPED_SENTINEL:
        return queryset.filter(train_group__isnull=True)
    return queryset.filter(train_group=group_param)
```

- [ ] **Step 16.4: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_query -v 2
```

- [ ] **Step 16.5: Commit**

```bash
git add cvat/apps/custom/train_group_query.py cvat/apps/custom/tests/test_train_group_query.py
git commit -m "query: add annotate_train_group helper (single-query Subquery)"
```

---

### Task 17: Wire `group` into `tasks-paginated/` (filter + response field)

**Files:**
- Modify: `cvat/apps/custom/views_analytics.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 17.1: Write failing test**

Append to `tests/test_train_group_endpoints.py`:

```python
from cvat.apps.engine.models import Task


class TasksPaginatedGroupFilterTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner")
        self.t1 = Task.objects.create(name="t1", owner=owner)
        self.t2 = Task.objects.create(name="t2", owner=owner)
        TaskTrainMetadata.objects.create(task=self.t1, train_id="3101F")
        TaskTrainMetadata.objects.create(task=self.t2, train_id="3199Z")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")

    def test_response_includes_group_field(self):
        resp = self.client.get("/api/tasks-paginated/?include_analytics=false")
        self.assertEqual(resp.status_code, 200)
        groups_by_train = {
            r["train_metadata"]["train_id"]: r.get("group")
            for r in resp.data["results"]
        }
        self.assertEqual(groups_by_train["3101F"], "A")
        self.assertIsNone(groups_by_train["3199Z"])

    def test_filter_by_group(self):
        resp = self.client.get(
            "/api/tasks-paginated/?include_analytics=false&group=A",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["train_metadata"]["train_id"], "3101F")

    def test_filter_ungrouped(self):
        resp = self.client.get(
            "/api/tasks-paginated/?include_analytics=false&group=__ungrouped__",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["train_metadata"]["train_id"], "3199Z")
```

- [ ] **Step 17.2: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.TasksPaginatedGroupFilterTest -v 2
```

- [ ] **Step 17.3: Modify `views_analytics.py`**

Open `cvat/apps/custom/views_analytics.py`.

**(a)** At the top of the file, after the existing `from .models import TaskTrainMetadata` line, add:

```python
from .train_group_query import annotate_train_group, filter_by_group
```

**(b)** Find the line that builds the base queryset (around line 90):

```python
            queryset = Task.objects.select_related(
                'project', 'owner', 'assignee', 'data'
            ).prefetch_related(
                'train_metadata'
            ).order_by('-id')
```

Immediately after that block, add:

```python
            queryset = annotate_train_group(queryset)
            queryset = filter_by_group(queryset, request.query_params.get("group"))
```

**(c)** Find the dict-construction block inside the pagination loop (around line 216, the `task_data = {` dict). Add a new key right after `"status": task.status,`:

```python
                        "group": getattr(task, "train_group", None),
```

- [ ] **Step 17.4: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.TasksPaginatedGroupFilterTest -v 2
```

- [ ] **Step 17.5: Commit**

```bash
git add cvat/apps/custom/views_analytics.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "tasks-paginated: add group field and ?group= filter (incl. __ungrouped__)"
```

---

### Task 18: Wire `available_groups` into `tasks-summary/`

**Files:**
- Modify: `cvat/apps/custom/views_analytics.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 18.1: Identify the summary view's response location**

In `cvat/apps/custom/views_analytics.py`, find `class TasksSummaryView`. Locate the dict returned from its `get()` method (the response payload).

- [ ] **Step 18.2: Write failing test**

Append to `tests/test_train_group_endpoints.py`:

```python
class TasksSummaryAvailableGroupsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u2", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner2")
        t1 = Task.objects.create(name="t1", owner=owner)
        t2 = Task.objects.create(name="t2", owner=owner)
        t3 = Task.objects.create(name="t3", owner=owner)
        TaskTrainMetadata.objects.create(task=t1, train_id="3101F")
        TaskTrainMetadata.objects.create(task=t2, train_id="3102F")
        TaskTrainMetadata.objects.create(task=t3, train_id="3103F")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        TrainGroupMapping.objects.create(train_id="3102F", group="A")
        TrainGroupMapping.objects.create(train_id="3103F", group="B")

    def test_available_groups_lists_groups_with_counts(self):
        resp = self.client.get("/api/tasks-summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("available_groups", resp.data)
        by_name = {g["name"]: g["count"] for g in resp.data["available_groups"]}
        # Counts reflect mapped tasks regardless of filter
        self.assertEqual(by_name.get("A"), 2)
        self.assertEqual(by_name.get("B"), 1)
```

- [ ] **Step 18.2a: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.TasksSummaryAvailableGroupsTest -v 2
```

- [ ] **Step 18.3: Implement `available_groups`**

In `cvat/apps/custom/views_analytics.py`, near the top alongside the existing imports, add:

```python
from django.db.models import Count
from .models import TrainGroupMapping
```

(skip duplicates if `Count` or `TrainGroupMapping` is already imported).

Inside `TasksSummaryView.get()`, just before the final `return Response(...)`, compute the list:

```python
            available_groups = list(
                TrainGroupMapping.objects.values("group")
                .annotate(count=Count(
                    "train_id",
                    filter=models.Q(  # restrict count to trains with at least one task
                        train_id__in=TaskTrainMetadata.objects.values("train_id")
                    ),
                ))
                .order_by("group")
                .values_list("group", "count")
            )
            available_groups_payload = [
                {"name": name, "count": count} for name, count in available_groups if count > 0
            ]
```

And add `available_groups_payload` to the response dict under key `"available_groups"`. Locate the response dictionary in the view (it's where `response_data` or similar is assembled) and append:

```python
            response_data["available_groups"] = available_groups_payload
```

(Adapt variable names to match what's already in that view.)

Also add `?group=` filtering to the summary itself by mirroring Task 17's pattern: annotate + filter before counting.

- [ ] **Step 18.4: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.TasksSummaryAvailableGroupsTest -v 2
```

- [ ] **Step 18.5: Commit**

```bash
git add cvat/apps/custom/views_analytics.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "tasks-summary: include available_groups + accept ?group= filter"
```

---

### Task 19: Add `group` to task detail (`tasks-extended/<id>/`)

**Files:**
- Modify: `cvat/apps/custom/views_task_extension.py`
- Modify: `cvat/apps/custom/tests/test_train_group_endpoints.py`

- [ ] **Step 19.1: Inspect the existing detail view**

```bash
grep -n "ExtendedTaskViewSet\|def retrieve\|to_representation" cvat/apps/custom/views_task_extension.py
```

Identify where the single-task response payload is assembled.

- [ ] **Step 19.2: Write failing test**

Append to `tests/test_train_group_endpoints.py`:

```python
class ExtendedTaskGroupTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u3", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner3")
        self.t1 = Task.objects.create(name="t1", owner=owner)
        TaskTrainMetadata.objects.create(task=self.t1, train_id="3101F")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")

    def test_detail_includes_group(self):
        resp = self.client.get(f"/api/tasks-extended/{self.t1.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("group"), "A")
```

- [ ] **Step 19.3: Verify failure**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.ExtendedTaskGroupTest -v 2
```

- [ ] **Step 19.4: Inject `group` into the response**

In `cvat/apps/custom/views_task_extension.py`, inside `ExtendedTaskViewSet`:
- Override `get_queryset()` to wrap the existing queryset with `annotate_train_group(...)` (import it from `.train_group_query`).
- In the serializer or `to_representation`, add `data["group"] = getattr(instance, "train_group", None)`.

Concretely, near the top of the file add:

```python
from .train_group_query import annotate_train_group
```

Inside the viewset, add:

```python
    def get_queryset(self):
        return annotate_train_group(super().get_queryset())
```

And in the response-shaping method (likely a `to_representation` or wherever the dict is built), include:

```python
        data["group"] = getattr(instance, "train_group", None)
```

(If the existing view doesn't use a serializer, add `"group": getattr(instance, "train_group", None)` to the response dict directly.)

- [ ] **Step 19.5: Verify pass**

```bash
python manage.py test cvat.apps.custom.tests.test_train_group_endpoints.ExtendedTaskGroupTest -v 2
```

- [ ] **Step 19.6: Commit**

```bash
git add cvat/apps/custom/views_task_extension.py cvat/apps/custom/tests/test_train_group_endpoints.py
git commit -m "tasks-extended: include group field in detail response"
```

---

## Phase 6 — Final verification

### Task 20: Run full test suite + manual smoke test

- [ ] **Step 20.1: Full test run**

```bash
python manage.py test cvat.apps.custom -v 2
```

Expected: all tests pass (parser + diff/apply + endpoints + query helper).

- [ ] **Step 20.2: Boot the dev server**

```bash
python manage.py runserver 0.0.0.0:8000
```

- [ ] **Step 20.3: Smoke test as admin via curl**

In another shell (replace `<admin_session_cookie>` or use basic auth):

```bash
# Download the template
curl -u admin:<password> http://localhost:8000/api/train-groups/mappings/template.csv

# Upload an initial schedule
echo "train_id,group
3101F,A
3102F,B" > /tmp/sched.csv
curl -u admin:<password> -F "file=@/tmp/sched.csv" -F "comment=initial smoke" \
    http://localhost:8000/api/train-groups/mappings/upload/

# List mappings
curl -u admin:<password> http://localhost:8000/api/train-groups/mappings/

# Inspect version history
curl -u admin:<password> http://localhost:8000/api/train-groups/versions/
curl -u admin:<password> http://localhost:8000/api/train-groups/versions/1/

# Verify the dashboard endpoint surfaces group
curl -u admin:<password> "http://localhost:8000/api/tasks-paginated/?include_analytics=false&page_size=5"
curl -u admin:<password> "http://localhost:8000/api/tasks-summary/"
```

Expected: all return 200 with sensible payloads; `available_groups` populated; `group` field present on task rows.

- [ ] **Step 20.4: Tag the milestone**

```bash
git log --oneline -25
# Verify all 20-ish commits are present on the branch
```

---

## Spec coverage map

| Spec section | Implementing task(s) |
|---|---|
| §6.1 `TrainGroupMapping` model | Task 2 |
| §6.2 `TrainGroupMappingVersion` model | Task 2 |
| §6.4 Migration | Task 2 |
| §7 Subquery annotation strategy | Task 16, integrated in 17/19 |
| §8.1 Changes to existing endpoints | Task 17, 18, 19 |
| §8.2 New endpoints (mappings, template, export, upload, versions, rollback) | Tasks 11, 12, 13, 14, 15 |
| §8.3 Permission constant | Task 10 |
| §9 CSV format & validation | Task 4 |
| §9.1 xlsx parsing | Task 5 |
| §9.1 Paste parsing | Task 6 |
| §9.3 Parser module | Tasks 3–8 |
| §10 Upload flow (parse → diff → dry-run → apply, transactional) | Tasks 7, 8, 13 |
| §11 Rollback | Task 15 |
| §13 Edge cases — duplicates, invalid chars, empty, BOM, whitespace | Task 4 |
| §13 Edge cases — xlsx first-sheet, integer cells, corrupt bytes | Task 5 |
| §13 Edge cases — paste separator, single column | Task 6 |
| §14 Tests (unit + integration + perf regression) | Tasks 3–19 (TDD throughout); query-count test in Task 16 |

## Frontend follow-up (separate plan in `Orochi-UI`)

After backend ships, write `Orochi-UI/docs/.../plans/2026-MM-DD-train-group-frontend.md` covering:
- New `Group` column + `Group` filter dropdown on the dashboard task table
- `Group` field on task detail page
- New `/train-groups` admin route with Current Schedule + Version History cards
- Upload dialog with two tabs (Upload file / Paste from Excel) and dry-run preview
- Rollback confirmation flow

All backend contracts above are stable once Phase 5 lands.
