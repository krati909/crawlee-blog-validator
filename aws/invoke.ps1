# =============================================================================
# aws/invoke.ps1
# Invoke the deployed Lambda function and print the result.
#
# Usage:
#   .\aws\invoke.ps1                     # full run
#   .\aws\invoke.ps1 -MaxArticles 5      # smoke test (first 5 articles)
#
# Prerequisites:
#   - $env:AWS_REGION set
# =============================================================================

param(
    [int]$MaxArticles = 0   # 0 = no limit (full run)
)

$ErrorActionPreference = "Stop"

if (-not $env:AWS_REGION) {
    Write-Host "[ERROR] `$env:AWS_REGION is not set." -ForegroundColor Red
    Write-Host "  Run: `$env:AWS_REGION = 'us-east-1'" -ForegroundColor Yellow
    exit 1
}

$OUTPUT_FILE = Join-Path $PSScriptRoot "output.json"

if ($MaxArticles -gt 0) {
    $json  = "{`"max_articles`": $MaxArticles}"
    $bytes = [System.Text.Encoding]::ASCII.GetBytes($json)
    $b64   = [Convert]::ToBase64String($bytes)
    Write-Host ""
    Write-Host "Invoking Lambda (smoke test - $MaxArticles articles)..." -ForegroundColor Cyan

    # Smoke test is fast enough for synchronous invocation
    $env:AWS_DEFAULT_READ_TIMEOUT = "120"
    aws lambda invoke `
        --function-name crawlee-blog-validator `
        --payload $b64 `
        --region $env:AWS_REGION `
        --cli-read-timeout 120 `
        $OUTPUT_FILE | Out-Null

} else {
    Write-Host ""
    Write-Host "Invoking Lambda (full run)..." -ForegroundColor Cyan
    Write-Host "This crawls all articles and may take 3-5 minutes." -ForegroundColor Gray
    Write-Host "Invoking asynchronously and polling for completion..." -ForegroundColor Gray

    # Full run: invoke async so the CLI doesn't time out
    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes("{}"))
    aws lambda invoke `
        --function-name crawlee-blog-validator `
        --invocation-type Event `
        --payload $b64 `
        --region $env:AWS_REGION `
        $OUTPUT_FILE | Out-Null

    Write-Host "Lambda triggered. Waiting for it to complete..." -ForegroundColor Gray

    # Poll CloudWatch for the result (wait up to 6 minutes)
    $deadline = (Get-Date).AddMinutes(6)
    $found = $false
    $startMs = [DateTimeOffset]::UtcNow.AddSeconds(-5).ToUnixTimeMilliseconds()

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 15
        Write-Host "  Checking..." -ForegroundColor Gray

        $logs = aws logs filter-log-events `
            --log-group-name /aws/lambda/crawlee-blog-validator `
            --region $env:AWS_REGION `
            --start-time $startMs `
            --filter-pattern "Pass Rate" `
            --query "events[*].message" `
            --output text 2>&1

        if ($logs -and $logs -notmatch "ERROR") {
            Write-Host ""
            Write-Host "--- Result (from CloudWatch) ---" -ForegroundColor Cyan
            Write-Host $logs
            $found = $true
            break
        }
    }

    if (-not $found) {
        Write-Host "[WARN] Timed out polling. Check CloudWatch manually:" -ForegroundColor Yellow
        Write-Host "  aws logs tail /aws/lambda/crawlee-blog-validator --region $($env:AWS_REGION)" -ForegroundColor Yellow
    }
    return
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Lambda invocation failed." -ForegroundColor Red
    exit 1
}

$result = Get-Content $OUTPUT_FILE -Raw | ConvertFrom-Json

if ($result.statusCode -eq 500) {
    Write-Host ""
    Write-Host "--- Lambda returned an error ---" -ForegroundColor Red
    $result.body | ConvertTo-Json -Depth 10
    Write-Host ""
    Write-Host "Check CloudWatch logs for details:" -ForegroundColor Yellow
    Write-Host "  aws logs tail /aws/lambda/crawlee-blog-validator --follow --region $($env:AWS_REGION)" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "--- Result ---" -ForegroundColor Cyan
    $result | ConvertTo-Json -Depth 10
    Write-Host ""
    Write-Host "Full output saved to: $OUTPUT_FILE" -ForegroundColor Gray
}
