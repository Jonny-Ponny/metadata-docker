# ---- Stage 1: Build the Svelte frontend ----
FROM node:current-alpine3.23 AS frontend-builder
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm install
RUN npm audit fix

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

# Create directories that might need permission changes
RUN mkdir -p /music /logs

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Verify size is NOT 0
RUN ls -la /entrypoint.sh

EXPOSE 5000
ENTRYPOINT ["/entrypoint.sh"]