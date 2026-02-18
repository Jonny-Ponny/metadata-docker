# ---- Stage 1: Build the Svelte frontend ----
FROM node:22 AS frontend-builder
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend source and build
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Build the Flask backend and include frontend ----
FROM python:3.9-slim
WORKDIR /app

# Copy backend requirements and install
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Copy the Flask application code
COPY backend/ .

# Create the static folder and copy the built frontend into it
RUN mkdir -p static
COPY --from=frontend-builder /app/frontend/dist/ ./static/

# Expose the port
EXPOSE $CONTAINER_PORT

# Run the Flask app
CMD gunicorn --bind 0.0.0.0:$CONTAINER_PORT --workers 1 --threads 8 app:app