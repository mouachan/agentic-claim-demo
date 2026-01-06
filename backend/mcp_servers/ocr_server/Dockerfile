# MCP OCR Server Dockerfile - EasyOCR Embedded
FROM registry.access.redhat.com/ubi9/python-311:latest

USER 0

# Install system dependencies for EasyOCR and PDF processing
# - poppler-utils: PDF to image conversion (pdf2image dependency)
# - mesa-libGL: OpenGL library for OpenCV (EasyOCR dependency)
# - libgomp: OpenMP library for parallel processing
RUN dnf install -y \
    poppler-utils \
    mesa-libGL \
    libgomp \
    && dnf clean all

# Note: EasyOCR is embedded - all OCR processing happens in this container
# Much faster than external Qwen-VL (2-4s vs 30+s)

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
# CRITICAL: Uninstall any pre-existing NumPy to prevent version conflicts
# The base UBI9 Python image may have NumPy 2.x which is incompatible with PyTorch/OpenCV
RUN pip uninstall -y numpy || true
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
