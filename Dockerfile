# ---- Stage 1: Build the Svelte frontend ----
# FROM node:current-alpine3.23 AS frontend-builder
# Changed for armv7 support
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend source and build
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Build the Flask backend and include frontend ----
FROM python:3.12-alpine
WORKDIR /app

# Install shadow (for user/group management) and gosu
# Use --no-cache to keep image size small
RUN apk add --no-cache shadow gosu bash

# Copy backend requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask application code
COPY backend/ .

# Create the static folder and copy the built frontend into it
RUN mkdir -p static
COPY --from=frontend-builder /app/frontend/dist/ ./static/

# Create directories that might need permission changes. /app/addons exists in
# the image so the app can start without an addons mount and never needs to
# create it under the root-owned application directory.
RUN mkdir -p /music /logs /app/addons

# Commit this image was built from. The release workflow passes GITHUB_SHA;
# /api/version exposes it so a running container can be matched against the
# signed build-provenance attestation.
ARG GIT_SHA=unknown
ENV APP_GIT_SHA=$GIT_SHA

# Run as an unprivileged user by default. Override PUID/PGID to match your host
# user, or set both to 0 to keep running as root (not recommended).
ENV PUID=1000 \
    PGID=1000 \
    CONTAINER_PORT=5000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Verify size is NOT 0
RUN ls -la /entrypoint.sh

EXPOSE $CONTAINER_PORT

# The app must answer its unauthenticated health endpoint for the container to
# be considered healthy. Give addon dependency installs time to finish at boot.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${CONTAINER_PORT:-5000}/api/ping" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
