# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Server-side 'today' helper.

Validation rules and the CSV-rewrite hook both need a single, consistent
definition of 'now' that is independent of the requesting user's locale.
The deployed region operates on Asia/Tokyo, so that is the default.

The timezone can be overridden via settings.SCHEDULE_TZ. We use getattr
with a default so this module does not require a settings edit when the
allowlist prohibits one.
"""

from __future__ import annotations

import datetime
import zoneinfo

from django.conf import settings

from .constants import DEFAULT_SCHEDULE_TZ


def server_today() -> datetime.date:
    """Return the current date in the configured schedule timezone.

    Reads settings.SCHEDULE_TZ lazily so tests can override settings
    without re-importing this module.
    """
    tz_name = getattr(settings, "SCHEDULE_TZ", DEFAULT_SCHEDULE_TZ)
    return datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).date()


def server_today_iso() -> str:
    """Return server_today() formatted as an ISO YYYY-MM-DD string."""
    return server_today().isoformat()
