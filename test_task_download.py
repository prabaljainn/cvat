#!/usr/bin/env python3
"""
Test script for the new Task-based download API
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

def get_tasks() -> List[Dict]:
    """Get all available tasks"""
    try:
        response = requests.get(f"{BASE_URL}/api/tasks", params={"page_size": 100}, headers=HEADERS)
        if response.status_code == 200:
            return response.json()['results']
        elif response.status_code == 401:
            print("❌ Basic Authentication failed!")
            print(f"Credentials: {USERNAME} / {PASSWORD}")
            return []
        else:
            print(f"❌ Failed to get tasks: {response.status_code}")
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

def get_task_jobs(task_id: int) -> List[Dict]:
    """Get jobs for a specific task"""
    try:
        response = requests.get(f"{BASE_URL}/api/jobs", params={
            "task_id": task_id,
            "page_size": 100
        }, headers=HEADERS)
        if response.status_code == 200:
            return response.json()['results']
        else:
            print(f"❌ Failed to get jobs: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error getting jobs: {e}")
        return []

def download_task_frames(task_id: int, label_id: Optional[int] = None) -> bool:
    """Download annotated frames for entire task"""
    params = {'task_id': task_id}
    if label_id:
        params['label_id'] = label_id

    try:
        print(f"📥 Downloading frames for task {task_id}...")
        response = requests.get(
            f"{BASE_URL}/api/custom/download-task-frames/",
            params=params,
            headers=HEADERS
        )

        print(f"📡 Response Status: {response.status_code}")

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'application/zip' in content_type:
                filename = f"task_{task_id}_frames.zip"
                if label_id:
                    filename = f"task_{task_id}_label_{label_id}_frames.zip"

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
    print("🎯 CVAT Task-Based Frame Downloader")
    print("=" * 50)

    # Get tasks
    tasks = get_tasks()
    if not tasks:
        print("❌ No tasks found.")
        sys.exit(1)

    print(f"\n📋 Found {len(tasks)} tasks:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. Task {task['id']} - {task['name']} ({task.get('status', 'Unknown')})")

        # Get jobs for this task
        jobs = get_task_jobs(task['id'])
        print(f"     Jobs: {len(jobs)}")

        # Get labels for this task
        labels = get_task_labels(task['id'])
        if labels:
            print(f"     Labels: {', '.join([l['name'] for l in labels])}")
        else:
            print("     Labels: None")

    # Test with first task
    if tasks:
        first_task = tasks[0]
        task_id = first_task['id']

        print(f"\n🧪 Testing download with Task {task_id} ({first_task['name']})...")

        # Download all frames for this task
        success = download_task_frames(task_id)

        if success:
            print("🎉 Test download completed!")
            print("\n📁 Check the generated ZIP file:")
            print("   - Contains folders for each job (job_1/, job_2/, etc.)")
            print("   - Each folder has annotated frames")
            print("   - Includes metadata.json with task information")
            print("   - Production-grade annotation overlays")
        else:
            print("❌ Test download failed!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
