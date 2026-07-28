---
name: frappe-lms-manager
description: Manage Frappe LMS courses, chapters, lessons, quizzes, and enrollments via the frappe-lms-mcp MCP server. Use when the user asks to create, update, list, or delete courses, build course content, create quizzes with questions, manage student enrollments, or create batches in a Frappe LMS instance.
---

# Frappe LMS Manager

Manage a Frappe LMS instance (courses, chapters, lessons, quizzes, enrollments, batches, certificates) using the `frappe-lms-mcp` MCP server. Works with ZCode, Claude Desktop, Claude Code, OpenAI Codex, and any MCP-compatible client.

## Prerequisites

1. **Frappe LMS** must be running (default: `http://localhost:8000`).
2. **MCP server** must be configured in your AI agent's MCP settings.
3. **Credentials** — either:
   - Set `FRAPPE_URL`, `FRAPPE_SITE`, `FRAPPE_USERNAME`, `FRAPPE_PASSWORD` as environment variables, or
   - Log in via the web dashboard at `http://localhost:8080/login` (credentials stored in SQLite automatically).

## Web Dashboard

The MCP server also runs a web dashboard on `http://localhost:8080` (started automatically). Use it to:
- **Login** to a Frappe instance and generate/store API keys in SQLite
- **Manage connections** — add, activate, or delete multiple Frappe instances
- **Browse cached courses** — view course specs saved in SQLite
- **Import courses** from Frappe into the local cache
- **Re-upload courses** to any Frappe instance by course ID
- **View audit logs** — all operations are logged

To run the dashboard standalone: `frappe-lms-dashboard`

## Core Workflow: Creating a Comprehensive Course

### Option A — One-shot with `create_full_course` (preferred for AI agents)

Pass a single JSON spec that defines the entire course structure. The tool creates the course, all chapters, all lessons (with EditorJS content), and all quizzes (with questions) in one call. The course spec is **automatically cached** to SQLite for future re-upload.

```
create_full_course(spec='{
  "title": "Introduction to Python",
  "short_introduction": "Learn Python from scratch",
  "description": "<p>A comprehensive Python course for beginners.</p>",
  "instructor": "Administrator",
  "tags": "Python, Programming, Beginner",
  "published": false,
  "chapters": [
    {
      "title": "Getting Started",
      "lessons": [
        {
          "title": "Why Python?",
          "content": {
            "headers": [{"text": "Overview", "level": 2}],
            "paragraphs": ["Python is a high-level, interpreted programming language."],
            "lists": [{"items": ["Easy to learn", "Versatile", "Large community"], "ordered": true}]
          }
        },
        {
          "title": "Your First Program",
          "content": {
            "paragraphs": ["Let us write our first Python program."],
            "code": [{"code": "print(\\"Hello, World!\\")", "language": "python"}]
          }
        },
        {
          "title": "Knowledge Check",
          "content": {"paragraphs": ["Test your understanding."]},
          "quiz": {
            "title": "Python Basics Quiz",
            "passing_percentage": 70,
            "questions": [
              {
                "question": "Is Python compiled or interpreted?",
                "type": "Choices",
                "options": [
                  {"text": "Compiled", "correct": false, "explanation": "Python is not compiled to machine code."},
                  {"text": "Interpreted", "correct": true, "explanation": "Python code is executed line by line by an interpreter."}
                ]
              }
            ]
          }
        }
      ]
    }
  ]
}')
```

### Option B — Step-by-step (for incremental edits)

1. `create_course(title, short_introduction, instructor, ...)` → returns course slug
2. `create_chapter(course, title)` → returns chapter name
3. `create_lesson(chapter, title, content)` → returns lesson name
4. `build_lesson_content(...)` → build EditorJS JSON for step 3's `content` parameter
5. `create_question(...)` → create reusable question
6. `create_quiz(title, passing_percentage, questions=[...])` → returns quiz slug
7. `embed_quiz_in_lesson(lesson, quiz)` → embed quiz in lesson content

## Lesson Content Spec

The `content` field on lessons is an EditorJS JSON string. Use `build_lesson_content` (or the `content` key in `create_full_course`) with these optional keys:

| Key         | Format                                           | Example                                                |
|-------------|--------------------------------------------------|--------------------------------------------------------|
| `paragraphs`| `["text", ...]`                                  | `["Python is great."]`                                 |
| `headers`   | `[{"text": "...", "level": 2}]`                  | `[{"text": "Overview", "level": 2}]`                   |
| `lists`     | `[{"items": [...], "ordered": false}]`           | `[{"items": ["a", "b"], "ordered": true}]`             |
| `images`    | `[{"url": "...", "caption": "..."}]`             | `[{"url": "/files/img.png", "caption": "Diagram"}]`    |
| `code`      | `[{"code": "...", "language": "python"}]`        | `[{"code": "print(1)", "language": "python"}]`         |
| `embeds`    | `[{"service": "youtube", "source": "url"}]`      | `[{"service": "youtube", "source": "https://..."}]`    |
| `quiz_refs` | `["quiz-slug"]`                                  | `["python-basics-quiz"]`                               |
| `markdown`  | `["raw markdown"]`                               | `["## Section\n- item"]`                               |

## Available Tools

### Courses
- `list_courses(published_only, limit)` — list courses
- `get_course(course)` — get course + outline
- `create_course(title, short_introduction, ...)` — create a course
- `update_course(course, fields)` — update fields (JSON string)
- `delete_course(course)` — delete course + dependencies
- `publish_course(course, published)` — toggle publish

### Chapters
- `create_chapter(course, title)` — create chapter
- `get_chapter(chapter)` — get chapter + lessons
- `update_chapter(chapter, title)` — rename chapter
- `delete_chapter(chapter)` — delete chapter + lessons
- `reorder_chapter(course, chapter, idx)` — reorder

### Lessons
- `create_lesson(chapter, title, content)` — create lesson
- `get_lesson(lesson)` — get lesson content
- `update_lesson(lesson, title, content, ...)` — update lesson
- `delete_lesson(lesson, chapter)` — delete lesson
- `move_lesson(lesson, source_chapter, target_chapter, idx)` — move/reorder
- `build_lesson_content(content_spec)` — build EditorJS JSON
- `add_paragraph_to_content(existing_content, text)` — append paragraph

### Quizzes & Questions
- `create_question(question, question_type, options, possibilities)` — create question
- `create_quiz(title, passing_percentage, questions, ...)` — create quiz
- `add_question_to_quiz(quiz, question, marks)` — add question to quiz
- `get_quiz(quiz, with_questions)` — get quiz details
- `list_quizzes(limit)` — list quizzes
- `delete_quiz(quiz)` — delete quiz
- `embed_quiz_in_lesson(lesson, quiz)` — embed quiz in lesson

### Enrollments
- `enroll_student(course, student, member_type)` — enroll student
- `list_enrollments(course, student, limit)` — list enrollments
- `unenroll_student(enrollment)` — remove enrollment

### Batches
- `create_batch(title, start_date, ...)` — create batch
- `list_batches(limit)` — list batches

### Certificates
- `issue_certificate(course, member, template, ...)` — issue certificate

### High-level
- `create_full_course(spec)` — create entire course from JSON spec (auto-caches to SQLite)

### Connections & Cache (SQLite memory)
- `list_connections()` — list all saved Frappe connections (secrets masked)
- `switch_connection(connection_name)` — activate a different Frappe instance
- `list_cached_courses(connection_name="")` — list courses from SQLite cache (fast, no Frappe query)
- `get_cached_course(course_id)` — get full cached course including spec JSON
- `reupload_course(course_id, connection_name="")` — re-upload a cached course spec to a Frappe instance
- `import_course_from_frappe(course_slug)` — fetch a course from Frappe and cache it to SQLite
- `list_operation_logs(limit=50)` — view audit trail of all operations

## Tips

- Course, quiz, and batch names are URL slugs auto-generated from titles.
- Lesson `course` is auto-fetched from `chapter.course` — never set it directly.
- Quiz names embedded in lesson content must already exist.
- Questions are reusable across quizzes (standalone LMS Question docs).
- Always create the course first, then chapters, then lessons.
- Use `published: false` during creation, then `publish_course` when ready.
- Courses created via `create_full_course` are auto-cached to SQLite. Use `list_cached_courses` to browse them and `reupload_course` to deploy to another Frappe instance without re-specifying details.
