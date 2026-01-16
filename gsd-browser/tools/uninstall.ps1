$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

param(
  [switch]$PurgeConfig
)

function Resolve-Python {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return @($python.Source) }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return @($py.Source, "-3") }

  throw "python is required (install Python 3.11+ and ensure it is on PATH)."
}

$pythonParts = Resolve-Python
$pythonExe = $pythonParts[0]
$pythonPrefix = @()
if ($pythonParts.Length -gt 1) { $pythonPrefix = @($pythonParts[1]) }

& $pythonExe @pythonPrefix -m pipx --version | Out-Null
if ($LASTEXITCODE -eq 0) {
  & $pythonExe @pythonPrefix -m pipx uninstall gsd | Out-Null
} else {
  Write-Host "pipx not found; skipping pipx uninstall."
}

$configDir = Join-Path $HOME ".gsd"
$manifestFile = Join-Path $configDir "install.json"

if (Test-Path $manifestFile) {
  Remove-Item -Force $manifestFile
  Write-Host "Removed manifest $manifestFile"
}

if ($PurgeConfig -and (Test-Path $configDir)) {
  Remove-Item -Recurse -Force $configDir
  Write-Host "Removed config dir $configDir"
}

Write-Host "Uninstall complete."
