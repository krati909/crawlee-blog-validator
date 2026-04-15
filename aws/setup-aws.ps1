# =============================================================================
# aws/setup-aws.ps1
# One-time AWS setup: ECR repo + IAM role + build/push image + create Lambda
#
# Run from the repo root:  .\aws\setup-aws.ps1
# For subsequent code changes use .\aws\deploy.ps1
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - Environment variables set:
#       $env:AWS_ACCOUNT_ID = "123456789012"
#       $env:AWS_REGION     = "us-east-1"
# =============================================================================

$ErrorActionPreference = "Stop"

# Always run from repo root so Docker context and file paths are correct
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
$POLICY_FILE = Join-Path $PSScriptRoot "policy.json"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Crawlee Blog Validator - One-time AWS Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Account : $($env:AWS_ACCOUNT_ID)"
Write-Host "  Region  : $($env:AWS_REGION)"
Write-Host "  Image   : $IMAGE_URI"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Create ECR repository
# ---------------------------------------------------------------------------
Write-Host "[1/5] Creating ECR repository..." -ForegroundColor Yellow
$repoExists = aws ecr describe-repositories `
    --repository-names crawlee-blog-validator `
    --region $env:AWS_REGION 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Already exists, skipping." -ForegroundColor Gray
} else {
    aws ecr create-repository `
        --repository-name crawlee-blog-validator `
        --region $env:AWS_REGION | Out-Null
    Write-Host "      Created." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 2: Create IAM execution role
# ---------------------------------------------------------------------------
Write-Host "[2/5] Creating IAM execution role..." -ForegroundColor Yellow
$roleExists = aws iam get-role --role-name crawlee-blog-validator-role 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Already exists, skipping." -ForegroundColor Gray
} else {
    aws iam create-role `
        --role-name crawlee-blog-validator-role `
        --assume-role-policy-document "file://$POLICY_FILE" | Out-Null

    aws iam attach-role-policy `
        --role-name crawlee-blog-validator-role `
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole | Out-Null

    Write-Host "      Created and policy attached." -ForegroundColor Green
    Write-Host "      Waiting 10s for IAM role to propagate..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
}

# ---------------------------------------------------------------------------
# Step 3: Build Docker image
# ---------------------------------------------------------------------------
Write-Host "[3/5] Building Docker image (linux/amd64)..." -ForegroundColor Yellow
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
# Step 4: Push image to ECR
# ---------------------------------------------------------------------------
Write-Host "[4/5] Pushing image to ECR..." -ForegroundColor Yellow
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
# Step 5: Create Lambda function
# ---------------------------------------------------------------------------
Write-Host "[5/5] Creating Lambda function..." -ForegroundColor Yellow
$lambdaExists = aws lambda get-function `
    --function-name crawlee-blog-validator `
    --region $env:AWS_REGION 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Already exists. Run .\aws\deploy.ps1 to update it." -ForegroundColor Gray
} else {
    aws lambda create-function `
        --function-name crawlee-blog-validator `
        --package-type Image `
        --code "ImageUri=${IMAGE_URI}:latest" `
        --role "arn:aws:iam::$($env:AWS_ACCOUNT_ID):role/crawlee-blog-validator-role" `
        --memory-size 1024 `
        --timeout 300 `
        --environment "Variables={CRAWLEE_STORAGE_DIR=/tmp/storage,REPORT_OUTPUT_DIR=/tmp/reports}" `
        --region $env:AWS_REGION | Out-Null

    Write-Host "      Waiting for function to become active..." -ForegroundColor Gray
    aws lambda wait function-active `
        --function-name crawlee-blog-validator `
        --region $env:AWS_REGION

    Write-Host "      Lambda function created and active." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To invoke the Lambda:" -ForegroundColor White
Write-Host "    .\aws\invoke.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  After making code changes, redeploy with:" -ForegroundColor White
Write-Host "    .\aws\deploy.ps1" -ForegroundColor Yellow
Write-Host ""
