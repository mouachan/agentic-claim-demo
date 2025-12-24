# MCP RAG Server Dockerfile - Centralized via LlamaStack
# No direct DB access - everything via LlamaStack APIs
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY mcp_server.py .
COPY rag_logic.py .
COPY prompts.py .
COPY server.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health/live')" || exit 1

# Start MCP server with SSE protocol
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8080"]
