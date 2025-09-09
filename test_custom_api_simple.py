#!/usr/bin/env python3
"""
Simple test for the custom API - requires manual authentication
"""

import requests
import sys

def test_custom_api():
    """Test the custom API endpoint"""

    print("🧪 Testing Custom API")
    print("📝 Note: You need to be logged in to CVAT in your browser first")
    print("🌐 Go to http://localhost:3000 and login, then run this script")

    # Test with the task we know exists (ID: 5, Job ID: 1)
    job_id = 1

    print(f"\n🔍 Testing with Job ID: {job_id}")

    # Make request (will work if user is logged in via browser)
    response = requests.get(
        f"http://localhost:8000/api/custom/download-annotated-frames/",
        params={"job_id": job_id}
    )

    print(f"Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")

    if response.status_code == 200:
        if 'application/zip' in response.headers.get('Content-Type', ''):
            print(f"✅ Success! ZIP file received ({len(response.content)} bytes)")
            filename = f"job_{job_id}_annotated_frames.zip"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"📁 Saved as: {filename}")
        else:
            print(f"✅ Success! Response: {response.text}")
    elif response.status_code == 401:
        print("❌ Authentication required. Please login to CVAT first:")
        print("   1. Go to http://localhost:3000")
        print("   2. Login with admin/admin123456")
        print("   3. Run this script again")
    else:
        print(f"❌ Error: {response.text}")

if __name__ == "__main__":
    test_custom_api()
