$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-Python {
  param([Parameter(Mandatory = $true)][string]$RootDir)

  $venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) { return @($venvPython) }

  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return @($python.Source) }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return @($py.Source, "-3") }

  throw "python is required (install Python 3.11+ and ensure it is on PATH)."
}

function Headline([string]$Text) {
  Write-Host ""
  Write-Host "=== $Text ==="
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Resolve-Path (Join-Path $scriptRoot "..")
$pythonParts = Resolve-Python -RootDir "$rootDir"
$pythonExe = $pythonParts[0]
$pythonPrefix = @()
if ($pythonParts.Length -gt 1) { $pythonPrefix = @($pythonParts[1]) }

$existingPythonPath = $env:PYTHONPATH
if (-not $existingPythonPath) { $existingPythonPath = "" }
$env:PYTHONPATH = (Join-Path $rootDir "src") + ";" + $existingPythonPath

Headline "System"
Write-Host "OS: $([System.Environment]::OSVersion.VersionString)"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
& $pythonExe @pythonPrefix --version

Headline "Tooling availability"
foreach ($tool in @("uv", "pipx", "gsd")) {
  $cmd = Get-Command $tool -ErrorAction SilentlyContinue
  if ($cmd) {
    Write-Host "- $tool: $($cmd.Source)"
  } else {
    Write-Host "- $tool: not found"
  }
}

Headline "Environment vars"
$vars = @("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BROWSER_USE_API_KEY", "GSD_LLM_PROVIDER", "GSD_MODEL", "GSD_JSON_LOGS", "LOG_LEVEL", "GSD_ENV_FILE")
foreach ($name in $vars) {
  if ($env:$name) { Write-Host "$name=set" } else { Write-Host "$name=(unset)" }
}

Headline "Config validation"
& $pythonExe @pythonPrefix -c "from gsd_browser.config import load_settings; s=load_settings(strict=False); print(f'Config OK: model={s.model}, log_level={s.log_level}')"

Headline "MCP config snippet"
& $pythonExe @pythonPrefix (Join-Path $rootDir "scripts\print-mcp-config.py")

Headline "Placeholder smoke"
"ping" | & $pythonExe @pythonPrefix -m gsd_browser.cli serve-echo --once
