#!/usr/bin/env python3
"""
Comprehensive test script for the CVAT Train System Extension
"""

import requests
import json

# CVAT API configuration
BASE_URL = "http://localhost:8000"
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

HEADERS = {
    'Authorization': BASIC_AUTH_HEADER,
    'Content-Type': 'application/json'
}

def test_train_system():
    """Test the complete train system functionality."""

    print("🚂 CVAT Train System Extension Test")
    print("=" * 60)

    task_id = 6

    # 1. Test Task Analysis with Train Metadata
    print(f"\n1️⃣  TASK ANALYSIS WITH TRAIN METADATA")
    print("-" * 40)

    response = requests.get(
        f"{BASE_URL}/api/custom/task-analysis/?task_id={task_id}",
        headers={'Authorization': BASIC_AUTH_HEADER}
    )

    if response.status_code == 200:
        data = response.json()
        train_meta = data['train_metadata']

        print(f"✅ Task {task_id}: {data['name']}")
        print(f"🚂 Train ID: {train_meta['train_id']}")
        print(f"⚖️  Verdict: {train_meta['verdict']} ({train_meta['verdict_display']})")
        print(f"📝 Notes: {train_meta['notes']}")
        print(f"🎯 Confidence: {train_meta['confidence_score']}")
        print(f"📅 Updated: {train_meta['updated_date']}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # 2. Test Quick Verdict Update
    print(f"\n2️⃣  QUICK VERDICT UPDATE")
    print("-" * 40)

    # Update to Rejected
    response = requests.post(
        f"{BASE_URL}/api/custom/update-verdict/",
        headers=HEADERS,
        json={"task_id": task_id, "verdict": "RJ"}
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ {data['message']}")
        print(f"🔄 {data['old_verdict']} → {data['new_verdict']}")
        print(f"📝 Display: {data['verdict_display']}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # 3. Test Full Metadata Update
    print(f"\n3️⃣  FULL METADATA UPDATE")
    print("-" * 40)

    response = requests.post(
        f"{BASE_URL}/api/custom/train-metadata/",
        headers=HEADERS,
        json={
            "task_id": task_id,
            "train_id": "TRAIN_FINAL_001",
            "verdict": "AC",
            "notes": "Final review completed - high quality annotations",
            "confidence_score": 0.98
        }
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ {data['message']}")
        print(f"📝 Updated fields: {', '.join(data['updated_fields'])}")

        meta = data['train_metadata']
        print(f"🚂 Train ID: {meta['train_id']}")
        print(f"⚖️  Verdict: {meta['verdict']} ({meta['verdict_display']})")
        print(f"📝 Notes: {meta['notes']}")
        print(f"🎯 Confidence: {meta['confidence_score']}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # 4. Test Train Metadata List
    print(f"\n4️⃣  TRAIN METADATA LIST")
    print("-" * 40)

    response = requests.get(
        f"{BASE_URL}/api/custom/train-metadata-list/",
        headers={'Authorization': BASIC_AUTH_HEADER}
    )

    if response.status_code == 200:
        data = response.json()

        print(f"📊 Total Tasks: {data['total_tasks']}")
        print(f"📈 Verdict Summary:")
        for verdict, count in data['verdict_summary'].items():
            verdict_names = {'AC': 'Accepted', 'NA': 'Not Applicable', 'RJ': 'Rejected'}
            print(f"   {verdict} ({verdict_names[verdict]}): {count}")

        print(f"\n📋 Tasks:")
        for task in data['tasks']:
            meta = task['train_metadata']
            print(f"   Task {task['task_id']}: {task['task_name']}")
            print(f"      🚂 Train: {meta['train_id']}")
            print(f"      ⚖️  Verdict: {meta['verdict']} ({meta['verdict_display']})")
            if meta['notes']:
                print(f"      📝 Notes: {meta['notes']}")
            if meta['confidence_score']:
                print(f"      🎯 Confidence: {meta['confidence_score']}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # 5. Test Filtered List (Accepted only)
    print(f"\n5️⃣  FILTERED LIST (ACCEPTED ONLY)")
    print("-" * 40)

    response = requests.get(
        f"{BASE_URL}/api/custom/train-metadata-list/?verdict=AC",
        headers={'Authorization': BASIC_AUTH_HEADER}
    )

    if response.status_code == 200:
        data = response.json()

        print(f"📊 Accepted Tasks: {data['total_tasks']}")
        for task in data['tasks']:
            meta = task['train_metadata']
            print(f"   ✅ Task {task['task_id']}: {task['task_name']} (Train: {meta['train_id']})")
    else:
        print(f"❌ Failed: {response.status_code}")

    # 6. Test Individual Train Metadata Get
    print(f"\n6️⃣  INDIVIDUAL TRAIN METADATA")
    print("-" * 40)

    response = requests.get(
        f"{BASE_URL}/api/custom/train-metadata/?task_id={task_id}",
        headers={'Authorization': BASIC_AUTH_HEADER}
    )

    if response.status_code == 200:
        data = response.json()
        meta = data['train_metadata']

        print(f"🚂 Train Metadata for Task {data['task_id']}:")
        print(f"   Train ID: {meta['train_id']}")
        print(f"   Verdict: {meta['verdict']} ({meta['verdict_display']})")
        print(f"   Notes: {meta['notes']}")
        print(f"   Confidence: {meta['confidence_score']}")
        print(f"   Created: {meta['created_date']}")
        print(f"   Updated: {meta['updated_date']}")
    else:
        print(f"❌ Failed: {response.status_code}")

    print(f"\n🎉 TRAIN SYSTEM TEST COMPLETE!")
    print("=" * 60)

    # Summary of available endpoints
    print(f"\n📚 AVAILABLE ENDPOINTS:")
    print("   GET  /api/custom/task-analysis/?task_id={id}")
    print("   GET  /api/custom/train-metadata/?task_id={id}")
    print("   POST /api/custom/train-metadata/")
    print("   POST /api/custom/update-verdict/")
    print("   GET  /api/custom/train-metadata-list/")
    print("   GET  /api/custom/train-metadata-list/?verdict=AC")
    print("   GET  /api/custom/train-metadata-list/?project_id=1")

if __name__ == "__main__":
    test_train_system()
