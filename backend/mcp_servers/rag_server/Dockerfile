# MCP RAG Server Dockerfile - Centralized via LlamaStack
# No direct DB access - everything via LlamaStack APIs
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code (only new LlamaStack-based server)
COPY prompts.py .
COPY server.py .
COPY mcp_server.py .

# Create non-root user and fix permissions
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

USER appuser

EXPOSE 8080

# Start MCP server with FastMCP SDK
CMD ["python", "mcp_server.py"]
