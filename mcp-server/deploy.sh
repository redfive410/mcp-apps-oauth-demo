#!/bin/bash

set -e

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION=us-west1
SERVICE_NAME=${SERVICE_NAME:-"mcp-apps-oauth-demo-rs"}
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Starting deployment to Cloud Run..."
echo "Project ID: ${PROJECT_ID}"
echo "Service Name: ${SERVICE_NAME}"
echo "Region: ${REGION}"

# Authenticate Docker with gcloud
echo "🔐 Configuring Docker authentication..."
gcloud auth configure-docker gcr.io --quiet

# Build the Docker image for linux/amd64 platform
echo "📦 Building Docker image..."
docker build --platform linux/amd64 -t ${IMAGE_NAME} .

# Push the image to Google Container Registry
echo "⬆️ Pushing image to Container Registry..."
docker push ${IMAGE_NAME}


# Deploy to Cloud Run
echo "🌟 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --port 8001 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --timeout 300 \
    --allow-unauthenticated \
    --project ${PROJECT_ID}

# Get the actual service URL
echo "🔍 Getting service URL..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --format="value(status.url)")

echo "📝 Updating service with correct SERVER_URL and AUTH_SERVER_URL..."
gcloud run services update ${SERVICE_NAME} \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --set-env-vars MCP_RESOURCE_SERVER_URL=${SERVICE_URL}/mcp,MCP_RESOURCE_AUTH_SERVER_URL=https://mcp-apps-oauth-demo-as-4vohcegqpq-uw.a.run.app

echo "✅ Deployment complete!"
echo "🔗 Service URL: ${SERVICE_URL}"
