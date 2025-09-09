# Fonts for CVAT Custom Annotation Overlay

## About

This directory contains fonts used for rendering label text on annotated frames.

## Fonts Included

- **DejaVuSans-Bold.ttf** - Bold version for high visibility labels
- **DejaVuSans.ttf** - Regular version (fallback)

## License

These fonts are from the DejaVu Fonts project and are licensed under a free license.
Source: https://github.com/dejavu-fonts/dejavu-fonts

## Cross-Platform Compatibility

The font loading system tries fonts in this order:

1. **Bundled fonts** (this directory) - Works on all platforms
2. **System fonts** - macOS and Linux specific paths
3. **Default font** - PIL's built-in fallback

## Adding Custom Fonts

To use different fonts:

1. Place TTF files in this directory
2. Update the `_get_font()` method in `views.py`
3. Ensure fonts are included when deploying

## Font Features Used

- **Size**: 24px for good visibility
- **Weight**: Bold for maximum contrast
- **Color**: Bright yellow text on black background
- **Border**: White border around background for edge definition
