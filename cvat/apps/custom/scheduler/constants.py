# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Constants for the train-group schedule sub-module.

Constants live here (not next to the model) so the model module stays
focused on schema and so views/serializers/resolver can share the same
values without circular imports.
"""

from __future__ import annotations

# Source identifier for a row created by an admin via POST /schedule/.
SOURCE_MANUAL = "manual"

# Source identifier for a row created automatically when the CSV upload
# drops a group that the most recent schedule still referenced.
SOURCE_CSV_REWRITE = "csv_rewrite"

# Window in which an identical POST is treated as a re-submit, not a new row.
# Chosen at 60s because the UI may double-submit on slow networks; longer
# windows risk hiding a legitimate intentional re-save.
DEDUPE_WINDOW_SECONDS = 60

# Inclusive ceiling for how far in the future start_date may be.
# 365 keeps the UI's date picker meaningful and prevents accidental
# year-2099 typos from being persisted.
MAX_FUTURE_DAYS = 365

# Sequence length bounds. Lower bound 1 because an empty cycle is meaningless;
# upper bound 100 caps storage and keeps the rotation picker scannable.
MIN_SEQUENCE_LEN = 1
MAX_SEQUENCE_LEN = 100

# Comment is optional but capped so a stray paste cannot bloat the row.
MAX_COMMENT_LEN = 500

# Default timezone used to compute server_today when settings.SCHEDULE_TZ
# is not configured. Asia/Tokyo matches the deployed operating region.
DEFAULT_SCHEDULE_TZ = "Asia/Tokyo"

# Warning code emitted when a CSV upload would leave the most recent
# schedule with an empty sequence; we skip the rewrite in that case.
WARNING_SCHEDULE_WOULD_BE_EMPTY = "schedule_would_be_empty"
