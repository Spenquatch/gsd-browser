$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = "utf-8"

param(
  [switch]$PurgeConfig
)

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

$pythonCmd = Resolve-Python
$pythonExe = $pythonCmd.Exe
$pythonPrefix = $pythonCmd.Prefix

$env:PIPX_DEFAULT_PYTHON = $pythonExe

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
