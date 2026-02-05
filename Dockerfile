# ---- Stage 1: Build the React frontend ----
FROM node:22-alpine AS ui-builder

WORKDIR /app/ui

# Install dependencies first (better layer caching)
COPY ui/package.json ui/package-lock.json ./
RUN npm ci

# Copy source and build
COPY ui/ ./
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ENV VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY
ENV VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN
ENV VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.13-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY server.py agent.py ./

# Copy built React app from stage 1
COPY --from=ui-builder /app/ui/dist ./ui/dist

# Cloud Run sets the PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# Use gunicorn for production; single worker with threads is recommended for Cloud Run.
# --timeout 0 disables worker timeout since Cloud Run manages request deadlines.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 server:app
