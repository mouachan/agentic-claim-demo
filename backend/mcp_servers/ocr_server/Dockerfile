# MCP OCR Server Dockerfile - Lightweight (uses qwen-vl-7b)
FROM registry.access.redhat.com/ubi9/python-311:latest

USER 0

# Install poppler-utils for PDF processing (pdf2image dependency)
RUN dnf install -y poppler-utils && \
    dnf clean all

# Note: Using qwen-vl-7b multimodal model deployed on OpenShift AI for OCR
# No ML libraries needed in this container!

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code (only new qwen-vl based server)
COPY prompts.py .
COPY server.py .
COPY mcp_server.py .

# Fix permissions for OpenShift
RUN chgrp -R 0 /app && \
    chmod -R g=u /app

USER 1001

EXPOSE 8080

# Start MCP server with FastMCP SDK
CMD ["python", "mcp_server.py"]
