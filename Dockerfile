# syntax=docker/dockerfile:1

# Base images are pinned by digest so the same Dockerfile always builds from
# the same inputs. Dependabot refreshes the digests (see .github/dependabot.yml).
# ---- Stage 1: Build the Svelte frontend ----
# The frontend output is platform-independent, so build it once on the host
# architecture instead of under QEMU for every target. Node 24+ publishes no
# linux/arm/v7 image, so the builder stays on 22 (still armv7-capable and
# supported until April 2027); the final stage keeps targeting armv7. The
# Dependabot config ignores Node major updates for this reason.
FROM --platform=$BUILDPLATFORM node:23-bookworm-slim@sha256:86191b94d2a163be41f3dc7fe5e5fcaca8ba2f1be7275d98a06343483c17414a AS frontend-builder
WORKDIR /app/frontend

# Install from the lockfile so the image matches CI and the repository
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source and build
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Build the Flask backend and include frontend ----
FROM python:3.12-alpine@sha256:5789aa194f757888f41fa3d48e14b6feaa1b57c0af0b56fcb1372d6474d3bff0
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
