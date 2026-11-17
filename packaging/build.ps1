<#
  Builds the Windows installer: dist\Keptwise-Setup.exe

  Usage (from the project folder, in PowerShell):
      .\packaging\build.ps1

  Options:
      -Version 1.2.0     version to stamp on the app (default: backend\app\__init__.py)
      -Install           install the new build over this PC's copy and reopen it
      -WithFfmpeg        also ship ffmpeg.exe (found on PATH). Off by default:
                         the app doesn't need it for normal downloads, and
                         it adds about 80-230 MB.
      -SearchModel DIR   folder with the bge-small-en-v1.5 search model
                         (found or downloaded automatically otherwise)
      -SkipSmokeTest     don't open the built app to check it starts

  What it does:
      1. Gets .venv and the frontend packages ready (scripts\setup.ps1),
         plus PyInstaller (backend\requirements-build.txt).
      2. Builds the frontend (frontend\dist).
      3. Finds the 67 MB search model, or downloads it once into
         packaging\cache.
      4. PyInstaller -> build\app\Keptwise\Keptwise.exe
      5. Opens the built app once to check it starts (closes by itself).
      6. Inno Setup -> dist\Keptwise-Setup.exe (the only file left in dist)

  Needs Inno Setup 6 (https://jrsoftware.org/isdl.php). Nothing else is
  installed system-wide by this script.
#>
param(
    [string] $Version = "",
    [switch] $WithFfmpeg,
    [string] $SearchModel = "",
    [switch] $SkipSmokeTest,
    # Install the new build over the one on this PC, the same way the app's
    # "Update now" does (old program files removed, data kept, app reopened).
    [switch] $Install
)

. "$PSScriptRoot\..\scripts\common.ps1"

$PackagingDir = $PSScriptRoot
$DistDir      = Join-Path $RepoRoot "dist"
$BuildDir     = Join-Path $RepoRoot "build"
$AppDir       = Join-Path $BuildDir "app"   # the PyInstaller program folder
$CacheDir     = Join-Path $PackagingDir "cache"
$ModelFolder  = "bge-small-en-v1.5"

function Find-InnoSetup {
    $candidates = @()
    $onPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    # Per-user install (winget's default) and the usual machine-wide places.
    $candidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    if (${env:ProgramFiles(x86)}) { $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe" }
    $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    throw ("Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php " +
        "(or: winget install JRSoftware.InnoSetup), then run this again.")
}

function Test-SearchModel([string]$Folder) {
    $Folder -and (Test-Path -LiteralPath (Join-Path $Folder "model_optimized.onnx")) -and
        (Test-Path -LiteralPath (Join-Path $Folder "tokenizer.json"))
}

function Find-SearchModel {
    if ($SearchModel) {
        if (Test-SearchModel $SearchModel) { return (Resolve-Path -LiteralPath $SearchModel).Path }
        throw "The folder $SearchModel doesn't have the search model files (model_optimized.onnx, tokenizer.json)."
    }
    $places = @(
        (Join-Path $CacheDir "models\search\$ModelFolder"),
        (Join-Path $RepoRoot ".devdata\models\search\$ModelFolder")
    )
    if ($env:APPDATA) { $places += Join-Path $env:APPDATA "Keptwise\models\search\$ModelFolder" }
    foreach ($place in $places) {
        if ((Test-SearchModel $place) -and (Test-Path -LiteralPath (Join-Path $place ".complete"))) { return $place }
    }
    Write-Step "Downloading the search model (67 MB, once) into packaging\cache"
    $models = Join-Path $CacheDir "models"
    # Out-Host: show Python's message without it becoming part of this function's answer.
    Invoke-Native "Downloading the search model" {
        & $VenvPython -c "import sys; sys.path.insert(0, r'$BackendDir'); from pathlib import Path; from app.search.embedder import download_search_model; print(download_search_model(Path(r'$models')))" | Out-Host
    }
    return Join-Path $models "search\$ModelFolder"
}

function Get-AppVersion {
    if ($Version) { return $Version.TrimStart("v") }
    $line = Select-String -LiteralPath (Join-Path $BackendDir "app\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"'
    return $line.Matches[0].Groups[1].Value
}

# ---------- 1. tools ----------

Write-Step "Checking the project is set up"
& (Join-Path $RepoRoot "scripts\setup.ps1")
# TikTok refuses OpenSSL 3.0's handshake (python.org's 3.12 builds), so every
# TikTok video would fail in the installed app. Needs OpenSSL 3.5 or newer.
& $VenvPython -c "import ssl, sys; sys.exit(0 if ssl.OPENSSL_VERSION_INFO >= (3, 5) else 1)"
if ($LASTEXITCODE -ne 0) {
    $openssl = & $VenvPython -c "import ssl; print(ssl.OPENSSL_VERSION)"
    throw ("The .venv Python uses $openssl, which TikTok blocks. Delete .venv and make it again " +
        "with uv's Python: uv python install 3.12, then run scripts\setup.ps1.")
}
$buildRequirements = Join-Path $BackendDir "requirements-build.txt"
Invoke-Native "Installing PyInstaller (inside .venv)" {
    & $VenvPython -m pip install --disable-pip-version-check --quiet -r $buildRequirements
}
$iscc = Find-InnoSetup
Write-Host "Inno Setup: $iscc"

$appVersion = Get-AppVersion
# Windows wants plain numbers (1.2.0) in the installer's version fields.
$numericVersion = if ($appVersion -match '^(\d+\.\d+\.\d+)') { $Matches[1] } else { "0.0.0" }
Write-Host "Version: $appVersion"
if ($Version) {
    # Stamp the version into the backend before PyInstaller reads it.
    $initFile = Join-Path $BackendDir "app\__init__.py"
    $text = Get-Content -Raw -LiteralPath $initFile
    $originalInit = $text
    $text = $text -replace '__version__\s*=\s*"[^"]+"', "__version__ = `"$appVersion`""
    [System.IO.File]::WriteAllText($initFile, $text)
}

# ---------- 2. frontend ----------

Write-Step "Building the frontend"
Push-Location $FrontendDir
try { Invoke-Native "Building the frontend" { npm.cmd run build } }
finally { Pop-Location }

# ---------- 3. search model and ffmpeg ----------

$env:SK_SEARCH_MODEL = Find-SearchModel
Write-Host "Search model: $env:SK_SEARCH_MODEL"
$env:SK_FFMPEG = ""
if ($WithFfmpeg) {
    $ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if (-not $ffmpeg) { throw "-WithFfmpeg was given, but ffmpeg.exe is not on PATH." }
    $env:SK_FFMPEG = $ffmpeg.Source
    Write-Host "ffmpeg: $env:SK_FFMPEG"
}

# ---------- 4. PyInstaller ----------

Write-Step "Packing the app with PyInstaller (takes a few minutes)"
# Start clean: dist ends up holding only the new setup file.
foreach ($old in @($AppDir, $DistDir)) {
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
}
Invoke-Native "PyInstaller" {
    & $VenvPython -m PyInstaller --noconfirm --clean --log-level WARN `
        --distpath $AppDir --workpath (Join-Path $BuildDir "pyinstaller") (Join-Path $PackagingDir "Keptwise.spec")
}
$exe = Join-Path $AppDir "Keptwise\Keptwise.exe"
# PyInstaller has read the stamped version: put the file back as it was in git.
if ($originalInit) { [System.IO.File]::WriteAllText($initFile, $originalInit) }

# ---------- 5. does it start? ----------

if (-not $SkipSmokeTest) {
    Write-Step "Opening the built app once to check it starts"
    $testData = Join-Path $BuildDir "smoke-test-data"
    if (Test-Path -LiteralPath $testData) { Remove-Item -LiteralPath $testData -Recurse -Force }
    $process = Start-Process -FilePath $exe -ArgumentList @("--smoke-test", "--data-dir", "`"$testData`"") -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        $log = Join-Path $testData "logs\app.log"
        if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 40 }
        throw "The built app didn't start properly (exit code $($process.ExitCode)). Its log is shown above."
    }
    Write-Host "The built app started and showed its home page." -ForegroundColor Green
}

# ---------- 6. installer ----------

Write-Step "Making the installer with Inno Setup"
Invoke-Native "Inno Setup" {
    & $iscc /Qp "/DAppVersion=$numericVersion" (Join-Path $PackagingDir "Keptwise.iss")
}

$setup = Get-Item -LiteralPath (Join-Path $DistDir "Keptwise-Setup.exe")
$folderBytes = (Get-ChildItem -LiteralPath (Join-Path $AppDir "Keptwise") -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ""
Write-Host ("Done: {0}  ({1:N0} MB; {2:N0} MB once installed)" -f $setup.FullName, ($setup.Length / 1MB), ($folderBytes / 1MB)) -ForegroundColor Green

# ---------- 7. install on this PC (with -Install) ----------

if ($Install) {
    Write-Step "Installing over the copy on this PC"
    # WaitForExit, not -Wait: -Wait would also wait for the app the installer reopens.
    $process = Start-Process -FilePath $setup.FullName -PassThru -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/CLOSEAPPLICATIONS", "/RELAUNCH")
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "The installer stopped with exit code $($process.ExitCode)." }
    Write-Host "Installed Keptwise $appVersion and opened it." -ForegroundColor Green
}
