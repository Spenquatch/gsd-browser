$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-Python {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return @($python.Source) }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return @($py.Source, "-3") }

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

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Resolve-Path (Join-Path $scriptRoot "..")
$manifestDir = Join-Path $HOME ".gsd"
$manifestFile = Join-Path $manifestDir "install.json"
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null

$pythonParts = Resolve-Python
$pythonExe = $pythonParts[0]
$pythonPrefix = @()
if ($pythonParts.Length -gt 1) { $pythonPrefix = @($pythonParts[1]) }

& $pythonExe @pythonPrefix -m pipx --version | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "pipx is required for upgrades. Run tools/install.ps1 first."
}

Write-Host "Upgrading gsd via pipx from $rootDir ..."
Invoke-Exe -Exe $pythonExe -Args @($pythonPrefix + @("-m", "pipx", "install", "--force", "$rootDir"))

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
