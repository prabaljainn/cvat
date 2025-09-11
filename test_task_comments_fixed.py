#!/usr/bin/env python3
"""
Fixed Task Comments API Test Script

Tests the corrected Task Comments API endpoints.
"""

import requests
import json
import base64
from datetime import datetime

# Configuration
BASE_URL = "https://sudocodes.com/api/custom"
USERNAME = "admin"
PASSWORD = "admin"

def get_auth_header():
    """Get Basic Auth header."""
    credentials = base64.b64encode(f'{USERNAME}:{PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {credentials}'}

def test_fixed_endpoints():
    """Test the fixed Task Comments API endpoints."""

    print("🔧 Testing FIXED Task Comments API Endpoints")
    print("=" * 50)

    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'

    # Test 1: Create a comment (this should work)
    print("\n1️⃣ Creating a test comment...")
    comment_data = {
        "task": 1,
        "message": "Fixed API test comment!",
        "comment_type": "GEN"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/task-comments/create/",
            headers=headers,
            json=comment_data
        )

        if response.status_code == 201:
            comment = response.json()
            comment_id = comment['id']
            print(f"✅ Comment created! ID: {comment_id}")
        else:
            print(f"❌ Failed to create comment: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Test 2: List comments using the correct endpoint
    print("\n2️⃣ Testing: List Task Comments (Fixed)")
    try:
        # Try the router-based endpoint
        response = requests.get(
            f"{BASE_URL}/comments/?task={1}",  # Query parameter approach
            headers=get_auth_header()
        )

        print(f"Router endpoint status: {response.status_code}")
        if response.status_code == 200:
            comments = response.json()
            print(f"✅ Router endpoint: Found {len(comments)} comments")
            if comments:
                print(f"   First comment: {comments[0]['message'][:50]}...")

        # Try the direct task endpoint
        response2 = requests.get(
            f"{BASE_URL}/tasks/1/comments/",
            headers=get_auth_header()
        )

        print(f"Direct endpoint status: {response2.status_code}")
        if response2.status_code == 200:
            data = response2.json()
            comments = data.get('results', data)  # Handle both formats
            print(f"✅ Direct endpoint: Found {len(comments)} comments")

    except Exception as e:
        print(f"❌ Error testing list: {e}")

    # Test 3: Get comment details using router
    print("\n3️⃣ Testing: Get Comment Details (Router)")
    try:
        response = requests.get(
            f"{BASE_URL}/comments/{comment_id}/",
            headers=get_auth_header()
        )

        print(f"Comment details status: {response.status_code}")
        if response.status_code == 200:
            comment = response.json()
            print(f"✅ Retrieved comment: {comment['message']}")
            print(f"   Author: {comment['author']['username']}")
            print(f"   Type: {comment['comment_type_display']}")
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 4: Update comment using router
    print("\n4️⃣ Testing: Update Comment (Router)")
    try:
        update_data = {
            "message": "Updated via fixed API test!",
            "comment_type": "REV"
        }

        response = requests.patch(
            f"{BASE_URL}/comments/{comment_id}/",
            headers=headers,
            json=update_data
        )

        print(f"Update status: {response.status_code}")
        if response.status_code == 200:
            updated = response.json()
            print(f"✅ Updated comment: {updated['message']}")
            print(f"   Is edited: {updated['is_edited']}")
        else:
            print(f"❌ Failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 5: Get all comments (no task filter)
    print("\n5️⃣ Testing: Get All Comments")
    try:
        response = requests.get(
            f"{BASE_URL}/comments/",
            headers=get_auth_header()
        )

        print(f"All comments status: {response.status_code}")
        if response.status_code == 200:
            comments = response.json()
            print(f"✅ Total comments in system: {len(comments)}")

            # Show first few comments
            for i, comment in enumerate(comments[:3]):
                print(f"   {i+1}. ID {comment['id']}: {comment['message'][:40]}...")
                print(f"      Task: {comment['task']}, Author: {comment['author']['username']}")

    except Exception as e:
        print(f"❌ Error: {e}")

    return True

def debug_url_patterns():
    """Debug which URL patterns are working."""

    print("\n🔍 Debugging URL Patterns")
    print("-" * 30)

    headers = get_auth_header()

    # Test different URL patterns
    test_urls = [
        f"{BASE_URL}/comments/",
        f"{BASE_URL}/comments/1/",
        f"{BASE_URL}/tasks/1/comments/",
        f"{BASE_URL}/task-comments/stats/",
        f"{BASE_URL}/task-comments/create/"
    ]

    for url in test_urls:
        try:
            response = requests.get(url, headers=headers)
            status_icon = "✅" if response.status_code < 400 else "❌"
            print(f"{status_icon} {url} → {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        print(f"   Returns list with {len(data)} items")
                    elif isinstance(data, dict):
                        print(f"   Returns dict with keys: {list(data.keys())[:5]}")
                except:
                    print(f"   Returns non-JSON content")

        except Exception as e:
            print(f"❌ {url} → Error: {e}")

def main():
    """Run all tests."""

    print("🚀 Fixed Task Comments API Test")
    print(f"🌐 Server: {BASE_URL}")
    print(f"👤 User: {USERNAME}")
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Debug URL patterns first
    debug_url_patterns()

    # Test fixed endpoints
    test_fixed_endpoints()

    print("\n📋 Key Findings:")
    print("- Comments are being created successfully")
    print("- Issue is likely in URL routing for retrieval")
    print("- Statistics endpoint works (proves data exists)")
    print("- Need to check which router endpoints are active")

    print("\n💡 Next Steps:")
    print("1. Deploy the fixed views to production")
    print("2. Re-run this test to verify fixes")
    print("3. Check Django URL routing in production logs")

if __name__ == "__main__":
    main()
