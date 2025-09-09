#!/usr/bin/env python3
"""
Simple script to download annotated frames from CVAT
Works with browser-based authentication (login via web interface first)
"""

import requests
import json
import sys
from typing import List, Dict, Optional

# CVAT API configuration
BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "#@Pjain9329"
# Basic Auth header (base64 encoded admin:#@Pjain9329)
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

# Headers for all requests
HEADERS = {
    'Authorization': BASIC_AUTH_HEADER
}

def get_jobs() -> List[Dict]:
    """Get all available jobs"""
    try:
        response = requests.get(f"{BASE_URL}/api/jobs", params={"page_size": 100}, headers=HEADERS)
        if response.status_code == 200:
            return response.json()['results']
        elif response.status_code == 401:
            print("❌ Basic Authentication failed!")
            print(f"Credentials: {USERNAME} / {PASSWORD}")
            print("Check if the Basic Auth header is correct")
            return []
        else:
            print(f"❌ Failed to get jobs: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def get_task_labels(task_id: int) -> List[Dict]:
    """Get labels for a specific task"""
    try:
        response = requests.get(f"{BASE_URL}/api/labels", params={
            "task_id": task_id,
            "page_size": 100
        }, headers=HEADERS)
        if response.status_code == 200:
            return response.json()['results']
        else:
            print(f"❌ Failed to get labels: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error getting labels: {e}")
        return []

def download_frames(job_id: int, label_id: Optional[int] = None) -> bool:
    """Download annotated frames"""
    params = {'job_id': job_id}
    if label_id:
        params['label_id'] = label_id

    try:
        response = requests.get(
            f"{BASE_URL}/api/custom/download-annotated-frames/",
            params=params,
            headers=HEADERS
        )

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'application/zip' in content_type:
                filename = f"job_{job_id}_frames.zip"
                if label_id:
                    filename = f"job_{job_id}_label_{label_id}_frames.zip"

                with open(filename, 'wb') as f:
                    f.write(response.content)

                print(f"✅ Downloaded: {filename} ({len(response.content):,} bytes)")
                return True
            else:
                print(f"📄 Response: {response.text}")
                return True
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

def main():
    print("🎯 Simple CVAT Frame Downloader")
    print("=" * 40)

    # Get jobs
    jobs = get_jobs()
    if not jobs:
        sys.exit(1)

    print(f"\n📋 Found {len(jobs)} jobs:")
    for i, job in enumerate(jobs, 1):
        task_name = job.get('task', {}).get('name', 'Unknown')
        print(f"  {i}. Job {job['id']} - {task_name} ({job.get('status', 'Unknown')})")

    # Quick test with first job
    if jobs:
        first_job = jobs[0]
        job_id = first_job['id']
        task_id = first_job.get('task', {}).get('id')

        print(f"\n🧪 Testing download with Job {job_id}...")

        # Get labels
        if task_id:
            labels = get_task_labels(task_id)
            if labels:
                print(f"📋 Available labels: {', '.join([l['name'] for l in labels])}")

        # Download all frames for this job
        success = download_frames(job_id)

        if success:
            print("🎉 Test download completed!")
        else:
            print("❌ Test download failed!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
