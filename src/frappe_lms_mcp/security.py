"""Fail-closed remote authentication; log no URLs, queries, bodies or credentials."""
import hmac
import logging
import os
from urllib.parse import parse_qs
from starlette.responses import JSONResponse


def read_only():
    value = os.getenv('MCP_READ_ONLY', '1')
    if value not in {'0', '1'}:
        raise ValueError('MCP_READ_ONLY must be 0 or 1')
    return value == '1'


class AuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.token = os.getenv('MCP_AUTH_TOKEN', '')
        if len(self.token.encode()) < 32:
            raise ValueError('MCP_AUTH_TOKEN must contain at least 32 bytes')
        self.allow_query = os.getenv('MCP_ALLOW_QUERY_TOKEN', '0') == '1'

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Public liveness only. All MCP methods and SSE messages require auth.
        public = scope['path'] == '/health' and scope['method'] == 'GET'
        headers = dict(scope.get('headers', []))
        header = headers.get(b'authorization', b'').decode('latin1')
        candidate = header[7:] if header.lower().startswith('bearer ') else ''
        if not header and self.allow_query:
            values = parse_qs(scope.get('query_string', b'').decode('latin1')).get('token', [])
            candidate = values[0] if len(values) == 1 else ''
        valid = hmac.compare_digest(candidate.encode(), self.token.encode())
        status = 500
        async def safe_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)
        try:
            if not public and not valid:
                return await JSONResponse({'error': 'Unauthorized'}, status_code=401,
                    headers={'WWW-Authenticate': 'Bearer'})(scope, receive, safe_send)
            return await self.app(scope, receive, safe_send)
        finally:
            logging.getLogger('mcp.access').info('request method=%s status=%s', scope['method'], status)
