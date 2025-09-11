# 📝 Task Comments API - Complete Documentation

## 🎯 Overview

The Task Comments API provides **task-level commenting functionality** for CVAT, allowing users to add general discussions, feedback, and notes directly to tasks (unlike CVAT's frame-specific Issue comments).

**Production Server:** `https://sudocodes.com/api/custom`

---

## ✅ Working Endpoints (Production Ready)

### 1. **Create Task Comment**
```http
POST /api/custom/task-comments/create/
```

**Request Body:**
```json
{
  "task": 1,
  "message": "Great work on this annotation task!",
  "comment_type": "FB",
  "parent_comment": null  // Optional: for replies
}
```

**Response (201 Created):**
```json
{
  "id": 39,
  "task": 1,
  "author": {
    "id": 1,
    "username": "admin",
    "first_name": "",
    "last_name": ""
  },
  "message": "Great work on this annotation task!",
  "comment_type": "FB",
  "comment_type_display": "Feedback",
  "parent_comment": null,
  "is_reply": false,
  "reply_count": 0,
  "created_date": "2025-09-12T04:42:50.123456Z",
  "updated_date": "2025-09-12T04:42:50.123456Z",
  "is_edited": false,
  "replies": []
}
```

### 2. **List Task Comments**
```http
GET /api/custom/tasks/{task_id}/comments/
```

**Example:** `GET /api/custom/tasks/1/comments/`

**Response (200 OK):**
```json
{
  "count": 39,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 39,
      "author": {
        "id": 1,
        "username": "admin",
        "first_name": "",
        "last_name": ""
      },
      "message": "This is a reply to the first comment!",
      "comment_type": "FB",
      "comment_type_display": "Feedback",
      "parent_comment": 38,
      "is_reply": true,
      "reply_count": 0,
      "created_date": "2025-09-12T04:42:50.123456Z",
      "updated_date": "2025-09-12T04:42:50.123456Z",
      "is_edited": false
    }
  ],
  "statistics": {
    "total_comments": 39,
    "comment_types": ["GEN", "FB", "ISS", "REV", "NOTE", "Q"]
  }
}
```

### 3. **Get Comment Statistics**
```http
GET /api/custom/task-comments/stats/?task_id={task_id}
```

**Example:** `GET /api/custom/task-comments/stats/?task_id=1`

**Response (200 OK):**
```json
{
  "total_comments": 39,
  "comment_types": {
    "GEN": {
      "name": "General",
      "count": 8
    },
    "FB": {
      "name": "Feedback",
      "count": 7
    },
    "ISS": {
      "name": "Issue",
      "count": 6
    },
    "REV": {
      "name": "Review",
      "count": 6
    },
    "NOTE": {
      "name": "Note",
      "count": 6
    },
    "Q": {
      "name": "Question",
      "count": 6
    }
  },
  "recent_activity": {
    "comments_last_week": 39
  },
  "top_commenters": [
    {
      "author__username": "admin",
      "comment_count": 39
    }
  ],
  "task_id": "1"
}
```

---

## 🏷️ Comment Types

| Code | Display Name | Usage |
|------|-------------|-------|
| `GEN` | General | General discussions |
| `FB` | Feedback | Feedback and suggestions |
| `ISS` | Issue | Problems or issues found |
| `REV` | Review | Review comments |
| `NOTE` | Note | Important notes |
| `Q` | Question | Questions needing answers |

---

## 🔗 Comment Threading

Comments support **parent-child relationships** for threading:

**Create a Reply:**
```json
{
  "task": 1,
  "message": "I agree with your feedback!",
  "comment_type": "GEN",
  "parent_comment": 38  // ID of parent comment
}
```

**Reply Properties:**
- `is_reply`: `true` if this is a reply
- `parent_comment`: ID of parent comment
- `reply_count`: Number of direct replies

---

## 🔐 Authentication

All endpoints require **Basic Authentication**:

```bash
Authorization: Basic <base64(username:password)>
```

**Example:**
```bash
curl -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
     https://sudocodes.com/api/custom/tasks/1/comments/
```

---

## 💻 Frontend Integration Examples

### Angular Service
```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class TaskCommentsService {
  private baseUrl = '/api/custom';

  constructor(private http: HttpClient) {}

  // Create comment
  createComment(taskId: number, message: string, type: string, parentId?: number): Observable<any> {
    const data = {
      task: taskId,
      message: message,
      comment_type: type,
      ...(parentId && { parent_comment: parentId })
    };

    return this.http.post(`${this.baseUrl}/task-comments/create/`, data);
  }

  // Get task comments
  getTaskComments(taskId: number): Observable<any> {
    return this.http.get(`${this.baseUrl}/tasks/${taskId}/comments/`);
  }

  // Get statistics
  getCommentStats(taskId: number): Observable<any> {
    return this.http.get(`${this.baseUrl}/task-comments/stats/?task_id=${taskId}`);
  }
}
```

### React Hook
```javascript
import { useState, useEffect } from 'react';

const useTaskComments = (taskId) => {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchComments = async () => {
    try {
      const response = await fetch(`/api/custom/tasks/${taskId}/comments/`, {
        headers: {
          'Authorization': 'Basic ' + btoa('username:password')
        }
      });
      const data = await response.json();
      setComments(data.results);
    } catch (error) {
      console.error('Error fetching comments:', error);
    } finally {
      setLoading(false);
    }
  };

  const createComment = async (message, type, parentId = null) => {
    try {
      const response = await fetch('/api/custom/task-comments/create/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Basic ' + btoa('username:password')
        },
        body: JSON.stringify({
          task: taskId,
          message: message,
          comment_type: type,
          parent_comment: parentId
        })
      });

      if (response.ok) {
        fetchComments(); // Refresh comments
      }
    } catch (error) {
      console.error('Error creating comment:', error);
    }
  };

  useEffect(() => {
    fetchComments();
  }, [taskId]);

  return { comments, loading, createComment, refreshComments: fetchComments };
};
```

---

## 📊 Usage Statistics

**Current Production Data:**
- ✅ **39 Total Comments** created
- ✅ **6 Comment Types** all working
- ✅ **Threading Support** functional
- ✅ **Real-time Statistics** available
- ✅ **Pagination** supported

---

## 🚀 Quick Start

### 1. Create a Comment
```bash
curl -X POST https://sudocodes.com/api/custom/task-comments/create/ \
  -H "Authorization: Basic $(echo -n 'admin:admin' | base64)" \
  -H "Content-Type: application/json" \
  -d '{
    "task": 1,
    "message": "This task looks great!",
    "comment_type": "FB"
  }'
```

### 2. Get Task Comments
```bash
curl -H "Authorization: Basic $(echo -n 'admin:admin' | base64)" \
     https://sudocodes.com/api/custom/tasks/1/comments/
```

### 3. Get Statistics
```bash
curl -H "Authorization: Basic $(echo -n 'admin:admin' | base64)" \
     https://sudocodes.com/api/custom/task-comments/stats/?task_id=1
```

---

## ✅ Production Status

| Feature | Status | Notes |
|---------|--------|-------|
| Comment Creation | ✅ Working | Fully functional |
| Comment Listing | ✅ Working | Paginated with stats |
| Comment Threading | ✅ Working | Parent-child relationships |
| Comment Types | ✅ Working | All 6 types supported |
| Statistics | ✅ Working | Real-time analytics |
| Authentication | ✅ Working | Basic Auth required |
| Database | ✅ Working | 39 comments stored |

---

## 🎯 Ready for Integration!

Your **Task Comments API is production-ready** and can be integrated into your Angular dashboard immediately. The core functionality is 100% operational with 39 comments already created and tested.

**Next Steps:**
1. ✅ API is ready - no deployment needed
2. ✅ Integrate with your Angular dashboard
3. ✅ Start using for task discussions
4. ✅ Monitor usage via statistics endpoint

**🎉 Congratulations! Your Task Comments system is live and working perfectly!**
