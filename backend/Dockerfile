# Backend FastAPI Dockerfile - OpenShift Compatible
FROM registry.access.redhat.com/ubi9/python-311:latest

USER 0

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Fix permissions for OpenShift
RUN chgrp -R 0 /app && \
    chmod -R g=u /app

USER 1001

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
