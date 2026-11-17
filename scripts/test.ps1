<#
  Runs all tests: backend (pytest) and frontend (Vitest).
  Both suites always run, even if the first one fails.

  Usage:   .\scripts\test.ps1
#>

. "$PSScriptRoot\common.ps1"

& (Join-Path $PSScriptRoot "setup.ps1")

$failed = @()

Write-Step "Backend tests (pytest)"
Push-Location $BackendDir
try {
    Invoke-Native "Backend tests" { & $VenvPython -m pytest }
}
catch {
    $failed += "backend"
}
finally {
    Pop-Location
}

Write-Step "Frontend tests (Vitest)"
Push-Location $FrontendDir
try {
    Invoke-Native "Frontend tests" { npm.cmd test }
}
catch {
    $failed += "frontend"
}
finally {
    Pop-Location
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "All tests passed." -ForegroundColor Green
    exit 0
}
Write-Host ("Tests failed: " + ($failed -join ", ") + ". Scroll up to see which ones and why.") -ForegroundColor Red
exit 1
