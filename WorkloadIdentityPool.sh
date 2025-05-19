#!/bin/bash
set -e  # Stop on first error

# Set your variables
PROJECT_ID="dotted-music-459906-t6"
REPO="LeoPrasanna/job_scraper"

# Get the project number - this is needed for the IAM binding
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
echo "Project Number: ${PROJECT_NUMBER}"

# Generate unique names with timestamp
TIMESTAMP=$(date +%s)
POOL_NAME="github-actions-pool-${TIMESTAMP}"
PROVIDER_NAME="github-provider-${TIMESTAMP}"

echo "Using dynamically generated names:"
echo "Pool name: ${POOL_NAME}"
echo "Provider name: ${PROVIDER_NAME}"

# Clean up previous service account if it exists
echo "Cleaning up previous service account..."
gcloud iam service-accounts delete github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --project=${PROJECT_ID} \
  --quiet 2>/dev/null || true

# Step 1: Create Workload Identity Pool with dynamic name
echo "Creating Workload Identity Pool..."
gcloud iam workload-identity-pools create ${POOL_NAME} \
  --project=${PROJECT_ID} \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Step 2: Create Workload Identity Provider with dynamic name
echo "Creating Workload Identity Provider..."
gcloud iam workload-identity-pools providers create-oidc ${PROVIDER_NAME} \
  --project=${PROJECT_ID} \
  --location="global" \
  --workload-identity-pool=${POOL_NAME} \
  --display-name="GitHub Actions Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-condition="attribute.repository=='${REPO}'"

# Step 3: Create Service Account
echo "Creating Service Account..."
gcloud iam service-accounts create github-actions-sa \
  --project=${PROJECT_ID} \
  --description="Service Account for GitHub Actions" \
  --display-name="GitHub Actions Service Account"

# Step 4: Enable necessary APIs
echo "Enabling APIs..."
gcloud services enable sheets.googleapis.com drive.googleapis.com iam.googleapis.com iamcredentials.googleapis.com --project=${PROJECT_ID}

# Step 5: Add IAM binding to allow GitHub to impersonate service account
echo "Adding IAM binding..."
MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${REPO}"
echo "Using member: ${MEMBER}"

gcloud iam service-accounts add-iam-policy-binding github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --project=${PROJECT_ID} \
  --role="roles/iam.workloadIdentityUser" \
  --member="${MEMBER}"

# Step 6: Grant necessary permissions to service account
echo "Granting service account permissions..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/editor"

# Step 7: Get provider ID for GitHub Actions
echo "Getting provider ID..."
WORKLOAD_IDENTITY_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/providers/${PROVIDER_NAME}"
SERVICE_ACCOUNT="github-actions-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "================================================"
echo "Setup complete! Use these values in GitHub:"
echo "================================================"
echo "WORKLOAD_IDENTITY_PROVIDER: ${WORKLOAD_IDENTITY_PROVIDER}"
echo "GCP_SERVICE_ACCOUNT: ${SERVICE_ACCOUNT}"
echo "================================================"