#!/usr/bin/env python3
"""
Test cross-platform font loading
"""

import os
import sys
sys.path.append('cvat/apps/custom')

from PIL import Image, ImageDraw, ImageFont

def get_font(size=24, bold=True):
    """Test the cross-platform font loading logic"""

    # Get the directory of this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(current_dir, 'cvat/apps/custom/fonts')

    print(f"Looking for fonts in: {fonts_dir}")

    # Try to load our bundled fonts first
    if bold:
        font_path = os.path.join(fonts_dir, 'DejaVuSans-Bold.ttf')
    else:
        font_path = os.path.join(fonts_dir, 'DejaVuSans.ttf')

    print(f"Trying bundled font: {font_path}")
    try:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, size)
            print(f"✅ Successfully loaded bundled font: {font_path}")
            return font
    except Exception as e:
        print(f"❌ Failed to load bundled font: {e}")

    # Fallback to system fonts (macOS/Linux)
    system_fonts = [
        "/System/Library/Fonts/Arial Bold.ttf",  # macOS
        "/System/Library/Fonts/Arial.ttf",       # macOS
        "/System/Library/Fonts/Helvetica.ttc",   # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",              # Arch Linux
        "/usr/share/fonts/TTF/DejaVuSans.ttf",                   # Arch Linux
    ]

    print("Trying system fonts...")
    for font_path in system_fonts:
        try:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, size)
                print(f"✅ Successfully loaded system font: {font_path}")
                return font
        except Exception as e:
            print(f"❌ Failed to load {font_path}: {e}")

    # Final fallback to default font
    print("⚠️  Using default font fallback")
    return ImageFont.load_default()

def test_font_rendering():
    """Test font rendering with the loaded font"""

    font = get_font(size=24, bold=True)

    # Create test image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Test text
    text = "Torn"
    position = (50, 50)

    # Draw with new styling
    padding = 8
    text_bbox = draw.textbbox(position, text, font=font)
    padded_bbox = (
        text_bbox[0] - padding,
        text_bbox[1] - padding,
        text_bbox[2] + padding,
        text_bbox[3] + padding
    )

    # Draw black background with white border
    draw.rectangle(padded_bbox, fill="black", outline="white", width=2)

    # Draw bright yellow text
    draw.text(position, text, fill="yellow", font=font)

    # Save test image
    img.save("test_cross_platform_fonts.png")
    print("✅ Test image saved as: test_cross_platform_fonts.png")

if __name__ == "__main__":
    print("🧪 Testing Cross-Platform Font Loading")
    print("=" * 50)
    test_font_rendering()
