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

# If we're running through a shim (pyenv), prefer the real interpreter path for pipx.
$pythonExe = Resolve-RealPythonExe -PythonExe $pythonExe -PythonPrefix $pythonPrefix
$pythonPrefix = @()

# Force pipx to use the detected Python (avoids pyenv shim ambiguity / stale PIPX_DEFAULT_PYTHON).
$env:PIPX_DEFAULT_PYTHON = $pythonExe

Ensure-Pipx -PythonExe $pythonExe -PythonPrefix $pythonPrefix
$pipxBin = Get-PipxBinDir -PythonExe $pythonExe -PythonPrefix $pythonPrefix
Ensure-OnPathForSession -Dir $pipxBin

Write-Host "Installing gsd via pipx from $rootDir ..."
Invoke-Exe -Exe $pythonExe -Args @(
  $pythonPrefix + @("-m", "pipx", "install", "--python", $pythonExe, "--force", "$rootDir")
)

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
