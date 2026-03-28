#!/bin/bash
set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
REPO_NAME="lobster-army"
TAG="latest"

echo "Deploying to Project: $PROJECT_ID in $REGION"

# 1. Build
echo "Building Docker Image..."
docker build -t gcr.io/$PROJECT_ID/$REPO_NAME:$TAG .

# 2. Push
echo "Pushing to GCR..."
docker push gcr.io/$PROJECT_ID/$REPO_NAME:$TAG

# 3. Deploy Gateway
echo "Deploying Gateway..."
gcloud run deploy $REPO_NAME-gateway \
  --image gcr.io/$PROJECT_ID/$REPO_NAME:$TAG \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "SERVICE_ROLE=gateway"

# 4. Deploy Runtime
echo "Deploying Runtime..."
gcloud run deploy $REPO_NAME-runtime \
  --image gcr.io/$PROJECT_ID/$REPO_NAME:$TAG \
  --region $REGION \
  --platform managed \
  --no-allow-unauthenticated \
  --set-env-vars "SERVICE_ROLE=runtime" \
  --command "python" \
  --args "-m,runtime.app"

echo "Deployment Complete."
