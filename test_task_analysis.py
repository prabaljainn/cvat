#!/usr/bin/env python3
"""
Test script for the Task Analysis API
"""

import requests
import json

# CVAT API configuration
BASE_URL = "http://localhost:8000"
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

HEADERS = {
    'Authorization': BASIC_AUTH_HEADER
}

def test_task_analysis():
    """Test the comprehensive task analysis API."""

    print("🔍 CVAT Task Analysis API Test")
    print("=" * 50)

    task_id = 6

    # Test the API
    response = requests.get(
        f"{BASE_URL}/api/custom/task-analysis/?task_id={task_id}",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()

        print(f"✅ Task Analysis for Task {task_id}: {data['name']}")
        print(f"📊 Project: {data['project_name']}")
        print(f"👤 Owner: {data['owner']['username']}")
        print(f"📈 Status: {data['status']}")

        print(f"\n📋 BASIC INFO:")
        print(f"   Total Frames: {data['data']['size']}")
        print(f"   Frame Range: {data['data']['start_frame']}-{data['data']['stop_frame']}")
        print(f"   Jobs: {len(data['jobs'])}")
        print(f"   Labels: {len(data['labels'])}")

        print(f"\n🎯 ANNOTATION ANALYSIS:")
        print(f"   Total Annotated Frames: {data['annotation_analysis']['total_annotated_frames']}")
        print(f"   Annotation Density: {data['statistics']['summary']['annotation_density_percentage']}%")
        print(f"   Most Used Label: {data['statistics']['summary']['most_used_label']}")

        print(f"\n🏷️  LABELS BREAKDOWN:")
        for label_name, label_data in data['annotation_analysis']['labels_analysis'].items():
            frames = label_data['annotated_frames']
            frame_count = label_data['frame_count']

            if frame_count > 0:
                print(f"   📌 {label_name} (ID: {label_data['label_id']}):")
                print(f"      Frames: {frames}")
                print(f"      Count: {frame_count}")
                print(f"      Annotations: {label_data['annotation_counts']['total']} total")
                print(f"        - Shapes: {label_data['annotation_counts']['shapes']}")
                print(f"        - Tracks: {label_data['annotation_counts']['tracks']}")
                print(f"        - Tags: {label_data['annotation_counts']['tags']}")
            else:
                print(f"   📌 {label_name} (ID: {label_data['label_id']}): No annotations")

        print(f"\n📊 STATISTICS:")
        for label_name, stats in data['statistics']['label_statistics'].items():
            if stats['frame_count'] > 0:
                print(f"   {label_name}: {stats['frame_count']} frames ({stats['percentage_of_annotated_frames']:.1f}% of annotated)")

        print(f"\n🎯 EXAMPLE OUTPUT (as requested):")
        print("   label_id: [array of frames]")
        for label_name, label_data in data['annotation_analysis']['labels_analysis'].items():
            if label_data['frame_count'] > 0:
                print(f"   {label_name}/labelId_{label_data['label_id']}: {label_data['annotated_frames']}")

    else:
        print(f"❌ Failed: HTTP {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_task_analysis()
