#!/usr/bin/env python3
"""
Test IAM Fix for Task Comments

This script tests that the IAM organization field fix resolves the schema error.
"""

import requests
import base64

# Configuration
BASE_URL = "https://sudocodes.com"
USERNAME = "admin"
PASSWORD = "admin"

def get_auth_header():
    """Get Basic Auth header."""
    credentials = base64.b64encode(f'{USERNAME}:{PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {credentials}'}

def test_schema_endpoint():
    """Test that the schema endpoint works without errors."""
    
    print("🔧 Testing IAM Fix for Task Comments")
    print("=" * 40)
    
    print("\n1️⃣ Testing API Schema Endpoint")
    
    try:
        # Test the schema endpoint that was failing
        response = requests.get(
            f"{BASE_URL}/api/schema/?scheme=json&org=",
            headers=get_auth_header(),
            timeout=30
        )
        
        print(f"Schema endpoint status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Schema endpoint working - IAM fix successful!")
            
            # Check if our custom endpoints are in the schema
            try:
                schema_data = response.json()
                paths = schema_data.get('paths', {})
                
                custom_endpoints = [path for path in paths.keys() if '/api/custom/' in path]
                print(f"✅ Found {len(custom_endpoints)} custom endpoints in schema")
                
                # Look for task comments endpoints
                comment_endpoints = [path for path in custom_endpoints if 'comment' in path.lower()]
                if comment_endpoints:
                    print(f"✅ Task Comments endpoints found in schema:")
                    for endpoint in comment_endpoints[:5]:  # Show first 5
                        print(f"   - {endpoint}")
                else:
                    print("⚠️  No comment endpoints found in schema")
                    
            except Exception as e:
                print(f"⚠️  Could not parse schema JSON: {e}")
                
        elif response.status_code == 500:
            print("❌ Schema endpoint still returning 500 - IAM fix may need more work")
            print(f"Response: {response.text[:200]}...")
            return False
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing schema endpoint: {e}")
        return False
    
    return True

def test_task_comments_still_working():
    """Verify task comments API still works after IAM fix."""
    
    print("\n2️⃣ Testing Task Comments API Still Works")
    
    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'
    
    # Test comment creation
    try:
        comment_data = {
            "task": 1,
            "message": "🔧 Testing after IAM fix - this comment verifies the API still works!",
            "comment_type": "GEN"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/custom/task-comments/create/",
            headers=headers,
            json=comment_data,
            timeout=10
        )
        
        if response.status_code == 201:
            comment = response.json()
            print(f"✅ Comment creation still works! ID: {comment['id']}")
        else:
            print(f"❌ Comment creation failed: {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Error testing comment creation: {e}")
        return False
    
    # Test comment listing
    try:
        response = requests.get(
            f"{BASE_URL}/api/custom/tasks/1/comments/",
            headers=get_auth_header(),
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            comments = data.get('results', [])
            print(f"✅ Comment listing still works! Found {len(comments)} comments")
        else:
            print(f"❌ Comment listing failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing comment listing: {e}")
        return False
    
    return True

def main():
    """Run IAM fix tests."""
    
    print("🚀 Task Comments IAM Fix Test")
    print(f"🌐 Server: {BASE_URL}")
    print(f"👤 User: {USERNAME}")
    
    success = True
    
    # Test schema endpoint
    if not test_schema_endpoint():
        success = False
    
    # Test task comments still work
    if not test_task_comments_still_working():
        success = False
    
    if success:
        print("\n🎉 IAM Fix Successful!")
        print("✅ Schema endpoint working")
        print("✅ Task Comments API still functional")
        print("✅ No more 500 errors expected")
        
        print("\n📋 Summary:")
        print("- Added iam_organization_field to all TaskComment views")
        print("- Added proper CVAT filter and search fields")
        print("- Schema generation should work without errors")
        print("- Task Comments functionality preserved")
        
    else:
        print("\n❌ IAM Fix needs more work")
        print("Please check the server logs for additional errors")
    
    return success

if __name__ == "__main__":
    main()
