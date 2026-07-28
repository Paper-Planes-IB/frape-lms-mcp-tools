"""FastAPI web dashboard for the Frappe LMS MCP server.

Provides a browser UI for:
  • Logging in to a Frappe instance (generates & stores API keys in SQLite)
  • Managing multiple Frappe connections (activate / delete)
  • Browsing cached courses (with full spec JSON)
  • Importing courses from Frappe into the cache
  • Viewing the operation audit log

The dashboard runs on port 8080 and shares the same SQLite database as the
MCP tools.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db
from .client import FrappeAPIError, FrappeClient

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="Frappe LMS MCP Dashboard")
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# Session middleware enables flash messages to survive across redirects (PRG pattern).
# The secret key can be set via env var for production; otherwise a random one is
# generated per process start (fine for local single-user dashboard).
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("FRAPPE_LMS_SESSION_SECRET", secrets.token_hex(32)),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_db() -> None:
    db.init_db()


def _flash(request: Request, message: str, category: str = "info") -> None:
    """Store a flash message in the session so it survives redirects."""
    flashes = request.session.get("flashes", [])
    flashes.append({"message": message, "category": category})
    request.session["flashes"] = flashes


def _get_flashes(request: Request) -> list[dict]:
    """Retrieve and clear flash messages from the session."""
    flashes = request.session.pop("flashes", [])
    return flashes


# ---------------------------------------------------------------------------
# Routes — Dashboard home
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    _ensure_db()
    connections = db.list_connections()
    active = db.get_active_connection()
    courses = db.list_cached_courses()
    return templates.TemplateResponse(request, "dashboard.html", {
        "connections": connections,
        "active": active,
        "courses": courses[:10],  # Show 10 most recent
        "flashes": _get_flashes(request),
    })


# ---------------------------------------------------------------------------
# Routes — Login / Add connection
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "flashes": _get_flashes(request),
    })


@app.post("/login")
async def login_submit(
    request: Request,
    name: str = Form(...),
    base_url: str = Form("http://localhost:8000"),
    site: str = Form("lms.localhost"),
    username: str = Form(...),
    password: str = Form(...),
):
    _ensure_db()
    try:
        api_key, api_secret, user_email = FrappeClient.login_and_generate_keys(
            url=base_url, site=site, username=username, password=password
        )
    except FrappeAPIError as e:
        _flash(request, f"Login failed: {e}", "error")
        return templates.TemplateResponse(request, "login.html", {
            "form_data": {"name": name, "base_url": base_url, "site": site, "username": username},
            "flashes": _get_flashes(request),
        })

    # Determine auth method: API keys (token auth) if available, else password (session auth)
    use_token_auth = bool(api_key and api_secret)

    # Check for duplicate name
    if db.get_connection_by_name(name):
        _flash(request, f"Connection '{name}' already exists. Updating credentials.", "warning")
        existing = db.get_connection_by_name(name)
        if use_token_auth:
            db.update_connection(existing["id"],
                                 base_url=base_url, site=site,
                                 api_key=api_key, api_secret=api_secret,
                                 password="",  # clear password if we now have API keys
                                 username=user_email)
        else:
            db.update_connection(existing["id"],
                                 base_url=base_url, site=site,
                                 api_key="", api_secret="",
                                 password=password,
                                 username=user_email)
        db.set_active_connection(existing["id"])
    else:
        db.add_connection(
            name=name, base_url=base_url, site=site,
            api_key=api_key or "", api_secret=api_secret or "",
            password=password if not use_token_auth else "",
            username=user_email, activate=True,
        )

    if use_token_auth:
        _flash(request, f"Connected to '{name}' as {user_email}. API keys saved.", "success")
    else:
        _flash(request, f"Connected to '{name}' as {user_email} (session auth — API keys need System Manager role).", "success")
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Connection management
# ---------------------------------------------------------------------------

@app.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    _ensure_db()
    connections = db.list_connections()
    return templates.TemplateResponse(request, "connections.html", {
        "connections": connections,
        "flashes": _get_flashes(request),
    })


@app.post("/connections/{conn_id}/activate")
async def activate_connection(conn_id: int):
    _ensure_db()
    db.set_active_connection(conn_id)
    # Reset the MCP tools singleton so it picks up new credentials
    from . import tools
    tools.reset_client()
    return RedirectResponse(url="/connections", status_code=303)


@app.post("/connections/{conn_id}/delete")
async def delete_connection(conn_id: int):
    _ensure_db()
    db.delete_connection(conn_id)
    from . import tools
    tools.reset_client()
    return RedirectResponse(url="/connections", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Course cache browser
# ---------------------------------------------------------------------------

@app.get("/courses", response_class=HTMLResponse)
async def courses_page(request: Request, q: str = ""):
    _ensure_db()
    courses = db.list_cached_courses()
    if q:
        q_lower = q.lower()
        courses = [c for c in courses if q_lower in c.get("title", "").lower()
                   or q_lower in c.get("frappe_course_id", "").lower()]
    return templates.TemplateResponse(request, "courses.html", {
        "courses": courses,
        "q": q,
        "flashes": _get_flashes(request),
    })


@app.get("/courses/import", response_class=HTMLResponse)
async def import_form(request: Request):
    _ensure_db()
    active = db.get_active_connection()
    return templates.TemplateResponse(request, "import.html", {
        "active": active,
        "flashes": _get_flashes(request),
    })


@app.post("/courses/import")
async def import_submit(request: Request, course_slug: str = Form(...)):
    _ensure_db()
    from . import tools
    try:
        result = tools.import_course_from_frappe(course_slug)
        if result.get("ok"):
            _flash(request, f"Imported '{course_slug}' to cache.", "success")
        else:
            _flash(request, f"Import failed: {result.get('error', 'unknown')}", "error")
    except Exception as e:
        _flash(request, f"Import failed: {e}", "error")
    return RedirectResponse(url="/courses", status_code=303)


@app.get("/courses/{course_id}", response_class=HTMLResponse)
async def course_detail(request: Request, course_id: int):
    _ensure_db()
    course = db.get_cached_course(course_id)
    if not course:
        _flash(request, "Course not found in cache.", "error")
        return RedirectResponse(url="/courses", status_code=303)

    # Parse spec_json for display
    spec: dict[str, Any] = {}
    if course.get("spec_json"):
        try:
            spec = json.loads(course["spec_json"])
        except json.JSONDecodeError:
            pass

    return templates.TemplateResponse(request, "course_detail.html", {
        "course": course,
        "spec": spec,
        "spec_json_pretty": json.dumps(spec, indent=2, ensure_ascii=False) if spec else "",
        "flashes": _get_flashes(request),
    })


@app.post("/courses/{course_id}/reupload")
async def reupload_course(
    request: Request,
    course_id: int,
    connection_name: str = Form(""),
):
    _ensure_db()
    from . import tools
    try:
        result = tools.reupload_course(course_id, connection_name)
        if result.get("ok"):
            _flash(request, f"Re-uploaded as '{result.get('course', '?')}'.", "success")
        else:
            _flash(request, f"Re-upload failed: {result.get('error', 'unknown')}", "error")
    except Exception as e:
        _flash(request, f"Re-upload failed: {e}", "error")
    return RedirectResponse(url=f"/courses/{course_id}", status_code=303)


@app.post("/courses/{course_id}/delete")
async def delete_cached_course(course_id: int):
    _ensure_db()
    db.delete_cached_course(course_id)
    return RedirectResponse(url="/courses", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Operation log
# ---------------------------------------------------------------------------

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, limit: int = 100):
    _ensure_db()
    logs = db.list_operations(limit)
    return templates.TemplateResponse(request, "logs.html", {
        "logs": logs,
        "flashes": _get_flashes(request),
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    _ensure_db()
    active = db.get_active_connection()
    return {
        "status": "ok",
        "active_connection": active["name"] if active else None,
        "db_path": str(db._db_path()),
    }
