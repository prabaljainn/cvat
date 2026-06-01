# Copyright (C) 2025 CVAT Custom S3 Utils
# SPDX-License-Identifier: MIT

"""
AWS S3 Presigned URL Generator

This module provides functionality to generate presigned URLs for S3 objects,
particularly for video files.
"""

import boto3
import os
from typing import Optional, List, Dict
from botocore.exceptions import ClientError, NoCredentialsError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Recognised video extensions (lower-case, with leading dot).
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']

# Thumbnail layout convention inside a task's S3 folder:
#   <folder>/<camN>.mp4
#   <folder>/matrix/<camN>/<camN>.vtt
#   <folder>/matrix/<camN>/sprite_001.jpg, sprite_002.jpg, ...
MATRIX_DIR = 'matrix'
SPRITE_PREFIX = 'sprite_'
SPRITE_EXT = '.jpg'
VTT_EXT = '.vtt'


def _browser_cache_control(expiration: int) -> str:
    """Cache-Control header value matching a presigned URL's lifetime."""
    return f"private, max-age={expiration}"


# Server-side cache of the assembled videos+thumbnails payload. Caching it keeps
# the presigned URLs *stable* across requests (so browsers/CDNs cache the actual
# video/sprite bytes) and skips the S3 listing on hits. The TTL is kept below the
# presign window so a cached URL is never served past its own expiry.
VIDEOS_CACHE_KEY_PREFIX = 'custom:task_videos:v1'
VIDEOS_CACHE_MARGIN_SECONDS = 600


def _videos_cache_key(bucket_name: str, folder_path: str, expiration: int) -> str:
    return f"{VIDEOS_CACHE_KEY_PREFIX}:{bucket_name}:{folder_path}:{expiration}"


def get_videos_with_thumbnails_cached(generator, bucket_name: str, folder_path: str,
                                      expiration: int, *, cache=None,
                                      refresh: bool = False) -> List[Dict]:
    """
    Cached wrapper around :meth:`S3PresignedURLGenerator.get_videos_with_thumbnails`.

    Args:
        generator: an :class:`S3PresignedURLGenerator`.
        cache: cache backend (defaults to Django's ``default`` cache). Injectable
            so the caching logic is testable without Django/Redis.
        refresh: when True, ignore any cached value and re-list from S3.
    """
    if cache is None:
        from django.core.cache import cache as _django_cache
        cache = _django_cache

    key = _videos_cache_key(bucket_name, folder_path, expiration)

    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    payload = generator.get_videos_with_thumbnails(bucket_name, folder_path, expiration)
    ttl = max(60, expiration - VIDEOS_CACHE_MARGIN_SECONDS)
    cache.set(key, payload, ttl)
    return payload


class S3PresignedURLGenerator:
    """Handle S3 operations and presigned URL generation."""

    def __init__(self, aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None,
                 region_name: str = 'us-east-1',
                 bucket_name: Optional[str] = None):
        """
        Initialize S3 client with credentials.

        Args:
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            region_name: AWS region name
            bucket_name: Default S3 bucket name
        """
        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("AWS credentials are required")

        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name
            )
            self.region_name = region_name
            self.bucket_name = bucket_name
        except Exception as e:
            raise ValueError(f"Failed to initialize S3 client: {str(e)}")

    @staticmethod
    def _normalize_prefix(folder_path: str) -> str:
        """Normalise an S3 folder prefix: '' for root, otherwise trailing '/'."""
        if not folder_path or folder_path == '/':
            return ''
        if not folder_path.endswith('/'):
            return folder_path + '/'
        return folder_path

    def _list_all_objects(self, bucket_name: str, folder_path: str = '') -> List[Dict]:
        """
        List every (non-folder) object under a prefix in a single paginated scan.

        Returns dicts with raw ``key``/``size``/``last_modified`` (datetime).
        Callers format/filter as needed; doing the listing once lets us derive
        videos *and* their thumbnail assets without extra S3 round-trips.
        """
        objects: List[Dict] = []
        try:
            prefix = self._normalize_prefix(folder_path)

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in pages:
                if 'Contents' not in page:
                    continue
                for obj in page['Contents']:
                    key = obj['Key']
                    # Skip folders (keys ending with /)
                    if key.endswith('/'):
                        continue
                    objects.append({
                        'key': key,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                    })

            return objects

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise ValueError(f"Bucket '{bucket_name}' does not exist")
            elif error_code == 'AccessDenied':
                raise PermissionError(f"Access denied to bucket '{bucket_name}'")
            else:
                raise Exception(f"Error listing objects: {str(e)}")
        except NoCredentialsError:
            raise ValueError("AWS credentials not configured")

    def list_videos_in_folder(self, bucket_name: str, folder_path: str = '') -> List[Dict]:
        """
        List all video files in a specific S3 folder.

        Args:
            bucket_name: Name of the S3 bucket
            folder_path: Path to folder in bucket (e.g., 'videos/' or '')

        Returns:
            List of dictionaries containing video file information
        """
        videos = []
        for obj in self._list_all_objects(bucket_name, folder_path):
            key = obj['key']
            if any(key.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                videos.append({
                    'key': key,
                    'size': obj['size'],
                    'last_modified': obj['last_modified'].isoformat(),
                    'filename': os.path.basename(key),
                })
        return videos

    def generate_presigned_url(self, bucket_name: str, object_key: str,
                               expiration: int = 3600,
                               cache_control: Optional[str] = None) -> str:
        """
        Generate a presigned URL for an S3 object.

        Args:
            bucket_name: Name of the S3 bucket
            object_key: Key/path of the object in S3
            expiration: Time in seconds for the presigned URL to remain valid (default: 1 hour)
            cache_control: Optional value for the response ``Cache-Control`` header.
                When set, S3 returns it on the GET so the browser can cache the
                bytes without revalidating.

        Returns:
            Presigned URL as string
        """
        try:
            logger.info(f"Generating presigned URL for bucket: {bucket_name}, key: {object_key}")
            params = {
                'Bucket': bucket_name,
                'Key': object_key,
            }
            if cache_control is not None:
                params['ResponseCacheControl'] = cache_control
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            return url

        except ClientError as e:
            raise Exception(f"Error generating presigned URL: {str(e)}")
        except NoCredentialsError:
            raise ValueError("AWS credentials not configured")

    def get_video_presigned_url(self, bucket_name: str, video_path: str,
                                expiration: int = 3600) -> Dict:
        """
        Get presigned URL for a specific video file.

        Args:
            bucket_name: Name of the S3 bucket
            video_path: Path to video file in S3
            expiration: Time in seconds for URL to remain valid

        Returns:
            Dictionary with video information and presigned URL
        """
        try:
            # Check if object exists
            self.s3_client.head_object(Bucket=bucket_name, Key=video_path)

            # Generate presigned URL
            url = self.generate_presigned_url(bucket_name, video_path, expiration)

            return {
                'video_path': video_path,
                'filename': os.path.basename(video_path),
                'presigned_url': url,
                'expiration_seconds': expiration,
                'generated_at': datetime.now().isoformat()
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise FileNotFoundError(f"Video file '{video_path}' not found in bucket '{bucket_name}'")
            else:
                raise Exception(f"Error getting video: {str(e)}")

    def get_all_videos_with_urls(self, bucket_name: str, folder_path: str = '',
                                  expiration: int = 3600) -> List[Dict]:
        """
        Get presigned URLs for all videos in a folder.

        Args:
            bucket_name: Name of the S3 bucket
            folder_path: Path to folder in bucket
            expiration: Time in seconds for URLs to remain valid

        Returns:
            List of dictionaries with video info and presigned URLs
        """
        videos = self.list_videos_in_folder(bucket_name, folder_path)

        result = []
        for video in videos:
            url = self.generate_presigned_url(bucket_name, video['key'], expiration)
            result.append({
                'key': video['key'],
                'filename': video['filename'],
                'size': video['size'],
                'last_modified': video['last_modified'],
                'presigned_url': url,
                'expiration_seconds': expiration
            })

        return result

    def get_videos_with_thumbnails(self, bucket_name: str, folder_path: str = '',
                                   expiration: int = 3600) -> List[Dict]:
        """
        Get presigned URLs for all videos in a folder, each with its scrubbing
        thumbnails (a WebVTT track + sprite images) discovered under
        ``<folder>/matrix/<video-basename>/``.

        Uses a single S3 listing for both the videos and their thumbnail assets.

        Returns:
            List of per-video dicts: the same shape as
            :meth:`get_all_videos_with_urls` plus a nested ``thumbnails`` block.
        """
        objects = self._list_all_objects(bucket_name, folder_path)
        matrix_root = f"{self._normalize_prefix(folder_path)}{MATRIX_DIR}/"

        result = []
        for obj in objects:
            key = obj['key']
            if not any(key.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                continue

            basename = os.path.splitext(os.path.basename(key))[0]
            result.append({
                'key': key,
                'filename': os.path.basename(key),
                'size': obj['size'],
                'last_modified': obj['last_modified'].isoformat(),
                'presigned_url': self.generate_presigned_url(
                    bucket_name, key, expiration,
                    cache_control=_browser_cache_control(expiration),
                ),
                'expiration_seconds': expiration,
                'thumbnails': self._build_thumbnails(
                    bucket_name, objects, matrix_root, basename, expiration
                ),
            })

        return result

    def _build_thumbnails(self, bucket_name: str, objects: List[Dict], matrix_root: str,
                          basename: str, expiration: int) -> Dict:
        """Collect the VTT + sprite presigned URLs for one video's matrix folder."""
        cam_prefix = f"{matrix_root}{basename}/"

        vtt_keys = []
        sprite_keys = []
        for obj in objects:
            key = obj['key']
            if not key.startswith(cam_prefix):
                continue
            name = os.path.basename(key).lower()
            if name.endswith(VTT_EXT):
                vtt_keys.append(key)
            elif name.startswith(SPRITE_PREFIX) and name.endswith(SPRITE_EXT):
                sprite_keys.append(key)

        vtt_url = None
        if vtt_keys:
            # Prefer the conventionally-named "<basename>.vtt"; else first by name.
            preferred = f"{cam_prefix}{basename}{VTT_EXT}"
            chosen = preferred if preferred in vtt_keys else sorted(vtt_keys)[0]
            vtt_url = self.generate_presigned_url(
                bucket_name, chosen, expiration,
                cache_control=_browser_cache_control(expiration),
            )

        sprites = [
            {
                'filename': os.path.basename(key),
                'url': self.generate_presigned_url(
                    bucket_name, key, expiration,
                    cache_control=_browser_cache_control(expiration),
                ),
            }
            for key in sorted(sprite_keys)
        ]

        return {
            'available': bool(vtt_url) or bool(sprites),
            'vtt_url': vtt_url,
            'sprites': sprites,
        }


# Global singleton instance
_s3_generator_instance = None
_s3_bucket_name = None


def create_s3_generator_from_env():
    """
    Create or return cached S3PresignedURLGenerator using environment variables.
    Uses singleton pattern to avoid creating multiple boto3 clients.

    Environment variables:
    - CVAT_S3_ACCESS_KEY_ID: AWS access key
    - CVAT_S3_SECRET_ACCESS_KEY: AWS secret key
    - CVAT_S3_REGION: AWS region (default: us-east-1)
    - CVAT_S3_BUCKET_NAME: S3 bucket name

    Returns:
        Tuple of (S3PresignedURLGenerator instance, bucket_name)

    Raises:
        ValueError: If required environment variables are missing
    """
    global _s3_generator_instance, _s3_bucket_name

    # Return cached instance if available
    if _s3_generator_instance is not None and _s3_bucket_name is not None:
        return _s3_generator_instance, _s3_bucket_name

    # Read environment variables
    aws_access_key_id = os.getenv('CVAT_S3_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('CVAT_S3_SECRET_ACCESS_KEY')
    region = os.getenv('CVAT_S3_REGION', 'us-east-1')
    bucket_name = os.getenv('CVAT_S3_BUCKET_NAME')

    if not aws_access_key_id:
        raise ValueError("CVAT_S3_ACCESS_KEY_ID environment variable is not set")
    if not aws_secret_access_key:
        raise ValueError("CVAT_S3_SECRET_ACCESS_KEY environment variable is not set")
    if not bucket_name:
        raise ValueError("CVAT_S3_BUCKET_NAME environment variable is not set")

    # Create and cache the generator
    _s3_generator_instance = S3PresignedURLGenerator(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region,
        bucket_name=bucket_name
    )
    _s3_bucket_name = bucket_name

    logger.info(f"Loaded S3 configuration from env. Bucket: {bucket_name}")
    return _s3_generator_instance, _s3_bucket_name

