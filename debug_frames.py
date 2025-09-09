#!/usr/bin/env python3
"""
Debug script to compare frame detection between original and optimized versions
"""

import requests
import json

# CVAT API configuration
BASE_URL = "http://localhost:8000"
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

HEADERS = {
    'Authorization': BASIC_AUTH_HEADER
}

def debug_annotations(task_id=6):
    """Debug what annotations exist for task 6"""

    print(f"🔍 Debugging Task {task_id} annotations...")

    # Get task info
    response = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=HEADERS)
    if response.status_code == 200:
        task = response.json()
        print(f"📋 Task: {task['name']} (Status: {task['status']})")

    # Get jobs for this task
    response = requests.get(f"{BASE_URL}/api/jobs", params={"task_id": task_id}, headers=HEADERS)
    if response.status_code == 200:
        jobs = response.json()['results']
        print(f"🔧 Jobs: {len(jobs)}")

        for job in jobs:
            job_id = job['id']
            print(f"\n  Job {job_id}:")
            print(f"    Start frame: {job['start_frame']}")
            print(f"    Stop frame: {job['stop_frame']}")

            # Get annotations for this job
            response = requests.get(f"{BASE_URL}/api/jobs/{job_id}/annotations", headers=HEADERS)
            if response.status_code == 200:
                annotations = response.json()

                print(f"    Shapes: {len(annotations.get('shapes', []))}")
                print(f"    Tracks: {len(annotations.get('tracks', []))}")
                print(f"    Tags: {len(annotations.get('tags', []))}")

                # Show frame numbers for shapes
                shape_frames = set()
                for shape in annotations.get('shapes', []):
                    shape_frames.add(shape['frame'])

                # Show frame numbers for tracks
                track_frames = set()
                for track in annotations.get('tracks', []):
                    for shape in track.get('shapes', []):
                        track_frames.add(shape['frame'])

                # Show frame numbers for tags
                tag_frames = set()
                for tag in annotations.get('tags', []):
                    tag_frames.add(tag['frame'])

                all_frames = shape_frames | track_frames | tag_frames

                print(f"    Shape frames: {sorted(shape_frames)}")
                print(f"    Track frames: {sorted(track_frames)}")
                print(f"    Tag frames: {sorted(tag_frames)}")
                print(f"    ALL annotated frames: {sorted(all_frames)}")

            else:
                print(f"    ❌ Failed to get annotations: {response.status_code}")

if __name__ == "__main__":
    debug_annotations()
