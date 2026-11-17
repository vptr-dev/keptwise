<#
  Tests the installer on this PC: install, start from the Start Menu,
  uninstall, and what happens to the data. Run it after build.ps1:
      .\packaging\test-install.ps1

  Part 1 uses the real installer (dist\Keptwise-Setup.exe):
    - installs silently for this user,
    - checks the program and the Start Menu shortcut are there,
    - starts the app from the shortcut, checks it writes to
      %APPDATA%\Keptwise, and closes it,
    - uninstalls silently and checks the data folder is KEPT.
  Part 2 builds a test copy of the installer whose data folder is
  %APPDATA%\KeptwiseInstallTest, so the "delete my data" choice is
  tested without ever touching your real saves or saved API keys.

  The app is uninstalled again at the end; your data stays.
#>
. "$PSScriptRoot\..\scripts\common.ps1"

$DistDir   = Join-Path $RepoRoot "dist"
$LogDir    = Join-Path $RepoRoot "build\install-test"
$Setup     = Join-Path $DistDir "Keptwise-Setup.exe"
$AppDir    = Join-Path $env:LOCALAPPDATA "Programs\Keptwise"
$AppExe    = Join-Path $AppDir "Keptwise.exe"
$Shortcut  = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Keptwise.lnk"
$RealData  = Join-Path $env:APPDATA "Keptwise"
$TestName  = "KeptwiseInstallTest"
$TestData  = Join-Path $env:APPDATA $TestName
$failures  = 0

New-Item -ItemType Directory -Force $LogDir | Out-Null

function Check([bool]$Ok, [string]$What) {
    if ($Ok) { Write-Host "  OK    $What" -ForegroundColor Green }
    else { Write-Host "  FAIL  $What" -ForegroundColor Red; $script:failures++ }
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds = 60) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return [bool](& $Condition)
}

function Install([string]$Installer, [string]$Name) {
    $log = Join-Path $LogDir "$Name-install.log"
    $p = Start-Process -FilePath $Installer -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/LOG=`"$log`"") -PassThru -Wait
    return $p.ExitCode
}

function Uninstall([string[]]$Extra = @()) {
    $uninstaller = Join-Path $AppDir "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) { return $false }
    Start-Process -FilePath $uninstaller -ArgumentList (@("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") + $Extra) -Wait | Out-Null
    # The uninstaller hands over to a copy of itself, so wait for the folder to go.
    return (Wait-Until { -not (Test-Path -LiteralPath $AppExe) } 90)
}

if (-not (Test-Path -LiteralPath $Setup)) { throw "Build the installer first: .\packaging\build.ps1" }
if (Test-Path -LiteralPath $AppExe) { throw "Keptwise is already installed. Uninstall it first, then run this again." }

# ---------- part 1: the real installer ----------

Write-Step "Part 1: install, start from the Start Menu, uninstall (keeps data)"
$hadData = Test-Path -LiteralPath $RealData
Check ((Install $Setup "real") -eq 0) "installer finished"
Check (Test-Path -LiteralPath $AppExe) "program installed in $AppDir"
Check (Test-Path -LiteralPath $Shortcut) "Start Menu shortcut"

$appLog = Join-Path $RealData "logs\app.log"
$logBefore = if (Test-Path -LiteralPath $appLog) { (Get-Item -LiteralPath $appLog).Length } else { 0 }
Start-Process -FilePath $Shortcut
$window = $null
$started = Wait-Until {
    $script:window = Get-Process Keptwise -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq "Keptwise" } | Select-Object -First 1
    [bool]$script:window
} 60
Check $started "app window opened from the Start Menu shortcut"
$logged = Wait-Until {
    (Test-Path -LiteralPath $appLog) -and
        ((Get-Content -Raw -LiteralPath $appLog).Substring([Math]::Min($logBefore, (Get-Item -LiteralPath $appLog).Length)) -match "is running at")
} 30
Check $logged "app uses $RealData (its log says it started)"
if ($window) {
    Start-Sleep -Seconds 3  # let the page finish loading
    [void]$window.CloseMainWindow()
    Check (Wait-Until { -not (Get-Process -Id $window.Id -ErrorAction SilentlyContinue) } 30) "app closed cleanly when its window closed"
}

Check (Uninstall) "uninstalled"
Check (-not (Test-Path -LiteralPath $Shortcut)) "Start Menu shortcut removed"
Check (Test-Path -LiteralPath (Join-Path $RealData "saves.db")) "data in $RealData kept (silent uninstall)"
if (-not $hadData) { Write-Host "  (the data folder was made by this test)" }

# ---------- part 2: the delete-data choice, on a test folder ----------

Write-Step "Part 2: 'delete my data' on a test data folder ($TestName)"
$iscc = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command ISCC.exe).Source }
Invoke-Native "Building the test installer" {
    & $iscc /Qp "/DDataName=$TestName" "/FKeptwise-InstallTest" "/O$LogDir" (Join-Path $PSScriptRoot "Keptwise.iss")
}
$testSetup = Join-Path $LogDir "Keptwise-InstallTest.exe"

function Make-TestData {
    New-Item -ItemType Directory -Force (Join-Path $TestData "logs") | Out-Null
    Set-Content -LiteralPath (Join-Path $TestData "saves.db") -Value "test" -Encoding ascii
}

Check ((Install $testSetup "keep") -eq 0) "test copy installed"
Make-TestData
Check (Uninstall) "uninstalled without /DELETEDATA"
Check (Test-Path -LiteralPath (Join-Path $TestData "saves.db")) "test data kept"

Check ((Install $testSetup "delete") -eq 0) "test copy installed again"
Make-TestData
Check (Uninstall @("/DELETEDATA")) "uninstalled with /DELETEDATA"
Check (-not (Test-Path -LiteralPath $TestData)) "test data deleted"
Check (Test-Path -LiteralPath (Join-Path $RealData "saves.db")) "real data still untouched"

if (Test-Path -LiteralPath $TestData) { Remove-Item -LiteralPath $TestData -Recurse -Force }
Remove-Item -LiteralPath $testSetup -Force -ErrorAction SilentlyContinue

Write-Host ""
if ($failures) { Write-Host "$failures check(s) failed. Logs: $LogDir" -ForegroundColor Red; exit 1 }
Write-Host "All install checks passed." -ForegroundColor Green
