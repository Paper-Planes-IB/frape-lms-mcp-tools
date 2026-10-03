FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FRAPPE_LMS_NO_DASHBOARD=1 FRAPPE_LMS_DB_PATH=/data/frappe_lms.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home mcp && mkdir /data && chown mcp:mcp /data
USER mcp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["frappe-lms-mcp"]
