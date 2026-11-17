# Shared settings and helpers for the scripts in this folder.
# The other scripts load this file with:   . "$PSScriptRoot\common.ps1"

$ErrorActionPreference = "Stop"

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$VenvDir     = Join-Path $RepoRoot ".venv"
$VenvPython  = Join-Path $VenvDir "Scripts\python.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    <#
      Runs a program (python, npm, ...) and stops with an error if it fails.
      Programs often print harmless notices on their error output, so only
      the exit code decides whether it worked.
    #>
    param(
        [Parameter(Mandatory = $true)] [string] $What,
        [Parameter(Mandatory = $true)] [scriptblock] $Command
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "$What failed (exit code $code). Read the messages above for the reason."
    }
}
