# HAP New Company Windows certification.
# Pulls latest git, activates backend\.venv, runs the full pytest suite, then
# launches a selected New Company analysis, pauses for manual lease-rate
# approval, runs Excel COM CalculateFullRebuild, validates, and prints artifacts.
#
# Required environment variables:
#   HAP_NC_TICKER     e.g. MSFT
#   HAP_NC_WORKBOOK   path to Industrial Template .xlsx
#   HAP_NC_CRF        path to Bloomberg Custom_Run_Filter .xlsx
# Optional:
#   HAP_NC_COMPANY    company name
#
# Usage (from the HAP repo root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows_new_company_certification.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    $RepoRoot = Get-Location
}
Set-Location $RepoRoot

Write-Host "Pulling latest committed changes..."
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

$Py = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating backend\.venv..."
    python -m venv (Join-Path $RepoRoot "backend\.venv")
    $Py = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
}

Write-Host "Installing backend requirements into .venv..."
& $Py -m pip install -r (Join-Path $RepoRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "Running full backend test suite..."
Push-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest tests -q
$TestExit = $LASTEXITCODE
Pop-Location
if ($TestExit -ne 0) { throw "pytest failed with exit code $TestExit" }

if (-not $env:HAP_NC_TICKER) { throw "Set HAP_NC_TICKER (e.g. MSFT)" }
if (-not $env:HAP_NC_WORKBOOK) { throw "Set HAP_NC_WORKBOOK to the Industrial Template .xlsx" }
if (-not $env:HAP_NC_CRF) { throw "Set HAP_NC_CRF to the Custom_Run_Filter .xlsx" }

Write-Host "Launching New Company analysis for $($env:HAP_NC_TICKER)..."
Write-Host "The run will pause for manual lease-rate approval, then Excel COM CalculateFullRebuild."
& $Py (Join-Path $RepoRoot "backend\scripts\new_company_windows_certify.py")
exit $LASTEXITCODE
