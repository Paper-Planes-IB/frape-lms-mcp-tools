# Frappe LMS MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that lets AI agents manage a Frappe LMS instance — create courses, chapters, lessons, quizzes, enrollments, batches, and certificates.

Designed for instructors and admins who want to build comprehensive course content using AI.

## Features

- **Course management** — create, read, update, delete, publish courses
- **Chapter management** — create, reorder, delete chapters
- **Lesson management** — create lessons with rich EditorJS content (paragraphs, headers, lists, code blocks, images, video embeds, inline quizzes)
- **Quiz management** — create quizzes with multiple-choice, user-input, and open-ended questions
- **Enrollment management** — enroll students, list enrollments, unenroll
- **Batch management** — create cohorts with linked courses
- **Certificate issuance** — manually issue completion certificates
- **One-shot course creation** — `create_full_course` builds an entire course (chapters + lessons + quizzes) from a single JSON spec

## Quick Start

### 1. Install

```bash
cd lms-mcp-tools
pip install -e .
```

### 2. Configure Credentials (Important!)

The server needs Frappe LMS credentials to connect. **Never hardcode passwords in config files that may be committed to git.** Use a `.env` file instead.

```bash
cd lms-mcp-tools
cp .env.example .env
# Edit .env with your real credentials
```

`.env` file format:
```env
FRAPPE_URL=http://localhost:8000
FRAPPE_SITE=lms.localhost
FRAPPE_USERNAME=your_username
FRAPPE_PASSWORD=your_password
```

> ⚠️ The `.env` file is **gitignored** — it will never be committed. Only `.env.example` (with placeholder values) is safe to commit.

The server reads these environment variables (with safe defaults for local dev only):

| Variable           | Default                  | Description                |
|--------------------|--------------------------|----------------------------|
| `FRAPPE_URL`       | `http://localhost:8000`  | Frappe base URL            |
| `FRAPPE_SITE`      | `lms.localhost`          | Site name                  |
| `FRAPPE_USERNAME`  | `Administrator`          | Login user                 |
| `FRAPPE_PASSWORD`  | *(no default — required)*| Login password             |

### 3. Register with ZCode / Claude Desktop

The MCP `env` block in the client config should reference your real credentials. **Two approaches:**

**Option A — Inline in workspace config (local dev only)**

The workspace config `.zcode/config.json` is gitignored, so it's safe to put credentials there directly:
```json
{
  "mcp": {
    "servers": {
      "frappe-lms": {
        "command": "/path/to/lms-mcp-tools/.venv/bin/frappe-lms-mcp",
        "env": {
          "FRAPPE_URL": "http://localhost:8000",
          "FRAPPE_SITE": "lms.localhost",
          "FRAPPE_USERNAME": "Administrator",
          "FRAPPE_PASSWORD": "your_real_password"
        }
      }
    }
  }
}
```

**Option B — Shell environment (recommended for production)**

Export the variables in your shell profile (`~/.zshrc` / `~/.bashrc`), then the MCP config only needs the command:
```json
{
  "mcp": {
    "servers": {
      "frappe-lms": {
        "command": "/path/to/lms-mcp-tools/.venv/bin/frappe-lms-mcp"
      }
    }
  }
}
```
```bash
# ~/.zshrc
export FRAPPE_URL="http://localhost:8000"
export FRAPPE_SITE="lms.localhost"
export FRAPPE_USERNAME="Administrator"
export FRAPPE_PASSWORD="your_real_password"
```

**Claude Desktop** (`claude_desktop_config.json`) — same structure with `mcpServers`:
```json
{
  "mcpServers": {
    "frappe-lms": {
      "command": "/path/to/lms-mcp-tools/.venv/bin/frappe-lms-mcp",
      "env": {
        "FRAPPE_URL": "http://localhost:8000",
        "FRAPPE_SITE": "lms.localhost",
        "FRAPPE_USERNAME": "Administrator",
        "FRAPPE_PASSWORD": "your_real_password"
      }
    }
  }
}
```

### 4. Use

Once registered, the AI agent can call any of the tools. For example:

> "Create a Python programming course with 3 chapters: Basics, Data Structures, and OOP. Each chapter should have 2 lessons with content and a quiz."

The agent will use `create_full_course` with a generated spec.

See `examples/web-development-course.json` for a complete course spec example.

## Available Tools

### Courses
| Tool | Description |
|------|-------------|
| `list_courses` | List courses (optionally published only) |
| `get_course` | Get course details + chapter/lesson outline |
| `create_course` | Create a new course |
| `update_course` | Update course fields |
| `delete_course` | Delete a course and all dependencies |
| `publish_course` | Toggle published status |

### Chapters
| Tool | Description |
|------|-------------|
| `create_chapter` | Create a chapter in a course |
| `get_chapter` | Get chapter with its lessons |
| `update_chapter` | Rename a chapter |
| `delete_chapter` | Delete chapter + lessons |
| `reorder_chapter` | Move chapter to new position |

### Lessons
| Tool | Description |
|------|-------------|
| `create_lesson` | Create a lesson with content |
| `get_lesson` | Get lesson content and metadata |
| `update_lesson` | Update lesson fields |
| `delete_lesson` | Delete a lesson |
| `move_lesson` | Move/reorder lesson between chapters |
| `build_lesson_content` | Build EditorJS JSON from a spec |
| `add_paragraph_to_content` | Append paragraph to content |

### Quizzes & Questions
| Tool | Description |
|------|-------------|
| `create_question` | Create a reusable question |
| `create_quiz` | Create a quiz with questions |
| `add_question_to_quiz` | Add question to existing quiz |
| `get_quiz` | Get quiz with question details |
| `list_quizzes` | List all quizzes |
| `delete_quiz` | Delete a quiz |
| `embed_quiz_in_lesson` | Embed quiz in lesson content |

### Enrollments
| Tool | Description |
|------|-------------|
| `enroll_student` | Enroll a student in a course |
| `list_enrollments` | List enrollments (filter by course/student) |
| `unenroll_student` | Remove an enrollment |

### Batches
| Tool | Description |
|------|-------------|
| `create_batch` | Create a batch (cohort) |
| `list_batches` | List batches |

### Certificates
| Tool | Description |
|------|-------------|
| `issue_certificate` | Issue a certificate to a member |

### High-level
| Tool | Description |
|------|-------------|
| `create_full_course` | Create an entire course from a JSON spec |

## Lesson Content Format

Lessons use [EditorJS](https://editorjs.io/) JSON for rich content. The `build_lesson_content` tool accepts a spec with these optional keys:

```json
{
  "paragraphs": ["Plain text paragraphs"],
  "headers": [{"text": "Section Title", "level": 2}],
  "lists": [{"items": ["item 1", "item 2"], "ordered": true}],
  "images": [{"url": "/files/image.png", "caption": "A diagram"}],
  "code": [{"code": "print('hello')", "language": "python"}],
  "embeds": [{"service": "youtube", "source": "https://youtube.com/watch?v=..."}],
  "quiz_refs": ["quiz-slug-name"],
  "markdown": ["## Raw markdown section"]
}
```

## Architecture

```
lms-mcp-tools/
├── pyproject.toml              # Package config & entry point
├── README.md
├── src/frappe_lms_mcp/
│   ├── __init__.py
│   ├── client.py               # FrappeClient — REST API wrapper
│   ├── content_blocks.py        # EditorJS block builders
│   ├── tools.py                # Tool implementations (business logic)
│   └── server.py               # FastMCP server — registers all tools
├── skill/
│   └── SKILL.md                # ZCode skill for workflow guidance
└── examples/
    └── web-development-course.json  # Example course spec
```

## Development

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests (when available)
pytest

# Run the server directly
python -m frappe_lms_mcp.server
```

## Security Notes

- **Credentials live in `.env`** (gitignored) or your shell profile — never commit real passwords.
- `.zcode/config.json` is also gitignored, so inline credentials there are safe for local dev only.
- `.env.example` (committed) contains only placeholder values — safe to share.
- The default `Administrator`/`admin` is for **local development only**. Change it before exposing the Frappe instance.
- The MCP server inherits the permissions of the configured Frappe user. For production, create a dedicated Frappe user with only the LMS roles needed (Course Creator, Moderator) rather than using Administrator.
- For production, create a dedicated Frappe user with Course Creator/Moderator role.
