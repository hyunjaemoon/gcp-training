#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load root .env (optional: GCP_PROJECT_ID, GCP_REGION, CLOUD_RUN_SERVICE)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Load Firebase config from ui/.env (required for Vite build)
if [ -f ui/.env ]; then
  set -a
  source ui/.env
  set +a
else
  echo "Error: ui/.env not found. Create it with VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID"
  exit 1
fi

# Configurable via .env (GCP_PROJECT_ID, GCP_REGION, CLOUD_RUN_SERVICE), ui/.env, or defaults
PROJECT_ID="${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${VITE_FIREBASE_PROJECT_ID}}}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-gcp-training}"

if [ -z "$PROJECT_ID" ]; then
  echo "Error: GCP project ID required. Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT in .env, or VITE_FIREBASE_PROJECT_ID in ui/.env"
  exit 1
fi

if [ -z "$REGION" ]; then
  echo "Error: GCP region required. Set GCP_REGION in .env"
  exit 1
fi

if [ -z "$SERVICE_NAME" ]; then
  echo "Error: Cloud Run service name required. Set CLOUD_RUN_SERVICE in .env"
  exit 1
fi

echo "Deploying to Cloud Run:"
echo "  Project:  $PROJECT_ID"
echo "  Region:   $REGION"
echo "  Service:  $SERVICE_NAME"
echo ""

# Ensure gcloud is configured for this project
gcloud config set project "$PROJECT_ID"

# Enable required APIs (idempotent; no-op if already enabled)
echo "Ensuring Cloud Build and Cloud Run APIs are enabled..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com --project="$PROJECT_ID"

# Ensure Artifact Registry repo exists (Cloud Run source deploy creates this automatically; we need it for manual builds)
if ! gcloud artifacts repositories describe cloud-run-source-deploy --location="$REGION" &>/dev/null; then
  echo "Creating Artifact Registry repository cloud-run-source-deploy in $REGION..."
  gcloud artifacts repositories create cloud-run-source-deploy \
    --repository-format=docker \
    --location="$REGION" \
    --description="Cloud Run source deploy images"
fi

# Deploy: Cloud Build builds the image (with Docker --build-arg), pushes to Artifact Registry, deploys to Cloud Run
# Uses cloudbuild.yaml because gcloud run deploy --source does not support --build-arg for Dockerfiles
# --region ensures build runs in same region as Cloud Run and uses regional bucket (avoids NOT_FOUND)
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --region="$REGION" \
  --substitutions="_VITE_FIREBASE_API_KEY=${VITE_FIREBASE_API_KEY},_VITE_FIREBASE_AUTH_DOMAIN=${VITE_FIREBASE_AUTH_DOMAIN},_VITE_FIREBASE_PROJECT_ID=${VITE_FIREBASE_PROJECT_ID},_SERVICE_NAME=${SERVICE_NAME},_REGION=${REGION}" \
  --project="$PROJECT_ID"

echo ""
echo "Allowing unauthenticated access (Cloud Build may not have permission to set this)..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project="$PROJECT_ID"

echo ""
echo "Deployment complete. Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')
echo "Your app is live at: $SERVICE_URL"
echo ""
echo "Note: Add this domain to Firebase Auth > Settings > Authorized domains for sign-in to work."
