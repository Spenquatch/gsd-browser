$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_PYTHON_VERSION_WARNING = "1"
$env:PIP_NO_COLOR = "1"
$env:PIP_PROGRESS_BAR = "off"

$valkeyContainerName = if ($env:GSD_VALKEY_CONTAINER_NAME) { $env:GSD_VALKEY_CONTAINER_NAME } else { "gsd-valkey" }
$valkeyImage = if ($env:GSD_VALKEY_IMAGE) { $env:GSD_VALKEY_IMAGE } else { "valkey/valkey:7.2-alpine" }
$docketUrl = if ($env:FASTMCP_DOCKET_URL_VALUE) { $env:FASTMCP_DOCKET_URL_VALUE } else { "redis://localhost:6379/0" }

function Resolve-Python {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return [pscustomobject]@{
      Exe    = $python.Source
      Prefix = @()
    }
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return [pscustomobject]@{
      Exe    = $py.Source
      Prefix = @("-3")
    }
  }

  throw "python is required (install Python 3.11+ and ensure it is on PATH)."
}

function Invoke-Exe {
  param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string[]]$Args
  )
  & $Exe @Args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed: $Exe $($Args -join ' ') (exit=$LASTEXITCODE)"
  }
}

function Ensure-Pipx {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string[]]$PythonPrefix = @()
  )

  & $PythonExe @PythonPrefix -m pipx --version | Out-Null
  if ($LASTEXITCODE -eq 0) { return }

  Write-Host "pipx not found; installing via pip --user..."
  Invoke-Exe -Exe $PythonExe -Args @($PythonPrefix + @("-m", "pip", "install", "--user", "pipx"))

  # Ensure PATH contains pipx scripts for future shells.
  & $PythonExe @PythonPrefix -m pipx ensurepath --force *> $null
}

function Get-PipxBinDir {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string[]]$PythonPrefix = @()
  )

  $bin = & $PythonExe @PythonPrefix -c "import pipx.paths; print(pipx.paths.ctx.bin_dir)"
  if ($LASTEXITCODE -eq 0 -and $bin) { return $bin.Trim() }
  return (Join-Path $HOME ".local\bin")
}

function Ensure-OnPathForSession {
  param([Parameter(Mandatory = $true)][string]$Dir)

  if (-not $Dir) { return }

  $pathParts = $env:PATH -split ";"
  if ($pathParts -contains $Dir) { return }
  $env:PATH = "$Dir;$env:PATH"
}

function Invoke-PipxInstallFromSource {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$SourceDir
  )

  Invoke-Exe -Exe $PythonExe -Args @(
    "-m", "pipx", "install", "--python", $PythonExe, "--force", "--editable", "$SourceDir[dev]"
  )
}

function Resolve-RealPythonExe {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string[]]$PythonPrefix = @()
  )

  $resolved = & $PythonExe @PythonPrefix -c "import sys; print(sys.executable)"
  if ($LASTEXITCODE -ne 0 -or -not $resolved) {
    throw "Failed to resolve sys.executable from: $PythonExe"
  }
  return ($resolved | Out-String).Trim().Trim('"')
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Resolve-Path (Join-Path $scriptRoot "..")
$manifestDir = Join-Path $HOME ".gsd"
$manifestFile = Join-Path $manifestDir "install.json"
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null

$pythonCmd = Resolve-Python
$pythonExe = ($pythonCmd.Exe | Out-String).Trim().Trim('"')
$pythonPrefix = $pythonCmd.Prefix

# Ensure Valkey (Redis-compatible) is running for FastMCP v2 stdio.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "docker is required to start Valkey for FastMCP v2. Install Docker and ensure the daemon is running."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "docker daemon is not reachable; start Docker and re-run this script."
}

$running = & docker ps --format "{{.Names}}" | Where-Object { $_ -eq $valkeyContainerName }
if ($running) {
  Write-Host "Valkey container already running: $valkeyContainerName"
} else {
  $exists = & docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $valkeyContainerName }
  if ($exists) {
    Write-Host "Starting Valkey container: $valkeyContainerName"
    & docker start $valkeyContainerName | Out-Null
  } else {
    Write-Host "Creating Valkey container: $valkeyContainerName"
    & docker run -d --name $valkeyContainerName --restart unless-stopped -p 127.0.0.1:6379:6379 $valkeyImage valkey-server --save "" --appendonly no | Out-Null
  }
}

# If we're running through a shim (pyenv), prefer the real interpreter path for pipx.
$pythonExe = Resolve-RealPythonExe -PythonExe $pythonExe -PythonPrefix $pythonPrefix
$pythonPrefix = @()

# Force pipx to use the detected Python (avoids pyenv shim ambiguity / stale PIPX_DEFAULT_PYTHON).
$env:PIPX_DEFAULT_PYTHON = $pythonExe

Ensure-Pipx -PythonExe $pythonExe -PythonPrefix $pythonPrefix
$pipxBin = Get-PipxBinDir -PythonExe $pythonExe -PythonPrefix $pythonPrefix
Ensure-OnPathForSession -Dir $pipxBin

Write-Host "Installing gsd via pipx from $rootDir ..."
try {
  Invoke-PipxInstallFromSource -PythonExe $pythonExe -SourceDir "$rootDir"
} catch {
  Write-Host ""
  Write-Host "pipx install failed; retrying with an isolated pipx home under ~/.gsd (to avoid pyenv/pipx state conflicts)..."

  $isolatedHome = Join-Path $HOME ".gsd\pipx_home"
  $isolatedBin = Join-Path $HOME ".gsd\bin"
  New-Item -ItemType Directory -Force -Path $isolatedHome | Out-Null
  New-Item -ItemType Directory -Force -Path $isolatedBin | Out-Null

  $env:PIPX_HOME = $isolatedHome
  $env:PIPX_BIN_DIR = $isolatedBin
  Ensure-OnPathForSession -Dir $isolatedBin

  # Ensure PATH is persisted for future shells (best-effort).
  & $pythonExe -m pipx ensurepath --force *> $null

  Invoke-PipxInstallFromSource -PythonExe $pythonExe -SourceDir "$rootDir"
}

$version = & $pythonExe @pythonPrefix -c @"
import tomllib
from pathlib import Path
root = Path(r"$rootDir")
data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
print(data["project"]["version"])
"@
$version = $version.Trim()

$pipxVenv = & $pythonExe @pythonPrefix -c @"
import json
import subprocess
import sys

raw = subprocess.check_output([sys.executable, "-m", "pipx", "list", "--json"], text=True)
data = json.loads(raw)
venvs = data.get("venvs") or {}
entry = venvs.get("gsd") or {}
print(entry.get("venv_dir") or "")
"@ 2>$null

$manifest = @{
  installed_at = (Get-Date).ToUniversalTime().ToString("o")
  version      = $version
  source       = "$rootDir"
  pipx_venv    = ($pipxVenv | Out-String).Trim()
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $manifestFile
Write-Host "Manifest written to $manifestFile"

Write-Host ""
Write-Host "Next steps:"
Write-Host "  gsd --version"
Write-Host "  gsd config init"
Write-Host "  gsd config set --anthropic-api-key <...>"
Write-Host "  gsd browser ensure --write-config"
Write-Host "  gsd mcp config --format json"

# Ensure FASTMCP_DOCKET_URL is present in the stable config file for running from any directory.
$envPath = Join-Path $HOME ".gsd\.env"
if (-not (Test-Path $envPath)) {
  & gsd config init *> $null
}

$lines = @()
if (Test-Path $envPath) { $lines = Get-Content -LiteralPath $envPath -ErrorAction SilentlyContinue }
$out = New-Object System.Collections.Generic.List[string]
$seen = $false
foreach ($line in $lines) {
  $trim = $line.Trim()
  if ($trim -and -not $trim.StartsWith("#") -and $trim.Contains("=")) {
    $k = $trim.Split("=", 2)[0].Trim()
    if ($k -eq "FASTMCP_DOCKET_URL") {
      $out.Add("FASTMCP_DOCKET_URL=$docketUrl")
      $seen = $true
      continue
    }
  }
  $out.Add($line)
}
if (-not $seen) {
  if ($out.Count -gt 0 -and $out[$out.Count - 1].Trim() -ne "") { $out.Add("") }
  $out.Add("# Added by gsd install")
  $out.Add("FASTMCP_DOCKET_URL=$docketUrl")
}
$out | Set-Content -Encoding UTF8 -LiteralPath $envPath

Write-Host ""
Write-Host "Configured FASTMCP_DOCKET_URL in $envPath"
Write-Host "Valkey container: $valkeyContainerName (port 6379)"
