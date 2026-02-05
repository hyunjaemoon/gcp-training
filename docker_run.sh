#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load Firebase config from ui/.env (required for Vite build)
if [ -f ui/.env ]; then
  set -a
  source ui/.env
  set +a
else
  echo "Error: ui/.env not found. Create it with VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID"
  exit 1
fi

# Build the image with Firebase config as build args
docker build -t gcp-training \
  --build-arg VITE_FIREBASE_API_KEY="${VITE_FIREBASE_API_KEY}" \
  --build-arg VITE_FIREBASE_AUTH_DOMAIN="${VITE_FIREBASE_AUTH_DOMAIN}" \
  --build-arg VITE_FIREBASE_PROJECT_ID="${VITE_FIREBASE_PROJECT_ID}" \
  .

# Run the container
# Mount gcloud credentials so firebase-admin and Vertex AI can authenticate locally.
# Run `gcloud auth application-default login` first if you haven't.
# GOOGLE_CLOUD_PROJECT is required for firebase-admin token verification and Vertex AI.
echo "Starting container. Open http://localhost:8080"
docker run -p 8080:8080 \
  -e GOOGLE_CLOUD_PROJECT="${VITE_FIREBASE_PROJECT_ID}" \
  -v "${HOME}/.config/gcloud:/root/.config/gcloud:ro" \
  gcp-training
