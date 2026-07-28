"""Standalone entry point for the Frappe LMS MCP dashboard.

Run the web dashboard without the MCP server::

    frappe-lms-dashboard
    # or: python -m frappe_lms_mcp.dashboard_cli

Useful for managing connections and cached courses independently.
"""

from __future__ import annotations

import os

import uvicorn

from . import db
from .dashboard import app


def main() -> None:
    """Run the dashboard server."""
    db.init_db()
    port = int(os.environ.get("FRAPPE_LMS_DASHBOARD_PORT", "8080"))
    print(f"Frappe LMS Dashboard: http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
