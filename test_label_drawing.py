#!/usr/bin/env python3
"""
Test script to verify label text drawing functionality
"""

from PIL import Image, ImageDraw, ImageFont
import io

def test_label_drawing():
    """Test if label text drawing works"""

    # Create a test image
    img = Image.new('RGB', (400, 300), color='white')
    draw = ImageDraw.Draw(img)

    # Test drawing a rectangle with label
    color = "#6e6791"  # Same color as "Torn" label
    x1, y1, x2, y2 = 50, 50, 200, 150

    # Draw rectangle
    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

    # Try to load font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
        print("✅ Arial font loaded")
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
            print("✅ Helvetica font loaded")
        except:
            font = ImageFont.load_default()
            print("⚠️  Using default font")

    # Draw label text
    label_name = "Torn"
    text_position = (x1, y1 - 20)

    # Draw text background
    text_bbox = draw.textbbox(text_position, label_name, font=font)
    draw.rectangle(text_bbox, fill=color, outline=color)

    # Draw text
    draw.text(text_position, label_name, fill="white", font=font)

    # Save test image
    img.save("test_label_drawing.png")
    print("✅ Test image saved as: test_label_drawing.png")
    print(f"   Rectangle: {x1},{y1} to {x2},{y2}")
    print(f"   Label: '{label_name}' at {text_position}")
    print(f"   Color: {color}")

if __name__ == "__main__":
    test_label_drawing()
