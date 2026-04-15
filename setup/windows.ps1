# =============================================================================
# Crawlee Blog Validator - One-click setup for Windows
# Run from the repo root:  .\setup\windows.ps1
# After setup, just run:   python orchestrator.py
# =============================================================================

$ErrorActionPreference = "Stop"

# Resolve repo root (the folder containing this script's parent)
$REPO_ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $REPO_ROOT

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Crawlee Blog Validator - Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Check Python 3.12 ---
Write-Host "[1/5] Checking Python 3.12..." -ForegroundColor Yellow
$pythonOk = $false
try {
    $version = py -3.12 --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      Found: $version" -ForegroundColor Green
        $pythonOk = $true
    }
} catch {}

if (-not $pythonOk) {
    Write-Host "      ERROR: Python 3.12 not found." -ForegroundColor Red
    Write-Host "      Run: winget install Python.Python.3.12" -ForegroundColor Red
    exit 1
}

# --- Step 2: Create virtual environment ---
Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "      .venv already exists, skipping." -ForegroundColor Gray
} else {
    py -3.12 -m venv .venv
    Write-Host "      Done." -ForegroundColor Green
}

# --- Step 3: Install dependencies ---
Write-Host "[3/5] Installing Python dependencies..." -ForegroundColor Yellow
& ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".venv\Scripts\pip.exe" install -r requirements.txt --quiet
& ".venv\Scripts\pip.exe" install pytest pytest-asyncio --quiet
Write-Host "      Done." -ForegroundColor Green

# --- Step 4: Install Playwright browsers ---
Write-Host "[4/5] Installing Playwright Chromium browser..." -ForegroundColor Yellow
& ".venv\Scripts\playwright.exe" install chromium
Write-Host "      Done." -ForegroundColor Green

# --- Step 5: Create reports directory and .env ---
Write-Host "[5/5] Setting up config..." -ForegroundColor Yellow
if (-not (Test-Path "reports")) {
    New-Item -ItemType Directory -Path "reports" | Out-Null
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "      Created .env from .env.example" -ForegroundColor Gray
} else {
    Write-Host "      .env already exists, skipping." -ForegroundColor Gray
}
Write-Host "      Done." -ForegroundColor Green

# --- Done ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To run the crawler:" -ForegroundColor White
Write-Host "    .venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "    python orchestrator.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To run tests:" -ForegroundColor White
Write-Host "    .venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "    pytest tests/ -v" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To deploy to AWS Lambda, set these env vars first:" -ForegroundColor White
Write-Host "    `$env:AWS_ACCOUNT_ID = '123456789012'" -ForegroundColor Yellow
Write-Host "    `$env:AWS_REGION     = 'us-east-1'" -ForegroundColor Yellow
Write-Host "  Then run (first time only):" -ForegroundColor White
Write-Host "    .\aws\setup-aws.ps1" -ForegroundColor Yellow
Write-Host "  For subsequent deploys:" -ForegroundColor White
Write-Host "    .\aws\deploy.ps1" -ForegroundColor Yellow
Write-Host ""
