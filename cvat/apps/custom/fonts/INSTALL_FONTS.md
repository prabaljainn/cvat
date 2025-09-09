# Font Installation Guide

## Quick Setup

The font loading system works with system fonts by default, but you can add custom fonts for better consistency across platforms.

## Option 1: Use System Fonts (Default)

The system automatically detects and uses fonts from:

### macOS:
- `/System/Library/Fonts/Arial Bold.ttf`
- `/System/Library/Fonts/Arial.ttf`
- `/System/Library/Fonts/Helvetica.ttc`

### Linux (Ubuntu/Debian):
- `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`
- `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`

### Linux (Arch/Manjaro):
- `/usr/share/fonts/TTF/DejaVuSans-Bold.ttf`
- `/usr/share/fonts/TTF/DejaVuSans.ttf`

## Option 2: Add Custom Fonts

To ensure consistent fonts across all platforms:

### 1. Download DejaVu Fonts

```bash
# Download from a reliable source
wget https://sourceforge.net/projects/dejavu/files/dejavu/2.37/dejavu-fonts-ttf-2.37.tar.bz2
tar -xjf dejavu-fonts-ttf-2.37.tar.bz2

# Copy fonts to the custom directory
cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf cvat/apps/custom/fonts/
cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf cvat/apps/custom/fonts/
```

### 2. Or Install System Fonts

#### Ubuntu/Debian:
```bash
sudo apt-get install fonts-dejavu-core
```

#### CentOS/RHEL:
```bash
sudo yum install dejavu-sans-fonts
```

#### Arch Linux:
```bash
sudo pacman -S ttf-dejavu
```

## Verification

The font loading system tries fonts in this order:
1. **Bundled fonts** (this directory)
2. **System fonts** (OS-specific paths)
3. **Default font** (PIL fallback)

You can verify which font is being used by checking the application logs.

## Current Status

✅ **System font fallback is working**
✅ **Cross-platform compatibility implemented**
⚠️  **Custom bundled fonts optional**

The annotation overlay will work on any system with the current implementation!
