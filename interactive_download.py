#!/usr/bin/env python3
"""
Interactive script to download annotated frames from CVAT
Prompts user to select job and label, then downloads ZIP file
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

class CVATDownloader:
    def __init__(self):
        self.session = requests.Session()
        # Set Basic Auth header for all requests
        self.session.headers.update({
            'Authorization': BASIC_AUTH_HEADER
        })
        self.authenticated = False

    def authenticate(self) -> bool:
        """Test Basic Auth by making a simple API call"""
        try:
            print("🔐 Testing Basic Authentication...")
            response = self.session.get(f"{BASE_URL}/api/jobs", params={"page_size": 1})

            if response.status_code == 200:
                self.authenticated = True
                print("✅ Basic Auth successful!")
                return True
            elif response.status_code == 401:
                print("❌ Authentication failed!")
                print(f"Please check credentials: {USERNAME} / {PASSWORD}")
                print("Make sure the Basic Auth header is correct")
                return False
            else:
                print(f"❌ Unexpected response: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection error: {e}")
            print("Make sure CVAT backend is running at http://localhost:8000")
            return False

    def get_jobs(self) -> List[Dict]:
        """Get all available jobs"""
        try:
            response = self.session.get(f"{BASE_URL}/api/jobs", params={"page_size": 100})
            if response.status_code == 200:
                jobs = response.json()['results']
                return jobs
            else:
                print(f"❌ Failed to get jobs: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting jobs: {e}")
            return []

    def get_task_labels(self, task_id: int) -> List[Dict]:
        """Get labels for a specific task"""
        try:
            response = self.session.get(f"{BASE_URL}/api/labels", params={
                "task_id": task_id,
                "page_size": 100
            })
            if response.status_code == 200:
                labels = response.json()['results']
                return labels
            else:
                print(f"❌ Failed to get labels: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error getting labels: {e}")
            return []

    def display_jobs(self, jobs: List[Dict]) -> None:
        """Display available jobs in a formatted table"""
        if not jobs:
            print("❌ No jobs found!")
            return

        print("\n📋 Available Jobs:")
        print("=" * 80)
        print(f"{'ID':<4} {'Task':<20} {'Status':<12} {'Assignee':<15} {'Stage':<10}")
        print("-" * 80)

        for job in jobs:
            task_name = job.get('task', {}).get('name', 'Unknown')[:19]
            status = job.get('status', 'Unknown')
            assignee = job.get('assignee', {})
            assignee_name = assignee.get('username', 'Unassigned') if assignee else 'Unassigned'
            stage = job.get('stage', 'Unknown')

            print(f"{job['id']:<4} {task_name:<20} {status:<12} {assignee_name:<15} {stage:<10}")

        print("=" * 80)

    def display_labels(self, labels: List[Dict]) -> None:
        """Display available labels in a formatted table"""
        if not labels:
            print("❌ No labels found for this task!")
            return

        print("\n🏷️  Available Labels:")
        print("=" * 60)
        print(f"{'ID':<4} {'Name':<25} {'Type':<15} {'Color':<10}")
        print("-" * 60)

        for label in labels:
            name = label.get('name', 'Unknown')[:24]
            label_type = label.get('type', 'Unknown')
            color = label.get('color', 'N/A')

            print(f"{label['id']:<4} {name:<25} {label_type:<15} {color:<10}")

        print("-" * 60)
        print("0    [All Labels]       -               -")
        print("=" * 60)

    def select_job(self, jobs: List[Dict]) -> Optional[Dict]:
        """Prompt user to select a job"""
        while True:
            try:
                choice = input(f"\n🎯 Select a job (1-{len(jobs)}) or 'q' to quit: ").strip()

                if choice.lower() == 'q':
                    return None

                job_index = int(choice) - 1
                if 0 <= job_index < len(jobs):
                    selected_job = jobs[job_index]
                    print(f"✅ Selected Job {selected_job['id']}: {selected_job.get('task', {}).get('name', 'Unknown')}")
                    return selected_job
                else:
                    print(f"❌ Please enter a number between 1 and {len(jobs)}")

            except ValueError:
                print("❌ Please enter a valid number or 'q' to quit")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                return None

    def select_label(self, labels: List[Dict]) -> Optional[int]:
        """Prompt user to select a label"""
        while True:
            try:
                choice = input(f"\n🏷️  Select a label (0 for all, 1-{len(labels)} for specific) or 'q' to quit: ").strip()

                if choice.lower() == 'q':
                    return None

                if choice == '0':
                    print("✅ Selected: All Labels")
                    return 0  # Special value for all labels

                label_index = int(choice) - 1
                if 0 <= label_index < len(labels):
                    selected_label = labels[label_index]
                    print(f"✅ Selected Label {selected_label['id']}: {selected_label['name']}")
                    return selected_label['id']
                else:
                    print(f"❌ Please enter a number between 0 and {len(labels)}")

            except ValueError:
                print("❌ Please enter a valid number or 'q' to quit")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                return None

    def download_annotated_frames(self, job_id: int, label_id: Optional[int] = None) -> bool:
        """Download annotated frames for the selected job and label"""
        print(f"\n📥 Downloading annotated frames...")
        print(f"   Job ID: {job_id}")
        print(f"   Label ID: {label_id if label_id else 'All Labels'}")

        # Prepare parameters
        params = {'job_id': job_id}
        if label_id and label_id != 0:  # 0 means all labels
            params['label_id'] = label_id

        try:
            response = self.session.get(
                f"{BASE_URL}/api/custom/download-annotated-frames/",
                params=params,
                stream=True  # For large files
            )

            print(f"📡 Response Status: {response.status_code}")

            if response.status_code == 200:
                # Check if it's a ZIP file
                content_type = response.headers.get('Content-Type', '')
                if 'application/zip' in content_type:
                    # Generate filename
                    if label_id and label_id != 0:
                        filename = f"job_{job_id}_label_{label_id}_frames.zip"
                    else:
                        filename = f"job_{job_id}_all_labels_frames.zip"

                    # Save the file
                    with open(filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    file_size = len(open(filename, 'rb').read())
                    print(f"✅ Success! Downloaded {file_size:,} bytes")
                    print(f"📁 Saved as: {filename}")
                    return True
                else:
                    # Not a ZIP file, probably JSON response
                    try:
                        result = response.json()
                        if 'message' in result:
                            print(f"ℹ️  {result['message']}")
                        else:
                            print(f"📄 Response: {result}")
                    except:
                        print(f"📄 Response: {response.text}")
                    return True

            elif response.status_code == 400:
                try:
                    error = response.json()
                    print(f"❌ Bad Request: {error.get('error', response.text)}")
                except:
                    print(f"❌ Bad Request: {response.text}")
                return False

            elif response.status_code == 404:
                print("❌ Job or label not found")
                return False

            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def run(self):
        """Main interactive loop"""
        print("🎯 CVAT Annotated Frames Downloader")
        print("=" * 50)

        # Check authentication
        if not self.authenticate():
            sys.exit(1)

        # Get jobs
        print("\n🔍 Fetching jobs...")
        jobs = self.get_jobs()
        if not jobs:
            print("❌ No jobs found. Please create a task with jobs first.")
            sys.exit(1)

        # Display and select job
        self.display_jobs(jobs)
        selected_job = self.select_job(jobs)
        if not selected_job:
            print("👋 Goodbye!")
            sys.exit(0)

        # Get labels for the selected job's task
        task_id = selected_job.get('task', {}).get('id')
        if not task_id:
            print("❌ Could not get task ID for selected job")
            sys.exit(1)

        print(f"\n🔍 Fetching labels for task {task_id}...")
        labels = self.get_task_labels(task_id)

        # Display and select label
        self.display_labels(labels)
        selected_label_id = self.select_label(labels)
        if selected_label_id is None:
            print("👋 Goodbye!")
            sys.exit(0)

        # Download annotated frames
        success = self.download_annotated_frames(
            selected_job['id'],
            selected_label_id if selected_label_id != 0 else None
        )

        if success:
            print("\n🎉 Download completed successfully!")
        else:
            print("\n❌ Download failed!")
            sys.exit(1)

def main():
    try:
        downloader = CVATDownloader()
        downloader.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
