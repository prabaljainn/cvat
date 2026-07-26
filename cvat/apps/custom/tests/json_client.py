# Copyright (C) 2026 CVAT Custom
# SPDX-License-Identifier: MIT

from rest_framework.test import APIClient


class JsonAPIClient(APIClient):
    """APIClient that sends JSON bodies by default.

    CVAT's DRF settings accept only JSON request parsers, so the
    multipart format APIClient uses out of the box is rejected with 415
    before reaching any view. Individual calls can still pass
    format="multipart" for endpoints that opt into upload parsers.
    """

    def post(self, path, data=None, format=None, content_type=None, **extra):
        if format is None and content_type is None:
            format = "json"
        return super().post(
            path, data=data, format=format, content_type=content_type, **extra
        )

    def patch(self, path, data=None, format=None, content_type=None, **extra):
        if format is None and content_type is None:
            format = "json"
        return super().patch(
            path, data=data, format=format, content_type=content_type, **extra
        )
