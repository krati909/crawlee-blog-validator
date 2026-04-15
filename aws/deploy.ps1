# =============================================================================
# aws/deploy.ps1
# Build image -> push to ECR -> update Lambda function
#
# Run from the repo root:  .\aws\deploy.ps1
# Run this every time you change code.
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - Environment variables set:
#       $env:AWS_ACCOUNT_ID = "123456789012"
#       $env:AWS_REGION     = "us-east-1"
# =============================================================================

$ErrorActionPreference = "Stop"

# Always run from repo root so Docker context is correct
$REPO_ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $REPO_ROOT

# ---------------------------------------------------------------------------
# Validate required env vars
# ---------------------------------------------------------------------------
if (-not $env:AWS_ACCOUNT_ID) {
    Write-Host "[ERROR] `$env:AWS_ACCOUNT_ID is not set." -ForegroundColor Red
    Write-Host "  Run: `$env:AWS_ACCOUNT_ID = '123456789012'" -ForegroundColor Yellow
    exit 1
}
if (-not $env:AWS_REGION) {
    Write-Host "[ERROR] `$env:AWS_REGION is not set." -ForegroundColor Red
    Write-Host "  Run: `$env:AWS_REGION = 'us-east-1'" -ForegroundColor Yellow
    exit 1
}

$IMAGE_URI = "$($env:AWS_ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com/crawlee-blog-validator"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Crawlee Blog Validator - Deploy Update" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Account : $($env:AWS_ACCOUNT_ID)"
Write-Host "  Region  : $($env:AWS_REGION)"
Write-Host "  Image   : $IMAGE_URI"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Build
# ---------------------------------------------------------------------------
Write-Host "[1/3] Building Docker image (linux/amd64)..." -ForegroundColor Yellow
docker buildx build `
    --platform linux/amd64 `
    --provenance=false `
    --load `
    -t crawlee-blog-validator `
    .
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker build failed." -ForegroundColor Red
    exit 1
}
Write-Host "      Build complete." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 2: Push to ECR
# ---------------------------------------------------------------------------
Write-Host "[2/3] Pushing to ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $env:AWS_REGION | `
    docker login --username AWS --password-stdin "$($env:AWS_ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com"

docker tag crawlee-blog-validator:latest "${IMAGE_URI}:latest"
docker push "${IMAGE_URI}:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker push failed." -ForegroundColor Red
    exit 1
}
Write-Host "      Push complete." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 3: Update Lambda
# ---------------------------------------------------------------------------
Write-Host "[3/3] Updating Lambda function..." -ForegroundColor Yellow
aws lambda update-function-code `
    --function-name crawlee-blog-validator `
    --image-uri "${IMAGE_URI}:latest" `
    --region $env:AWS_REGION | Out-Null

Write-Host "      Waiting for update to complete..." -ForegroundColor Gray
aws lambda wait function-updated `
    --function-name crawlee-blog-validator `
    --region $env:AWS_REGION

Write-Host "      Lambda updated successfully." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Deployment complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To invoke:" -ForegroundColor White
Write-Host "    .\aws\invoke.ps1" -ForegroundColor Yellow
Write-Host ""
