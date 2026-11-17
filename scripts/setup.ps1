<#
  Gets this project ready to run: Python packages and frontend packages.

  Safe to run any time. It only installs when something is missing or a
  package list changed. Everything goes inside this project folder
  (.venv and frontend\node_modules); nothing is installed system-wide.

  Usage:   .\scripts\setup.ps1
  (dev.ps1 and test.ps1 run this for you.)
#>

. "$PSScriptRoot\common.ps1"

function Find-Python312 {
    # Programs may print to their error output here; that's fine.
    $ErrorActionPreference = "Continue"

    # 1. Any Python 3.12 the Windows "py" launcher knows about.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($line in (& py -0p 2>$null)) {
            if ($line -match '3\.12' -and $line -match '([A-Za-z]:\\.*python\.exe)\s*$') {
                return $Matches[1]
            }
        }
    }
    # 2. "python" on PATH, if it is 3.12 (for example on the GitHub build machine).
    $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($onPath) {
        $version = & $onPath.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq "3.12") {
            return $onPath.Source
        }
    }
    # 3. A Python 3.12 installed by the "uv" tool.
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $found = & uv python find 3.12 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) {
            return ($found | Select-Object -First 1).Trim()
        }
    }
    throw ("Python 3.12 was not found. Install Python 3.12 from " +
        "https://www.python.org/downloads/windows/ , open a new terminal, and run this again.")
}

function Get-Fingerprint([string[]]$Files) {
    # A short text that changes whenever any of the files change.
    ($Files | ForEach-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_).Hash }) -join "-"
}

function Test-UpToDate([string]$StampFile, [string]$Fingerprint) {
    (Test-Path -LiteralPath $StampFile) -and
        ((Get-Content -Raw -LiteralPath $StampFile).Trim() -eq $Fingerprint)
}

# ---------- Python (backend and app window) ----------

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Step "Creating the Python environment (.venv)"
    $python = Find-Python312
    Write-Host "Using $python"
    Invoke-Native "Creating .venv" { & $python -m venv $VenvDir }
}

$requirements = @(
    (Join-Path $BackendDir "requirements.txt"),
    (Join-Path $BackendDir "requirements-dev.txt")
)
$pythonStamp = Join-Path $VenvDir "installed-requirements.txt"
$pythonPrint = Get-Fingerprint $requirements
if (-not (Test-UpToDate $pythonStamp $pythonPrint)) {
    Write-Step "Installing Python packages"
    Invoke-Native "Installing Python packages" {
        & $VenvPython -m pip install --disable-pip-version-check -r $requirements[1]
    }
    Set-Content -LiteralPath $pythonStamp -Value $pythonPrint -Encoding ascii
}

# Speech to text on an NVIDIA graphics card (optional, about 435 MB, only
# inside .venv). Skipped on PCs without an NVIDIA card; the processor is used.
$gpuRequirements = Join-Path $BackendDir "requirements-gpu.txt"
if (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue) {
    $gpuStamp = Join-Path $VenvDir "installed-requirements-gpu.txt"
    $gpuPrint = Get-Fingerprint @($gpuRequirements)
    if (-not (Test-UpToDate $gpuStamp $gpuPrint)) {
        Write-Step "Adding NVIDIA files so speech to text can use the graphics card"
        Invoke-Native "Installing the NVIDIA files" {
            & $VenvPython -m pip install --disable-pip-version-check -r $gpuRequirements
        }
        Set-Content -LiteralPath $gpuStamp -Value $gpuPrint -Encoding ascii
    }
}

# ---------- Frontend (the app's pages) ----------

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw ("Node.js was not found. Install the LTS version from https://nodejs.org , " +
        "open a new terminal, and run this again.")
}

$nodeStamp = Join-Path $FrontendDir "node_modules\.installed-lock"
$nodePrint = Get-Fingerprint @(Join-Path $FrontendDir "package-lock.json")
if (-not (Test-UpToDate $nodeStamp $nodePrint)) {
    Write-Step "Installing frontend packages"
    Push-Location $FrontendDir
    try {
        # "npm ci" installs exactly the versions in package-lock.json.
        Invoke-Native "Installing frontend packages" { npm.cmd ci --no-audit --no-fund }
    }
    finally {
        Pop-Location
    }
    Set-Content -LiteralPath $nodeStamp -Value $nodePrint -Encoding ascii
}

Write-Host "Setup is up to date." -ForegroundColor Green
