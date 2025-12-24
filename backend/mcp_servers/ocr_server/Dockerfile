# MCP OCR Server Dockerfile - OpenShift Compatible
FROM registry.access.redhat.com/ubi9/python-311:latest

USER 0

# Install EPEL, enable CRB, and install Tesseract OCR
RUN dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm && \
    /usr/bin/crb enable && \
    dnf install -y python3-pip gcc python3-devel && \
    dnf clean all && \
    pip install --no-cache-dir pytesseract pillow pdf2image && \
    pip install --no-cache-dir easyocr

# Note: Using EasyOCR instead of Tesseract as it's Python-only and easier in containers

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .
COPY prompts.py .

# Fix permissions for OpenShift
RUN chgrp -R 0 /app && \
    chmod -R g=u /app

USER 1001

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
