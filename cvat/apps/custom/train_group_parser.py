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


import csv
import io
import re
from io import BytesIO

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
        import zipfile
        wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
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
