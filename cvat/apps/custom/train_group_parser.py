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
