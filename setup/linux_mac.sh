#!/bin/bash
# =============================================================================
# Crawlee Blog Validator - One-click setup for Mac/Linux
# Run from the repo root:  bash setup/linux_mac.sh
# After setup:             source .venv/bin/activate && python orchestrator.py
# =============================================================================

set -e

# Always run from repo root regardless of where the script is called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo ""
echo "============================================================"
echo "  Crawlee Blog Validator - Setup"
echo "============================================================"
echo ""

# --- Step 1: Check Python ---
echo "[1/5] Checking Python 3.12+..."
if command -v python3.12 &>/dev/null; then
    echo "      Found: $(python3.12 --version)"
    PYTHON=python3.12
elif command -v python3 &>/dev/null; then
    PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
    if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MINOR" -lt 11 ]; then
        echo "      ERROR: Python 3.11+ required, found $(python3 --version)"
        exit 1
    fi
    echo "      Found: $(python3 --version)"
    PYTHON=python3
else
    echo "      ERROR: Python 3.12+ not found."
    echo "      Install from: https://www.python.org/downloads/"
    exit 1
fi

# --- Step 2: Create virtual environment ---
echo "[2/5] Creating virtual environment..."
if [ -d ".venv" ]; then
    echo "      .venv already exists, skipping."
else
    $PYTHON -m venv .venv
    echo "      Done."
fi

# --- Step 3: Install dependencies ---
echo "[3/5] Installing Python dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
.venv/bin/pip install pytest pytest-asyncio --quiet
echo "      Done."

# --- Step 4: Install Playwright browsers ---
echo "[4/5] Installing Playwright Chromium..."
.venv/bin/playwright install chromium
echo "      Done."

# --- Step 5: Config ---
echo "[5/5] Setting up config..."
mkdir -p reports
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "      Created .env from .env.example"
else
    echo "      .env already exists, skipping."
fi
echo "      Done."

echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "  To run the crawler:"
echo "    source .venv/bin/activate"
echo "    python orchestrator.py"
echo ""
echo "  To run tests:"
echo "    source .venv/bin/activate"
echo "    pytest tests/ -v"
echo ""
echo "  To deploy to AWS Lambda, set these env vars first:"
echo "    export AWS_ACCOUNT_ID='123456789012'"
echo "    export AWS_REGION='us-east-1'"
echo "  Then run (first time only):"
echo "    bash aws/setup-aws.sh"
echo ""
