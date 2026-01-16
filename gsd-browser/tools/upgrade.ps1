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

$pythonExe = Resolve-RealPythonExe -PythonExe $pythonExe -PythonPrefix $pythonPrefix
$pythonPrefix = @()

$env:PIPX_DEFAULT_PYTHON = $pythonExe

& $pythonExe @pythonPrefix -m pipx --version | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "pipx is required for upgrades. Run tools/install.ps1 first."
}

Write-Host "Upgrading gsd via pipx from $rootDir ..."
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
Write-Host "Updated manifest at $manifestFile"
