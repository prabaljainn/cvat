#!/usr/bin/env python3
"""
Performance comparison script for optimized vs original API endpoints
"""

import requests
import time
import json
from typing import Dict, List

# CVAT API configuration
BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "#@Pjain9329"
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

HEADERS = {
    'Authorization': BASIC_AUTH_HEADER
}

def get_tasks() -> List[Dict]:
    """Get all available tasks"""
    try:
        response = requests.get(f"{BASE_URL}/api/tasks", params={"page_size": 100}, headers=HEADERS)
        if response.status_code == 200:
            return response.json()['results']
        else:
            print(f"❌ Failed to get tasks: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def benchmark_endpoint(endpoint_url: str, task_id: int, label_id: int = None) -> Dict:
    """Benchmark a specific endpoint"""

    params = {'task_id': task_id}
    if label_id:
        params['label_id'] = label_id

    print(f"🚀 Testing: {endpoint_url}")
    print(f"   Parameters: {params}")

    start_time = time.time()

    try:
        response = requests.get(endpoint_url, params=params, headers=HEADERS)

        end_time = time.time()
        duration = end_time - start_time

        if response.status_code == 200:
            content_length = len(response.content)

            result = {
                'success': True,
                'duration': duration,
                'content_length': content_length,
                'throughput_mbps': (content_length / (1024 * 1024)) / duration if duration > 0 else 0,
                'status_code': response.status_code
            }

            print(f"   ✅ Success: {duration:.2f}s, {content_length:,} bytes, {result['throughput_mbps']:.2f} MB/s")

        else:
            result = {
                'success': False,
                'duration': duration,
                'status_code': response.status_code,
                'error': response.text[:200]
            }

            print(f"   ❌ Failed: {response.status_code} in {duration:.2f}s")

        return result

    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time

        result = {
            'success': False,
            'duration': duration,
            'error': str(e)
        }

        print(f"   ❌ Exception: {str(e)} in {duration:.2f}s")
        return result

def main():
    print("🏁 CVAT API Performance Comparison")
    print("=" * 60)

    # Get tasks
    tasks = get_tasks()
    if not tasks:
        print("❌ No tasks found for testing.")
        return

    # Use the first task for testing
    test_task = tasks[0]
    task_id = test_task['id']

    print(f"\n🎯 Testing with Task {task_id}: {test_task['name']}")
    print(f"   Status: {test_task.get('status', 'Unknown')}")

    # Define endpoints to test
    endpoints = {
        'Original (Production)': f"{BASE_URL}/api/custom/download-task-frames/",
        'Optimized (High-Performance)': f"{BASE_URL}/api/custom/download-task-frames-optimized/"
    }

    results = {}

    # Test each endpoint
    for name, url in endpoints.items():
        print(f"\n📊 Testing {name}")
        print("-" * 40)

        # Run the test
        result = benchmark_endpoint(url, task_id)
        results[name] = result

        # Small delay between tests
        time.sleep(2)

    # Performance comparison
    print(f"\n📈 PERFORMANCE COMPARISON")
    print("=" * 60)

    successful_results = {name: result for name, result in results.items() if result['success']}

    if len(successful_results) >= 2:
        original_result = successful_results.get('Original (Production)')
        optimized_result = successful_results.get('Optimized (High-Performance)')

        if original_result and optimized_result:
            speed_improvement = (original_result['duration'] - optimized_result['duration']) / original_result['duration'] * 100
            throughput_improvement = (optimized_result['throughput_mbps'] - original_result['throughput_mbps']) / original_result['throughput_mbps'] * 100

            print(f"⏱️  Speed Improvement: {speed_improvement:+.1f}%")
            print(f"📊 Throughput Improvement: {throughput_improvement:+.1f}%")

            if speed_improvement > 0:
                print(f"🚀 Optimized version is {speed_improvement:.1f}% FASTER!")
            else:
                print(f"⚠️  Optimized version is {abs(speed_improvement):.1f}% slower")

    # Detailed results
    print(f"\n📋 DETAILED RESULTS")
    print("-" * 60)

    for name, result in results.items():
        print(f"\n{name}:")
        if result['success']:
            print(f"  ✅ Duration: {result['duration']:.2f}s")
            print(f"  📦 Size: {result['content_length']:,} bytes")
            print(f"  🚀 Throughput: {result['throughput_mbps']:.2f} MB/s")
        else:
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")

    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 60)

    if successful_results:
        fastest = min(successful_results.items(), key=lambda x: x[1]['duration'])
        print(f"🏆 Fastest: {fastest[0]} ({fastest[1]['duration']:.2f}s)")

        if len(successful_results) > 1:
            print("\n🔧 Optimization Strategies Applied:")
            print("   • Bulk database queries with select_related/prefetch_related")
            print("   • Parallel frame processing using ThreadPoolExecutor")
            print("   • Streaming ZIP creation to reduce memory usage")
            print("   • Font caching to avoid repeated font loading")
            print("   • Optimized image processing pipeline")
            print("   • Batch processing to manage memory efficiently")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Benchmark interrupted!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
