# HAP New Company Windows certification.
# Certifies the currently checked-out branch. Does not pull, merge, or switch to main.
#
# Required environment variables:
#   HAP_NC_TICKER     e.g. MSFT
#   HAP_NC_WORKBOOK   path to Industrial Template .xlsx
#   HAP_NC_CRF        path to Bloomberg Custom_Run_Filter .xlsx
# Optional:
#   HAP_NC_COMPANY    company name
#
# Usage (from the HAP repo root, on the New Company branch):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows_new_company_certification.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    $RepoRoot = Get-Location
}
Set-Location $RepoRoot

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

if ($env:OS -notlike "*Windows*" -and [System.Environment]::OSVersion.Platform -ne "Win32NT") {
    Fail "Windows certification requires Microsoft Windows with Excel installed."
}

$Branch = (git rev-parse --abbrev-ref HEAD).Trim()
$Commit = (git rev-parse HEAD).Trim()
Write-Host "Branch: $Branch"
Write-Host "Commit: $Commit"
if (-not $Branch -or $Branch -eq "HEAD") {
    Fail "Could not determine the current Git branch."
}

$Dirty = git status --porcelain --untracked-files=no
if ($Dirty) {
    Write-Host $Dirty
    Fail "Refuse to certify with uncommitted tracked changes. Commit or stash first."
}

$ExcelProgId = $null
try {
    $ExcelProgId = [System.Type]::GetTypeFromProgID("Excel.Application")
} catch {
    $ExcelProgId = $null
}
if (-not $ExcelProgId) {
    Fail "Microsoft Excel COM (Excel.Application) is not registered on this machine."
}

$Py = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating backend\.venv..."
    python -m venv (Join-Path $RepoRoot "backend\.venv")
    $Py = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
}

Write-Host "Installing backend requirements into .venv..."
& $Py -m pip install -r (Join-Path $RepoRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }

Write-Host "Confirming pywin32 / win32com..."
& $Py -c "import win32com.client; print('pywin32 ok')"
if ($LASTEXITCODE -ne 0) { Fail "pywin32 is required for Excel COM CalculateFullRebuild." }

if (-not $env:HAP_NC_TICKER) { Fail "Set HAP_NC_TICKER (e.g. MSFT)" }
if (-not $env:HAP_NC_WORKBOOK) { Fail "Set HAP_NC_WORKBOOK to the Industrial Template .xlsx" }
if (-not $env:HAP_NC_CRF) { Fail "Set HAP_NC_CRF to the Custom_Run_Filter .xlsx" }
if (-not (Test-Path $env:HAP_NC_WORKBOOK)) { Fail "HAP_NC_WORKBOOK does not exist: $($env:HAP_NC_WORKBOOK)" }
if (-not (Test-Path $env:HAP_NC_CRF)) { Fail "HAP_NC_CRF does not exist: $($env:HAP_NC_CRF)" }

Write-Host "Running full backend test suite..."
Push-Location (Join-Path $RepoRoot "backend")
& $Py -m pytest tests -q
$TestExit = $LASTEXITCODE
Pop-Location
if ($TestExit -ne 0) { Fail "pytest failed with exit code $TestExit" }

Write-Host "Launching New Company analysis for $($env:HAP_NC_TICKER) on $Branch @$Commit..."
Write-Host "The run will display the R&D useful-life warning and pause for lease-rate review via the real API."
& $Py (Join-Path $RepoRoot "backend\scripts\new_company_windows_certify.py") --branch $Branch --commit $Commit
exit $LASTEXITCODE
