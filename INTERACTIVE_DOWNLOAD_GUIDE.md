# 🎯 Interactive Annotated Frames Downloader

## 📖 Overview

This interactive script allows you to easily download annotated frames from CVAT by guiding you through the selection process step by step.

## 🚀 How to Use

### 1. Prerequisites

Make sure your CVAT development environment is running:

```bash
# Terminal 1 - Backend + Workers
./start_dev.sh

# Terminal 2 - Frontend
./start_frontend.sh
```

### 2. Login to CVAT (Required)

1. Go to http://localhost:3000
2. Login with credentials: `admin` / `#@Pjain9329`
3. Keep the browser tab open

### 3. Run the Interactive Script

The script will detect your browser session and work automatically!

```bash
# Full interactive experience
python interactive_download.py

# Or use the simple version for quick testing
python simple_download.py
```

## 🎮 Interactive Flow

### Step 1: Automatic Login
The script automatically logs in to CVAT using the configured credentials.

```
🎯 CVAT Annotated Frames Downloader
==================================================
🔐 Authentication required, attempting login...
🔐 Getting CSRF token...
🔑 Logging in...
✅ Login successful!
```

### Step 2: Job Selection
The script displays all available jobs in a formatted table:

```
📋 Available Jobs:
================================================================================
ID   Task                 Status       Assignee        Stage
--------------------------------------------------------------------------------
1    Task 1               annotation   admin           annotation
2    My Video Task        annotation   admin           annotation
================================================================================

🎯 Select a job (1-2) or 'q' to quit: 1
✅ Selected Job 1: Task 1
```

### Step 3: Label Selection
Shows all labels available for the selected task:

```
🏷️  Available Labels:
============================================================
ID   Name                     Type            Color
------------------------------------------------------------
1    person                   rectangle       #ff0000
2    car                      rectangle       #00ff00
3    bicycle                  polygon         #0000ff
------------------------------------------------------------
0    [All Labels]             -               -
============================================================

🏷️  Select a label (0 for all, 1-3 for specific) or 'q' to quit: 1
✅ Selected Label 1: person
```

### Step 4: Download
The script downloads the annotated frames:

```
📥 Downloading annotated frames...
   Job ID: 1
   Label ID: 1
📡 Response Status: 200
✅ Success! Downloaded 2,048,576 bytes
📁 Saved as: job_1_label_1_frames.zip

🎉 Download completed successfully!
```

## 📁 Output Files

The script generates ZIP files with descriptive names:

- **Single Label**: `job_1_label_5_frames.zip`
- **All Labels**: `job_1_all_labels_frames.zip`

Each ZIP contains PNG images with annotations overlaid:
```
job_1_label_1_frames.zip
├── frame_000001.png
├── frame_000005.png
├── frame_000012.png
└── ...
```

## 🎛️ Features

### ✅ User-Friendly Interface
- Clear prompts and instructions
- Formatted tables for easy reading
- Color-coded status messages
- Graceful error handling

### ✅ Flexible Selection
- Choose specific jobs from all available
- Filter by specific labels or download all
- Option to quit at any step

### ✅ Robust Error Handling
- Authentication checks
- Connection error detection
- Invalid input validation
- Graceful keyboard interrupt handling

### ✅ Detailed Feedback
- Progress indicators
- File size information
- Clear success/error messages
- Helpful troubleshooting tips

## 🛠️ Troubleshooting

### Authentication Issues
```
❌ Authentication required!
```
**Solution**: Login to CVAT at http://localhost:3000 first

### Connection Issues
```
❌ Connection error: Connection refused
```
**Solution**: Make sure backend is running with `./start_dev.sh`

### No Jobs Found
```
❌ No jobs found!
```
**Solution**: Create a task with jobs in CVAT first

### No Annotations Found
```
ℹ️  No annotated frames found for the specified criteria
```
**Solution**: Add annotations to frames in the selected job

## 🔧 Advanced Usage

### Command Line Testing
You can also test the API directly:

```bash
# Download all labels for job 1
curl -X GET "http://localhost:8000/api/custom/download-annotated-frames/?job_id=1" \
  -H "Cookie: sessionid=YOUR_SESSION" \
  -o "frames.zip"

# Download specific label for job 1
curl -X GET "http://localhost:8000/api/custom/download-annotated-frames/?job_id=1&label_id=5" \
  -H "Cookie: sessionid=YOUR_SESSION" \
  -o "frames.zip"
```

### Python API Usage
```python
import requests

session = requests.Session()
# ... login process ...

response = session.get(
    "http://localhost:8000/api/custom/download-annotated-frames/",
    params={"job_id": 1, "label_id": 5}
)

if response.status_code == 200:
    with open("frames.zip", "wb") as f:
        f.write(response.content)
```

## 📊 Example Session

```
🎯 CVAT Annotated Frames Downloader
==================================================
✅ Authentication successful!

🔍 Fetching jobs...

📋 Available Jobs:
================================================================================
ID   Task                 Status       Assignee        Stage
--------------------------------------------------------------------------------
1    My Images            annotation   admin           annotation
2    Video Analysis       annotation   admin           annotation
================================================================================

🎯 Select a job (1-2) or 'q' to quit: 1
✅ Selected Job 1: My Images

🔍 Fetching labels for task 1...

🏷️  Available Labels:
============================================================
ID   Name                     Type            Color
------------------------------------------------------------
5    person                   rectangle       #ff0000
6    vehicle                  rectangle       #00ff00
------------------------------------------------------------
0    [All Labels]             -               -
============================================================

🏷️  Select a label (0 for all, 1-2 for specific) or 'q' to quit: 0
✅ Selected: All Labels

📥 Downloading annotated frames...
   Job ID: 1
   Label ID: All Labels
📡 Response Status: 200
✅ Success! Downloaded 1,234,567 bytes
📁 Saved as: job_1_all_labels_frames.zip

🎉 Download completed successfully!
```

---

**Ready to download your annotated frames!** 🎯
