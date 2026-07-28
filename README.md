# Frappe LMS MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that lets AI agents manage a Frappe LMS instance — create courses, chapters, lessons, quizzes, enrollments, batches, and certificates.

Designed for instructors and admins who want to build comprehensive course content using AI.

## Features

- **39 MCP tools** for managing Frappe LMS (courses, chapters, lessons, quizzes, enrollments, batches, certificates)
- **Web dashboard** (FastAPI + Jinja2) on port 8080 for browser-based login and course browsing
- **SQLite database** for connection storage, course caching, and audit logging
- **Dual authentication** — API key/secret (token auth) or password (session auth fallback)
- **Course memory** — auto-cache course specs on creation for cross-instance re-upload
- **Multi-instance** — store multiple Frappe connections, switch between them
- **Audit trail** — all operations logged to SQLite

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │     MCP Server Process (Python)     │
                    │                                     │
  AI Agent ────────►│  FastMCP (stdio)    FastAPI (:8080) │
  (ZCode, Claude,   │       │                  │           │
   Codex, etc.)     │       ▼                  ▼           │
                    │   tools.py ◄──── Web Dashboard      │
                    │       │          (login UI,         │
                    │       │           course browser)   │
                    │       ▼                             │
                    │   client.py ◄── API Key/Secret      │
                    │       │        (from SQLite)        │
                    │       ▼                             │
                    │   SQLite (frappe_lms.db)            │
                    │   - connections: api_key, password  │
                    │   - courses: id, title, spec_json   │
                    │   - operations: audit log           │
                    └───────┬─────────────────────────────┘
                            │
                            ▼
                    Frappe LMS (localhost:8000)
```

## Project Structure

```
lms-mcp-tools/
├── pyproject.toml                  # Package config, deps, entry points
├── README.md
├── .env.example                    # Template credentials (safe to commit)
├── .gitignore
├── src/frappe_lms_mcp/
│   ├── __init__.py
│   ├── client.py                   # FrappeClient — REST API wrapper (dual auth)
│   ├── content_blocks.py           # EditorJS block builders
│   ├── db.py                       # SQLite schema + CRUD (connections, cache, logs)
│   ├── dashboard.py                # FastAPI web dashboard (login, courses, logs)
│   ├── dashboard_cli.py            # Standalone dashboard entry point
│   ├── tools.py                    # Tool implementations (business logic)
│   ├── server.py                   # FastMCP server — registers 39 tools + dual-start
│   └── templates/                  # Jinja2 HTML templates (8 pages)
├── skill/
│   └── SKILL.md                    # Skill definition for AI agents
└── examples/
    └── web-development-course.json # Example course spec
```

---

## Step-by-Step Setup

### Prerequisites

- **Python 3.10+** (tested on 3.11)
- **Frappe LMS** running and reachable (e.g. via Docker on `http://localhost:8000`)
- A **Frappe user** with Course Creator or Moderator role

### Step 1 — Clone & Install

```bash
git clone https://github.com/anggun-indra/frape-lms-mcp-tools.git
cd frape-lms-mcp-tools

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package (editable mode)
pip install -e .
```

### Step 2 — Start Frappe LMS

Make sure your Frappe LMS instance is running. If using Docker:

```bash
cd path/to/your/frappe-docker
docker compose up -d
# Wait for Frappe to be ready
curl http://localhost:8000  # should return HTTP 200
```

### Step 3 — Configure Credentials

Choose **one** method:

#### Method A — `.env` file (simplest)

```bash
cp .env.example .env
# Edit .env with your real credentials
```

`.env` contents:
```env
FRAPPE_URL=http://localhost:8000
FRAPPE_SITE=lms.localhost
FRAPPE_USERNAME=your_email@example.com
FRAPPE_PASSWORD=your_password
```

> ⚠️ `.env` is gitignored — it will never be committed.

#### Method B — Web Dashboard (recommended — no password in config)

1. Start the dashboard:
   ```bash
   source .venv/bin/activate
   frappe-lms-dashboard
   ```
2. Open `http://localhost:8080/login` in your browser
3. Fill in: Name (e.g. "Local LMS"), Frappe URL, Site, Username, Password
4. Click "Connect" — the dashboard logs in to Frappe, generates API keys if possible, and stores them in SQLite
5. The MCP server now uses these credentials automatically — no env vars needed

#### Method C — Shell environment variables

```bash
# ~/.zshrc or ~/.bashrc
export FRAPPE_URL="http://localhost:8000"
export FRAPPE_SITE="lms.localhost"
export FRAPPE_USERNAME="your_email@example.com"
export FRAPPE_PASSWORD="your_password"
```

### Step 4 — Verify the Installation

```bash
source .venv/bin/activate

# Verify the MCP server starts and lists all tools
python -c "
from frappe_lms_mcp.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
print(f'{len(tools)} tools registered')
"
```

You should see: `39 tools registered`

### Step 5 — Register with Your AI Agent

The MCP server communicates over **stdio** (standard MCP transport). Every MCP-compatible agent can use it — the only difference is the config file location and key name.

#### ZCode

Config file: `.zcode/config.json` (workspace scope) or `~/.zcode/config.json` (user scope)

```json
{
  "mcp": {
    "servers": {
      "frappe-lms": {
        "command": "/absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp",
        "env": {
          "FRAPPE_URL": "http://localhost:8000",
          "FRAPPE_SITE": "lms.localhost",
          "FRAPPE_USERNAME": "your_email@example.com",
          "FRAPPE_PASSWORD": "your_password"
        }
      }
    }
  }
}
```

> If you configured credentials via the dashboard (Method B), you can omit the `env` block entirely — the server reads from SQLite.

#### Claude Desktop

Config file: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "frappe-lms": {
      "command": "/absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp",
      "env": {
        "FRAPPE_URL": "http://localhost:8000",
        "FRAPPE_SITE": "lms.localhost",
        "FRAPPE_USERNAME": "your_email@example.com",
        "FRAPPE_PASSWORD": "your_password"
      }
    }
  }
}
```

After saving, restart Claude Desktop. The tools will appear as `mcp__frappe-lms__<tool_name>`.

#### OpenAI Codex (GPT Codex)

Config file: `~/.codex/config.toml` or project-level `codex.toml`

```toml
[mcp_servers.frappe_lms]
command = "/absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp"
env = { FRAPPE_URL = "http://localhost:8000", FRAPPE_SITE = "lms.localhost", FRAPPE_USERNAME = "your_email@example.com", FRAPPE_PASSWORD = "your_password" }
```

Or if using Codex CLI with JSON config (`~/.codex/config.json`):

```json
{
  "mcpServers": {
    "frappe_lms": {
      "command": "/absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp",
      "env": {
        "FRAPPE_URL": "http://localhost:8000",
        "FRAPPE_SITE": "lms.localhost",
        "FRAPPE_USERNAME": "your_email@example.com",
        "FRAPPE_PASSWORD": "your_password"
      }
    }
  }
}
```

#### Claude Code (CLI)

Config file: `~/.claude/claude_config.json` or `.claude/config.json` (project scope)

```json
{
  "mcpServers": {
    "frappe-lms": {
      "command": "/absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp",
      "env": {
        "FRAPPE_URL": "http://localhost:8000",
        "FRAPPE_SITE": "lms.localhost",
        "FRAPPE_USERNAME": "your_email@example.com",
        "FRAPPE_PASSWORD": "your_password"
      }
    }
  }
}
```

#### Generic MCP Client (any MCP-compatible tool)

The server uses the standard MCP **stdio** transport. Any tool that supports MCP can connect. The minimal config is:

```
Command: /absolute/path/to/frape-lms-mcp-tools/.venv/bin/frappe-lms-mcp
Transport: stdio
Environment variables (optional if using dashboard auth):
  FRAPPE_URL=http://localhost:8000
  FRAPPE_SITE=lms.localhost
  FRAPPE_USERNAME=your_email@example.com
  FRAPPE_PASSWORD=your_password
```

> 💡 **Tip**: Replace `/absolute/path/to/` with the actual path on your machine. Use `which frappe-lms-mcp` (inside the venv) to find it.

### Step 6 — Use It!

Once registered, ask your AI agent to manage courses. Examples:

> "Create a Python programming course with 3 chapters: Basics, Data Structures, and OOP. Each chapter should have 2 lessons with content and a quiz."

The agent will use `create_full_course` with a generated JSON spec. The course is automatically cached to SQLite for future re-upload.

> "List all cached courses and re-upload course ID 1 to the active connection"

The agent uses `list_cached_courses` and `reupload_course` — no need to re-specify course details.

See `examples/web-development-course.json` for a complete course spec example.

---

## Running the Dashboard

The dashboard runs automatically alongside the MCP server (in a background thread on port 8080). To run it standalone:

```bash
source .venv/bin/activate
frappe-lms-dashboard
```

Open `http://localhost:8080` in your browser.

| Page | URL | Purpose |
|------|-----|---------|
| Dashboard | `http://localhost:8080/` | Overview: active connection, recent courses |
| Login | `http://localhost:8080/login` | Add a new Frappe connection |
| Connections | `http://localhost:8080/connections` | Manage multiple Frappe instances |
| Courses | `http://localhost:8080/courses` | Browse cached courses |
| Import | `http://localhost:8080/courses/import` | Import course from Frappe to cache |
| Logs | `http://localhost:8080/logs` | Audit trail of all operations |

To disable the dashboard (MCP-only mode):
```bash
export FRAPPE_LMS_NO_DASHBOARD=1
```

To change the dashboard port:
```bash
export FRAPPE_LMS_DASHBOARD_PORT=9090
```

---

## Authentication

The server supports two authentication methods, tried in this order:

### 1. Token Auth (API Key/Secret) — preferred
- No login needed — each request sends `Authorization: token <key>:<secret>` header
- Generated via the dashboard login flow (requires System Manager role)
- Stored in SQLite

### 2. Session Auth (Password) — fallback
- Used when the user doesn't have System Manager role (can't generate API keys)
- The server logs in with username/password and maintains a session cookie
- Password stored in SQLite (encrypted at rest by Frappe, but stored plaintext locally)

### Auth Priority in `get_client()`:
1. Active SQLite connection with API key/secret → token auth
2. Active SQLite connection with password → session auth (auto-login)
3. Environment variables (`FRAPPE_USERNAME`/`FRAPPE_PASSWORD`) → session auth
4. Error if no credentials found

---

## Available Tools (39)

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

### Batches & Certificates
| Tool | Description |
|------|-------------|
| `create_batch` | Create a batch (cohort) |
| `list_batches` | List batches |
| `issue_certificate` | Issue a certificate to a member |

### High-level
| Tool | Description |
|------|-------------|
| `create_full_course` | Create an entire course from a JSON spec (auto-caches to SQLite) |

### Connections & Cache (SQLite)
| Tool | Description |
|------|-------------|
| `list_connections` | List all saved Frappe connections (secrets masked) |
| `switch_connection` | Activate a different Frappe instance |
| `list_cached_courses` | List courses from SQLite cache (fast, no Frappe query) |
| `get_cached_course` | Get full cached course including spec JSON |
| `reupload_course` | Re-upload a cached course spec to a Frappe instance |
| `import_course_from_frappe` | Fetch a course from Frappe and cache it to SQLite |
| `list_operation_logs` | View audit trail of all operations |

---

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

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FRAPPE_URL` | `http://localhost:8000` | Frappe base URL |
| `FRAPPE_SITE` | `lms.localhost` | Frappe site name |
| `FRAPPE_USERNAME` | *(none)* | Login username/email |
| `FRAPPE_PASSWORD` | *(none)* | Login password |
| `FRAPPE_API_KEY` | *(none)* | API key for token auth (alternative to password) |
| `FRAPPE_API_SECRET` | *(none)* | API secret for token auth |
| `FRAPPE_LMS_NO_DASHBOARD` | *(unset)* | Set to `1` to disable the web dashboard |
| `FRAPPE_LMS_DASHBOARD_PORT` | `8080` | Port for the web dashboard |
| `FRAPPE_LMS_DB_PATH` | `data/frappe_lms.db` | SQLite database file path |
| `FRAPPE_LMS_SESSION_SECRET` | *(random)* | Secret key for dashboard session cookies |

---

## Development

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run the server directly (with dashboard)
python -m frappe_lms_mcp.server

# Run dashboard only (no MCP)
frappe-lms-dashboard

# Run tests
pytest
```

---

## Security Notes

- **Credentials live in `.env`** (gitignored) or SQLite (in `data/`, also gitignored) — never committed.
- `.env.example` (committed) contains only placeholder values — safe to share.
- The MCP server inherits the permissions of the configured Frappe user. For production, create a dedicated Frappe user with only the LMS roles needed (Course Creator, Moderator) rather than using Administrator.
- The SQLite database at `data/frappe_lms.db` contains API keys and passwords — it is gitignored. If you need to share the project, delete this file first.
- API key generation requires the System Manager role. Users without this role fall back to session auth (password stored in SQLite).

---

## License

MIT
