# Copyright (C) 2026 CVAT Custom S3 Videos Module
# SPDX-License-Identifier: MIT

"""
Tests for S3 video thumbnail (VTT + sprite) discovery and presigned-URL caching.

These exercise the Django-free ``S3PresignedURLGenerator`` logic, so they run
under plain ``unittest`` with a mocked boto3 client (no test DB required).
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from cvat.apps.custom.s3_utils import S3PresignedURLGenerator


def _obj(key, size=10):
    return {
        "Key": key,
        "Size": size,
        "LastModified": datetime(2026, 3, 1, 4, 57, 25, tzinfo=timezone.utc),
    }


def make_generator(keys):
    """Build a generator whose S3 client is a mock returning ``keys``."""
    gen = S3PresignedURLGenerator(
        aws_access_key_id="x",
        aws_secret_access_key="y",
        region_name="us-east-1",
        bucket_name="bkt",
    )
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [_obj(k) for k in keys]}
    ]
    client.generate_presigned_url.side_effect = (
        lambda op, Params, ExpiresIn: (
            f"https://signed/{Params['Key']}"
            f"|cc={Params.get('ResponseCacheControl')}|exp={ExpiresIn}"
        )
    )
    gen.s3_client = client
    return gen, client


class GetVideosWithThumbnailsTest(unittest.TestCase):
    def test_attaches_vtt_and_sprites_from_matrix_subfolder(self):
        keys = [
            "1780296861/cam1.mp4",
            "1780296861/cam2.mp4",
            "1780296861/matrix/cam1/cam1.vtt",
            "1780296861/matrix/cam1/sprite_002.jpg",
            "1780296861/matrix/cam1/sprite_001.jpg",
            "1780296861/matrix/cam1/poster.jpg",  # not a sprite -> excluded
            "1780296861/matrix/cam2/cam2.vtt",
            "1780296861/matrix/cam2/sprite_001.jpg",
        ]
        gen, _ = make_generator(keys)

        videos = gen.get_videos_with_thumbnails("bkt", "1780296861", expiration=36000)

        self.assertEqual([v["filename"] for v in videos], ["cam1.mp4", "cam2.mp4"])

        th = videos[0]["thumbnails"]
        self.assertTrue(th["available"])
        self.assertIn("matrix/cam1/cam1.vtt", th["vtt_url"])
        # sprites are sorted and poster.jpg is excluded
        self.assertEqual(
            [s["filename"] for s in th["sprites"]],
            ["sprite_001.jpg", "sprite_002.jpg"],
        )
        self.assertIn("matrix/cam1/sprite_001.jpg", th["sprites"][0]["url"])

    def test_video_without_matrix_folder_reports_unavailable(self):
        gen, _ = make_generator(["1770382883/cam6.mp4"])

        videos = gen.get_videos_with_thumbnails("bkt", "1770382883", expiration=36000)

        th = videos[0]["thumbnails"]
        self.assertFalse(th["available"])
        self.assertIsNone(th["vtt_url"])
        self.assertEqual(th["sprites"], [])

    def test_prefers_basename_vtt_when_several_present(self):
        keys = [
            "p/cam1.mp4",
            "p/matrix/cam1/aaa.vtt",
            "p/matrix/cam1/cam1.vtt",
        ]
        gen, _ = make_generator(keys)

        videos = gen.get_videos_with_thumbnails("bkt", "p", expiration=100)

        self.assertIn("matrix/cam1/cam1.vtt", videos[0]["thumbnails"]["vtt_url"])

    def test_presigns_with_response_cache_control(self):
        gen, _ = make_generator(["p/cam1.mp4", "p/matrix/cam1/sprite_001.jpg"])

        videos = gen.get_videos_with_thumbnails("bkt", "p", expiration=36000)

        self.assertIn("cc=private, max-age=36000", videos[0]["presigned_url"])
        self.assertIn(
            "cc=private, max-age=36000",
            videos[0]["thumbnails"]["sprites"][0]["url"],
        )


class PresignedUrlCacheControlTest(unittest.TestCase):
    def test_passes_response_cache_control_when_given(self):
        gen, client = make_generator([])
        gen.generate_presigned_url("bkt", "k.mp4", 36000, cache_control="private, max-age=36000")
        self.assertEqual(
            client.generate_presigned_url.call_args.kwargs["Params"]["ResponseCacheControl"],
            "private, max-age=36000",
        )

    def test_omits_cache_control_when_not_given(self):
        gen, client = make_generator([])
        gen.generate_presigned_url("bkt", "k.mp4", 36000)
        self.assertNotIn(
            "ResponseCacheControl",
            client.generate_presigned_url.call_args.kwargs["Params"],
        )


class FakeCache:
    """Minimal dict-backed stand-in for Django's cache."""

    def __init__(self):
        self.store = {}
        self.sets = []  # (key, value, timeout) for assertions

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value, timeout=None):
        self.store[key] = value
        self.sets.append((key, value, timeout))


class CachedVideosTest(unittest.TestCase):
    def test_miss_calls_generator_and_caches_with_ttl(self):
        from cvat.apps.custom.s3_utils import get_videos_with_thumbnails_cached

        gen = MagicMock()
        gen.get_videos_with_thumbnails.return_value = [{"x": 1}]
        cache = FakeCache()

        out = get_videos_with_thumbnails_cached(gen, "bkt", "p", 36000, cache=cache)

        self.assertEqual(out, [{"x": 1}])
        gen.get_videos_with_thumbnails.assert_called_once_with("bkt", "p", 36000)
        self.assertEqual(len(cache.sets), 1)
        _, value, timeout = cache.sets[0]
        self.assertEqual(value, [{"x": 1}])
        self.assertEqual(timeout, 35400)  # 36000 - 600 margin

    def test_hit_returns_cached_without_calling_generator(self):
        from cvat.apps.custom.s3_utils import (
            get_videos_with_thumbnails_cached,
            _videos_cache_key,
        )

        gen = MagicMock()
        cache = FakeCache()
        cache.store[_videos_cache_key("bkt", "p", 36000)] = [{"cached": True}]

        out = get_videos_with_thumbnails_cached(gen, "bkt", "p", 36000, cache=cache)

        self.assertEqual(out, [{"cached": True}])
        gen.get_videos_with_thumbnails.assert_not_called()

    def test_empty_list_is_a_valid_cache_hit(self):
        from cvat.apps.custom.s3_utils import (
            get_videos_with_thumbnails_cached,
            _videos_cache_key,
        )

        gen = MagicMock()
        cache = FakeCache()
        cache.store[_videos_cache_key("bkt", "p", 36000)] = []

        out = get_videos_with_thumbnails_cached(gen, "bkt", "p", 36000, cache=cache)

        self.assertEqual(out, [])
        gen.get_videos_with_thumbnails.assert_not_called()

    def test_refresh_bypasses_cache(self):
        from cvat.apps.custom.s3_utils import (
            get_videos_with_thumbnails_cached,
            _videos_cache_key,
        )

        gen = MagicMock()
        gen.get_videos_with_thumbnails.return_value = [{"fresh": True}]
        cache = FakeCache()
        cache.store[_videos_cache_key("bkt", "p", 36000)] = [{"stale": True}]

        out = get_videos_with_thumbnails_cached(
            gen, "bkt", "p", 36000, cache=cache, refresh=True
        )

        self.assertEqual(out, [{"fresh": True}])
        gen.get_videos_with_thumbnails.assert_called_once()

    def test_ttl_has_a_floor_for_short_expirations(self):
        from cvat.apps.custom.s3_utils import get_videos_with_thumbnails_cached

        gen = MagicMock()
        gen.get_videos_with_thumbnails.return_value = []
        cache = FakeCache()

        get_videos_with_thumbnails_cached(gen, "bkt", "p", 100, cache=cache)

        self.assertEqual(cache.sets[0][2], 60)


class ListVideosInFolderTest(unittest.TestCase):
    def test_returns_only_video_files_with_isoformat_dates(self):
        keys = [
            "p/cam1.mp4",
            "p/matrix/cam1/cam1.vtt",  # not a video
            "p/notes.txt",             # not a video
        ]
        gen, _ = make_generator(keys)

        videos = gen.list_videos_in_folder("bkt", "p")

        self.assertEqual([v["filename"] for v in videos], ["cam1.mp4"])
        # last_modified is serialised to an ISO string for the API response
        self.assertIsInstance(videos[0]["last_modified"], str)
