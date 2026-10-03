"""Frappe REST API client for the MCP server.

Wraps the Frappe /api/resource and /api/method endpoints with session
authentication, providing a small typed surface for the MCP tools.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote, urlsplit
from .security import read_only
from typing import Any

import httpx

# Silence httpx INFO-level logs (e.g. "HTTP Request: POST ...") that would
# leak into the MCP stdio transport as noise and confuse clients.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class FrappeAPIError(Exception):
    """Raised when the Frappe API returns an error response."""

    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FrappeClient:
    """Stateful Frappe REST client supporting two auth modes.

    **Token auth (recommended for MCP):**  pass ``api_key`` and ``api_secret``.
    Every request carries ``Authorization: token <key>:<secret>``.  No session
    login is needed — the token is stateless and never expires.

    **Session auth (fallback):**  pass ``username`` and ``password``.  The
    client logs in via ``/api/method/login`` and stores the session cookie.

    Environment-variable fallbacks (used when a parameter is ``None``):

    - ``FRAPPE_URL``       — base URL (default ``http://localhost:8000``)
    - ``FRAPPE_SITE``      — site name (default ``lms.localhost``)
    - ``FRAPPE_API_KEY``   — API key for token auth
    - ``FRAPPE_API_SECRET``— API secret for token auth
    - ``FRAPPE_USERNAME``  — login user (default ``Administrator``)
    - ``FRAPPE_PASSWORD``  — login password (required for session auth)
    """

    def __init__(
        self,
        url: str | None = None,
        site: str | None = None,
        username: str | None = None,
        password: str | None = None,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (url or os.environ.get("FRAPPE_URL", "http://localhost:8000")).rstrip("/")
        self.site = site or os.environ.get("FRAPPE_SITE", "lms.localhost")

        # Token auth takes precedence if either key/secret is provided
        # (explicitly or via env).
        self.api_key = api_key or os.environ.get("FRAPPE_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("FRAPPE_API_SECRET", "")
        self._use_token = bool(self.api_key and self.api_secret)

        self.username = ""
        self.password = ""
        if not self._use_token:
            raise FrappeAPIError("FRAPPE_API_KEY and FRAPPE_API_SECRET are required")
        parts = urlsplit(self.base_url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path:
            raise FrappeAPIError("FRAPPE_URL must be an HTTPS origin without credentials or path")
        self._client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
        self._logged_in = self._use_token  # token auth needs no login

    # ------------------------------------------------------------------ #
    #  Session management
    # ------------------------------------------------------------------ #

    def login(self) -> None:
        """Authenticate via username/password and store the session cookie.

        Skipped automatically when token auth is in use.
        """
        if self._use_token:
            return
        resp = self._client.post(
            f"{self.base_url}/api/method/login",
            data={"usr": self.username, "pwd": self.password},
            headers={"X-Frappe-Site-Name": self.site},
        )
        if resp.status_code != 200:
            raise FrappeAPIError(
                f"Login failed ({resp.status_code}): {resp.text}",
                resp.status_code,
            )
        # A 200 response means the session cookie was set successfully.
        # Frappe may return {"message": "Logged In"} for Desk users or
        # {"message": "No App", "home_page": "/lms", "full_name": "..."}
        # for Website/System users without a default desk app — both are
        # successful logins as long as the session cookie is present.
        if not resp.cookies:
            raise FrappeAPIError(f"Login failed (no session cookie): {resp.text}")
        self._logged_in = True

    def _ensure_session(self) -> None:
        if not self._logged_in:
            self.login()

    def get_current_user(self) -> str:
        """Return the email of the currently logged-in user."""
        self._ensure_session()
        resp = self._client.get(
            f"{self.base_url}/api/method/frappe.auth.get_logged_user",
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise FrappeAPIError(
                f"Failed to get current user ({resp.status_code}): {resp.text}",
                resp.status_code,
            )
        return resp.json().get("message", "")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Frappe-Site-Name": self.site,
            "Accept": "application/json",
        }
        if self._use_token:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        return headers

    # ------------------------------------------------------------------ #
    #  Low-level request helpers
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        data: dict | None = None,
    ) -> Any:
        if read_only() and (method != "GET" or not path.startswith("/api/resource/")):
            raise FrappeAPIError("Read-only mode: request denied")
        self._ensure_session()
        url = f"{self.base_url}{path}"
        resp = self._client.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            headers=self._headers(),
        )
        if resp.status_code >= 300:
            self._raise_error(resp)
        # Some endpoints return empty body on success
        if not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    def _raise_error(self, resp: httpx.Response) -> None:
        raise FrappeAPIError(f"Frappe request failed (HTTP {resp.status_code})", resp.status_code)

    # ------------------------------------------------------------------ #
    #  Resource CRUD  (frappe.client.* via /api/resource)
    # ------------------------------------------------------------------ #

    def get_doc(self, doctype: str, name: str) -> dict:
        """Fetch a single document by doctype + name."""
        return self._request("GET", f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}")

    def get_value(
        self,
        doctype: str,
        name: str,
        fields: str | list[str] | None = None,
    ) -> dict:
        """Fetch specific fields of a document."""
        params: dict = {}
        if fields:
            params["fields"] = fields if isinstance(fields, str) else json_dumps(fields)
        resp = self._request(
            "GET", f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}", params=params
        )
        return resp.get("data", resp)

    def insert(self, doctype: str, data: dict) -> dict:
        """Create a new document.  Returns the created doc."""
        resp = self._request(
            "POST", f"/api/resource/{quote(doctype, safe='')}", json=data
        )
        return resp.get("data", resp)

    def update(self, doctype: str, name: str, data: dict) -> dict:
        """Update an existing document."""
        resp = self._request(
            "PUT", f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}", json=data
        )
        return resp.get("data", resp)

    def delete(self, doctype: str, name: str) -> None:
        """Delete a document."""
        self._request("DELETE", f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}")

    def get_list(
        self,
        doctype: str,
        *,
        fields: list[str] | None = None,
        filters: list | dict | None = None,
        limit_page_length: int = 100,
        limit_start: int = 0,
        order_by: str | None = None,
    ) -> list[dict]:
        """List documents matching filters."""
        params: dict = {
            "limit_page_length": max(1, min(200, limit_page_length)),
            "limit_start": limit_start,
        }
        if fields:
            params["fields"] = json_dumps(fields)
        if filters:
            params["filters"] = json_dumps(filters)
        if order_by:
            params["order_by"] = order_by
        resp = self._request("GET", f"/api/resource/{quote(doctype, safe='')}", params=params)
        return resp.get("data", resp)

    # ------------------------------------------------------------------ #
    #  Whitelisted method calls  (/api/method/<method>)
    # ------------------------------------------------------------------ #

    def call_method(self, method: str, **kwargs: Any) -> Any:
        """Call a whitelisted Frappe method via POST with JSON kwargs.

        ``method`` is the dotted path, e.g. ``"lms.api.upsert_chapter"``.
        Keyword arguments are sent as JSON in the request body.
        """
        if read_only():
            raise FrappeAPIError("Read-only mode: method calls denied")
        self._ensure_session()
        url = f"{self.base_url}/api/method/{method}"
        resp = self._client.post(url, json=kwargs, headers=self._headers())
        if resp.status_code >= 300:
            self._raise_error(resp)
        if not resp.content:
            return None
        data = resp.json()
        # Frappe wraps whitelisted results under "message"
        if isinstance(data, dict) and "message" in data and len(data) <= 3:
            return data["message"]
        return data

    def call_method_args(self, method: str, args: list) -> Any:
        """Call a whitelisted Frappe method with positional args.

        Frappe's REST ``/api/method/<method>`` endpoint maps query/form
        parameters to function arguments by **name**, not by position.
        Since we cannot introspect the server-side function signature from
        the client, we use Frappe's ``runservermethod`` convention: send
        the args as a JSON array in the ``args`` form field.  Frappe will
        unpack them positionally.

        If that fails (some endpoints don't support the ``args`` convention),
        fall back to sending each value as ``cmd``-less query params.
        """
        if read_only():
            raise FrappeAPIError("Read-only mode: method calls denied")
        self._ensure_session()
        url = f"{self.base_url}/api/method/{method}"
        # Try the standard Frappe positional-args convention first:
        # POST with form data {"args": "[val1, val2, ...]"}
        resp = self._client.post(
            url, data={"args": json_dumps(args)}, headers=self._headers()
        )
        if resp.status_code >= 300:
            self._raise_error(resp)
        if not resp.content:
            return None
        data = resp.json()
        if isinstance(data, dict) and "message" in data and len(data) <= 3:
            return data["message"]
        return data

    # ------------------------------------------------------------------ #
    #  Convenience
    # ------------------------------------------------------------------ #

    def exists(self, doctype: str, name: str) -> bool:
        """Check whether a document exists."""
        try:
            self.get_value(doctype, name, ["name"])
            return True
        except FrappeAPIError:
            return False

    def generate_api_keys(self, user: str = "") -> tuple[str, str]:
        """Generate (or regenerate) API key/secret for a user.

        Requires the current session to have write access to the User doctype
        (e.g. Administrator).  Returns ``(api_key, api_secret)``.

        Frappe hashes the api_secret in the database, so this is the only
        time the plaintext secret is available — the caller must store it.
        """
        self._ensure_session()
        target = user or self.username
        # generate_keys is a whitelisted method on the User doctype
        self.call_method(
            "frappe.core.doctype.user.user.generate_keys", user=target
        )
        # Fetch the generated values (api_secret is only visible right after generation)
        doc = self.get_value("User", target, ["api_key", "api_secret"])
        api_key = doc.get("api_key", "")
        api_secret = doc.get("api_secret", "")
        if not api_key or not api_secret:
            raise FrappeAPIError(
                "Failed to retrieve API key/secret after generation. "
                "The user may lack permission to read these fields."
            )
        return api_key, api_secret

    def close(self) -> None:
        self._client.close()
        self._logged_in = False

    # ------------------------------------------------------------------ #
    #  Static helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def login_and_generate_keys(
        url: str,
        site: str,
        username: str,
        password: str,
    ) -> tuple[str, str | None, str | None, str]:
        """One-shot: login with username/password, generate API keys if possible.

        Returns ``(api_key, api_secret, user_email)`` where ``api_key`` and
        ``api_secret`` may be ``None`` if the user lacks the System Manager
        role needed to call ``generate_keys``.  In that case the caller should
        fall back to session-based auth (storing the password).

        The temporary session client is closed afterwards.
        """
        client = FrappeClient(
            url=url, site=site, username=username, password=password
        )
        client.login()
        try:
            # Verify who we are
            user_email = client.get_current_user()
            try:
                api_key, api_secret = client.generate_api_keys(user_email)
                return api_key, api_secret, user_email
            except FrappeAPIError:
                # User lacks permission to generate API keys (not System Manager).
                # Fall back to session auth — caller should store the password.
                return None, None, user_email
        finally:
            client.close()


def json_dumps(obj: Any) -> str:
    """Serialise to a compact JSON string (for Frappe query params)."""
    import json

    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
