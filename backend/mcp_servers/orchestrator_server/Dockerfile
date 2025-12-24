# MCP Orchestrator Server Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install PostgreSQL client
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .
COPY prompts.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health/live')" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
