# Multi-stage build for React frontend

# Stage 1: Build
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Stage 2: Production with nginx - OpenShift compatible
FROM nginxinc/nginx-unprivileged:alpine

# Switch to root to set permissions
USER 0

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config as TEMPLATE (with ${BACKEND_URL} placeholder)
COPY nginx-custom.conf /tmp/nginx.conf.template

# Copy entrypoint script to /tmp (better permissions for OpenShift)
COPY docker-entrypoint.sh /tmp/docker-entrypoint.sh

# Fix permissions for OpenShift
RUN chmod -R g+rwX /tmp /usr/share/nginx/html && \
    chown -R nginx:0 /tmp /usr/share/nginx/html && \
    chmod +x /tmp/docker-entrypoint.sh

# Switch back to non-root user
USER nginx

# Expose port 8080
EXPOSE 8080

# ENTRYPOINT runs at container startup, reads BACKEND_URL env var and generates nginx.conf
ENTRYPOINT ["/bin/sh", "/tmp/docker-entrypoint.sh"]
