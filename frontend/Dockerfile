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

# Copy custom nginx configuration
COPY nginx-custom.conf /tmp/nginx.conf

# Fix permissions for OpenShift
RUN chmod -R g+rwX /tmp /usr/share/nginx/html && \
    chown -R nginx:0 /tmp /usr/share/nginx/html

# Switch back to non-root user
USER nginx

# Expose port 8080
EXPOSE 8080

# Start nginx with custom config
CMD ["nginx", "-c", "/tmp/nginx.conf", "-g", "daemon off;"]
