<#
  Opens Keptwise in developer mode.

  1. Makes sure packages are installed (scripts\setup.ps1).
  2. Builds the app's pages into frontend\dist.
  3. Opens the app window. Close the window to stop everything.

  Usage:        .\scripts\dev.ps1
  Quick check:  .\scripts\dev.ps1 -SmokeTest
                (opens the window, checks the hello page shows, closes it)
#>
param(
    [switch] $SmokeTest
)

. "$PSScriptRoot\common.ps1"

& (Join-Path $PSScriptRoot "setup.ps1")

Write-Step "Building the app's pages"
Push-Location $FrontendDir
try {
    Invoke-Native "Building the frontend" { npm.cmd run build }
}
finally {
    Pop-Location
}

Write-Step "Starting Keptwise (close the window to stop)"
# -u: show the app's messages right away instead of in batches.
$launcherArgs = @("-u", (Join-Path $RepoRoot "desktop\launcher.py"))
if ($SmokeTest) {
    $launcherArgs += "--smoke-test"
}
Invoke-Native "Keptwise" { & $VenvPython @launcherArgs }
