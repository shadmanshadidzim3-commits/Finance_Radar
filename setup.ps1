<#
    One-time setup for Finance Radar.

        powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "Setting up Finance Radar..." -ForegroundColor Cyan

# 1. Virtual environment
$venv = Join-Path $root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "  Creating virtual environment..."
    python -m venv $venv
} else {
    Write-Host "  Virtual environment already exists."
}
$py = Join-Path $venv "Scripts\python.exe"

# 2. Dependencies
Write-Host "  Installing dependencies (this takes a minute)..."
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r (Join-Path $root "requirements.txt")

# 3. Check that an analysis engine is reachable
Write-Host ""
Write-Host "Checking for an analysis engine..." -ForegroundColor Cyan
$found = $false

if (Get-Command claude -ErrorAction SilentlyContinue) {
    Write-Host "  [ok] claude CLI found - free with your Claude subscription." -ForegroundColor Green
    $found = $true
}
if ($env:ANTHROPIC_API_KEY) {
    Write-Host "  [ok] ANTHROPIC_API_KEY is set." -ForegroundColor Green
    $found = $true
}
if (Get-Command gemini -ErrorAction SilentlyContinue) {
    Write-Host "  [ok] gemini CLI found (make sure it is logged in)." -ForegroundColor Green
    $found = $true
}

if (-not $found) {
    Write-Host "  [!] No analysis engine found yet." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Pick ONE of these, then re-run setup:"
    Write-Host "    1. npm install -g @anthropic-ai/claude-code"
    Write-Host "       then run 'claude' once and log in.   (free with your Claude plan)"
    Write-Host "    2. Set ANTHROPIC_API_KEY in your environment.  (pay per use)"
    Write-Host "    3. Run 'gemini' once and log in with Google.   (free tier)"
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Try it without calling the model:"
Write-Host "    .\.venv\Scripts\python.exe run_daily.py --dry-run"
Write-Host ""
Write-Host "Run it for real:"
Write-Host "    .\.venv\Scripts\python.exe run_daily.py"
Write-Host ""
Write-Host "Then schedule it daily:"
Write-Host "    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1"
