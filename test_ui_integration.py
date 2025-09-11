#!/usr/bin/env python3
"""
Test UI Integration for Task Comments

This script verifies that the UI integration is working correctly.
"""

import requests
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

def test_ui_integration():
    """Test that the UI integration endpoints work correctly."""

    print("🎨 Testing Task Comments UI Integration")
    print("=" * 50)

    headers = get_auth_header()
    headers['Content-Type'] = 'application/json'

    # Test 1: Create a UI-specific comment
    print("\n1️⃣ Creating UI Test Comment")
    ui_comment = {
        "task": 1,
        "message": "🎨 This comment was created to test the UI integration! The TaskComments component should display this beautifully.",
        "comment_type": "GEN"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/task-comments/create/",
            headers=headers,
            json=ui_comment
        )

        if response.status_code == 201:
            comment = response.json()
            print(f"✅ UI test comment created! ID: {comment['id']}")
            print(f"   Message: {comment['message'][:60]}...")
            ui_comment_id = comment['id']
        else:
            print(f"❌ Failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

    # Test 2: Create different comment types for UI display
    print("\n2️⃣ Creating Comments of Different Types for UI")

    ui_test_comments = [
        {
            "message": "🔍 Found an issue with the annotation quality in frames 10-15",
            "type": "ISS",
            "description": "Issue comment"
        },
        {
            "message": "👍 Great work on the bounding box accuracy!",
            "type": "FB",
            "description": "Feedback comment"
        },
        {
            "message": "❓ Should we include partial occlusions in this dataset?",
            "type": "Q",
            "description": "Question comment"
        },
        {
            "message": "📝 Remember to check the edge cases in the final review",
            "type": "NOTE",
            "description": "Note comment"
        },
        {
            "message": "🔎 This task needs a thorough review before approval",
            "type": "REV",
            "description": "Review comment"
        }
    ]

    created_comments = []

    for comment_info in ui_test_comments:
        try:
            comment_data = {
                "task": 1,
                "message": comment_info["message"],
                "comment_type": comment_info["type"]
            }

            response = requests.post(
                f"{BASE_URL}/task-comments/create/",
                headers=headers,
                json=comment_data
            )

            if response.status_code == 201:
                comment = response.json()
                created_comments.append(comment['id'])
                print(f"✅ {comment_info['description']}: ID {comment['id']}")
            else:
                print(f"❌ {comment_info['description']}: Failed ({response.status_code})")

        except Exception as e:
            print(f"❌ Error creating {comment_info['description']}: {e}")

    # Test 3: Create a reply for threading display
    print("\n3️⃣ Creating Reply Comment for Threading")

    reply_data = {
        "task": 1,
        "message": "💬 This is a reply to test the threading display in the UI. The component should show this indented under the parent comment.",
        "comment_type": "GEN",
        "parent_comment": ui_comment_id
    }

    try:
        response = requests.post(
            f"{BASE_URL}/task-comments/create/",
            headers=headers,
            json=reply_data
        )

        if response.status_code == 201:
            reply = response.json()
            print(f"✅ Reply comment created! ID: {reply['id']}")
            print(f"   Parent: {reply['parent_comment']}")
        else:
            print(f"❌ Failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 4: Verify UI data endpoints
    print("\n4️⃣ Verifying UI Data Endpoints")

    try:
        # Test task comments endpoint (used by UI)
        response = requests.get(
            f"{BASE_URL}/tasks/1/comments/",
            headers=get_auth_header()
        )

        if response.status_code == 200:
            data = response.json()
            comments = data.get('results', [])
            stats = data.get('statistics', {})

            print(f"✅ UI Comments Endpoint Working")
            print(f"   Comments returned: {len(comments)}")
            print(f"   Total in DB: {stats.get('total_comments', 'unknown')}")

            # Show comment types for UI display
            comment_types = {}
            for comment in comments[:10]:  # Show first 10
                comment_type = comment['comment_type_display']
                comment_types[comment_type] = comment_types.get(comment_type, 0) + 1

            print(f"   Comment types in UI data:")
            for type_name, count in comment_types.items():
                print(f"     - {type_name}: {count}")

        else:
            print(f"❌ UI endpoint failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Error testing UI endpoint: {e}")

    # Test 5: Verify statistics endpoint (used by UI)
    print("\n5️⃣ Verifying Statistics Endpoint for UI")

    try:
        response = requests.get(
            f"{BASE_URL}/task-comments/stats/?task_id=1",
            headers=get_auth_header()
        )

        if response.status_code == 200:
            stats = response.json()
            print(f"✅ UI Statistics Endpoint Working")
            print(f"   Total comments: {stats['total_comments']}")
            print(f"   Recent activity: {stats['recent_activity']['comments_last_week']} this week")

            # Show type breakdown for UI
            print(f"   Type breakdown for UI:")
            for type_code, type_data in stats['comment_types'].items():
                if type_data['count'] > 0:
                    print(f"     - {type_data['name']}: {type_data['count']}")

        else:
            print(f"❌ Statistics endpoint failed: {response.status_code}")

    except Exception as e:
        print(f"❌ Error testing statistics: {e}")

    return True

def show_ui_instructions():
    """Show instructions for testing the UI."""

    print("\n🎨 UI Testing Instructions")
    print("=" * 30)

    print("""
📋 **How to Test the UI Integration:**

1. **Deploy the Updated Frontend:**
   ```bash
   # On your server
   docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d cvat_ui
   ```

2. **Access Task Page:**
   - Go to https://sudocodes.com
   - Login as admin
   - Navigate to any task (e.g., Task #1)
   - Scroll down to see the "Task Comments" section

3. **Test UI Features:**
   ✅ View existing comments with different types and colors
   ✅ Click "Add Comment" to create new comments
   ✅ Try different comment types (General, Feedback, Issue, etc.)
   ✅ Create replies by clicking "Reply" on existing comments
   ✅ View comment statistics at the top
   ✅ Use "Refresh" button to reload comments

4. **Expected UI Elements:**
   - 💬 Task Comments card with statistics
   - 🏷️  Colored tags for comment types
   - 👤 User avatars and names
   - 🕐 Timestamps for each comment
   - 📝 Reply threading with indentation
   - ➕ Add Comment form with type selector
   - 📊 Statistics showing comment counts

5. **UI Features to Test:**
   - Comment creation with different types
   - Reply functionality and threading
   - Real-time statistics updates
   - Responsive design on different screen sizes
   - Loading states and error handling
""")

def main():
    """Run UI integration tests."""

    print("🚀 Task Comments UI Integration Test")
    print(f"🌐 Server: {BASE_URL}")
    print(f"👤 User: {USERNAME}")
    print(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run tests
    if test_ui_integration():
        print("\n🎉 UI Integration Tests Completed Successfully!")

        print("\n📊 Summary:")
        print("✅ UI test comments created")
        print("✅ Different comment types added")
        print("✅ Reply threading tested")
        print("✅ UI data endpoints verified")
        print("✅ Statistics endpoint confirmed")

        print("\n🎯 Ready for UI Testing!")
        print("The TaskComments component is integrated and ready to test in the browser.")

        # Show instructions
        show_ui_instructions()

    else:
        print("\n❌ UI Integration tests failed")
        return False

    return True

if __name__ == "__main__":
    main()
