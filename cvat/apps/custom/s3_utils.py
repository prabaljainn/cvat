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

    def list_videos_in_folder(self, bucket_name: str, folder_path: str = '') -> List[Dict]:
        """
        List all video files in a specific S3 folder.

        Args:
            bucket_name: Name of the S3 bucket
            folder_path: Path to folder in bucket (e.g., 'videos/' or '')

        Returns:
            List of dictionaries containing video file information
        """
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
        videos = []

        try:
            # Ensure folder path ends with '/' if not empty and not root
            if folder_path and folder_path != '/' and not folder_path.endswith('/'):
                folder_path += '/'

            # Handle root folder
            if folder_path == '/':
                folder_path = ''

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket_name, Prefix=folder_path)

            for page in pages:
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    key = obj['Key']
                    # Skip folders (keys ending with /)
                    if key.endswith('/'):
                        continue
                    # Check if it's a video file
                    if any(key.lower().endswith(ext) for ext in video_extensions):
                        videos.append({
                            'key': key,
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'filename': os.path.basename(key)
                        })

            return videos

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise ValueError(f"Bucket '{bucket_name}' does not exist")
            elif error_code == 'AccessDenied':
                raise PermissionError(f"Access denied to bucket '{bucket_name}'")
            else:
                raise Exception(f"Error listing videos: {str(e)}")
        except NoCredentialsError:
            raise ValueError("AWS credentials not configured")

    def generate_presigned_url(self, bucket_name: str, object_key: str,
                               expiration: int = 3600) -> str:
        """
        Generate a presigned URL for an S3 object.

        Args:
            bucket_name: Name of the S3 bucket
            object_key: Key/path of the object in S3
            expiration: Time in seconds for the presigned URL to remain valid (default: 1 hour)

        Returns:
            Presigned URL as string
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': object_key
                },
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

    return _s3_generator_instance, _s3_bucket_name

