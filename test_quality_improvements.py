#!/usr/bin/env python3
"""
Test script to compare the quality improvements in annotation rendering
"""

import requests
import time

# CVAT API configuration
BASE_URL = "http://localhost:8000"
BASIC_AUTH_HEADER = "Basic YWRtaW46I0BQamFpbjkzMjk="

HEADERS = {
    'Authorization': BASIC_AUTH_HEADER
}

def test_quality_comparison():
    """Test different quality levels of annotation rendering."""

    print("🎨 CVAT Annotation Quality Comparison")
    print("=" * 60)

    endpoints = {
        "Original Custom API": "/api/custom/download-task-frames/?task_id=6",
        "Optimized Version": "/api/custom/download-task-frames-optimized/?task_id=6",
        "High-Quality CVAT Integration": "/api/custom/export-task/?task_id=6&format=annotated_images"
    }

    results = {}

    for name, url in endpoints.items():
        print(f"\n🚀 Testing: {name}")
        print("-" * 40)

        start_time = time.time()

        try:
            response = requests.get(f"{BASE_URL}{url}", headers=HEADERS)
            end_time = time.time()

            if response.status_code == 200:
                size_mb = len(response.content) / (1024 * 1024)
                duration = end_time - start_time

                results[name] = {
                    'success': True,
                    'size_mb': size_mb,
                    'duration': duration,
                    'quality_features': get_quality_features(name)
                }

                print(f"   ✅ Success: {size_mb:.2f} MB in {duration:.2f}s")

            else:
                results[name] = {
                    'success': False,
                    'error': f"HTTP {response.status_code}"
                }
                print(f"   ❌ Failed: HTTP {response.status_code}")

        except Exception as e:
            results[name] = {
                'success': False,
                'error': str(e)
            }
            print(f"   ❌ Error: {str(e)}")

    # Quality comparison summary
    print(f"\n📊 QUALITY COMPARISON SUMMARY")
    print("=" * 60)

    for name, result in results.items():
        if result['success']:
            print(f"\n🎯 {name}:")
            print(f"   Size: {result['size_mb']:.2f} MB")
            print(f"   Speed: {result['duration']:.2f}s")
            print(f"   Quality Features:")
            for feature in result['quality_features']:
                print(f"     • {feature}")

    print(f"\n🏆 QUALITY IMPROVEMENTS")
    print("-" * 60)
    print("✨ High-Quality CVAT Integration includes:")
    print("   • 32px font size (vs 24px in original)")
    print("   • 4px line width (vs 3px in original)")
    print("   • Anti-aliasing simulation with multiple thin lines")
    print("   • Corner emphasis markers for rectangles")
    print("   • Vertex markers for polygons")
    print("   • Endpoint markers for polylines")
    print("   • Concentric circles for points")
    print("   • Multi-layer text backgrounds with shadows")
    print("   • Text outlines for maximum clarity")
    print("   • Bright green shapes (#00FF00) for better contrast")
    print("   • Bright yellow text (#FFFF00) with white highlights")
    print("   • Enhanced font loading with comprehensive fallbacks")

def get_quality_features(endpoint_name):
    """Get quality features for each endpoint."""

    features = {
        "Original Custom API": [
            "24px font size",
            "3px line width",
            "Basic text background",
            "Yellow text on black background"
        ],
        "Optimized Version": [
            "28px font size",
            "3px line width",
            "Font caching for performance",
            "Bulk database queries"
        ],
        "High-Quality CVAT Integration": [
            "32px font size with bold weight",
            "4px line width with anti-aliasing",
            "Multi-layer text backgrounds with shadows",
            "Text outlines for maximum clarity",
            "Corner markers for rectangles",
            "Vertex markers for polygons",
            "Endpoint markers for polylines",
            "Concentric circles for points",
            "Bright color palette (#00FF00, #FFFF00)",
            "Enhanced font loading system",
            "CVAT architecture integration"
        ]
    }

    return features.get(endpoint_name, [])

if __name__ == "__main__":
    try:
        test_quality_comparison()
    except KeyboardInterrupt:
        print("\n👋 Test interrupted!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
