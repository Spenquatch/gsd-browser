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

function Invoke-BestEffort {
  param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string[]]$Args
  )
  try {
    & $Exe @Args | Out-Host
  } catch {
    return
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
  try {
    Invoke-Exe -Exe $PythonExe -Args @($PythonPrefix + @("-m", "pip", "install", "--user", "pipx"))
  } catch {
    Write-Host "pipx install failed; retrying with --break-system-packages (PEP 668 environments)..."
    Invoke-Exe -Exe $PythonExe -Args @($PythonPrefix + @("-m", "pip", "install", "--user", "--break-system-packages", "pipx"))
  }

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

function Get-PipxVenvsDir {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [string[]]$PythonPrefix = @()
  )

  # pipx 1.8.x uses ctx.venvs (a Path) rather than ctx.venvs_dir.
  $venvs = & $PythonExe @PythonPrefix -c "import pipx.paths; print(pipx.paths.ctx.venvs)" 2>$null
  if ($LASTEXITCODE -eq 0 -and $venvs) { return $venvs.Trim() }

  # Best-effort fallback; may not match all pipx versions but avoids hard failures.
  $fallbackHome = if ($env:PIPX_HOME) { $env:PIPX_HOME } else { (Join-Path $HOME ".local\pipx") }
  return (Join-Path $fallbackHome "venvs")
}

function Remove-PipxPackageBestEffort {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$PackageName
  )

  # Try uninstall (may fail if an old venv is broken); ignore errors.
  try { & $PythonExe -m pipx uninstall $PackageName *> $null } catch { }

  # Also remove the venv directory directly to handle pyenv/removed-interpreter breakage.
  try {
    $venvsDir = Get-PipxVenvsDir -PythonExe $PythonExe
    $venvPath = Join-Path $venvsDir $PackageName
    if (Test-Path -LiteralPath $venvPath) {
      Remove-Item -LiteralPath $venvPath -Recurse -Force -ErrorAction SilentlyContinue
    }
  } catch {
    return
  }
}

function Invoke-PipxInstallFromSource {
  param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$SourceDir
  )

  Remove-PipxPackageBestEffort -PythonExe $PythonExe -PackageName "gsd"

  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $output = & $PythonExe -m pipx install --editable "$SourceDir[dev]" 2>&1
  $exit = $LASTEXITCODE
  $ErrorActionPreference = $prevEap

  $text = @()
  if ($output) { $text = @($output | ForEach-Object { $_.ToString() }) }
  if ($exit -ne 0) {
    $preview = ($text | Select-Object -First 60) -join "`n"
    throw "pipx install failed (exit=$exit). Output:`n$preview"
  }

  if ($text) { $text | Out-Host }
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

function Resolve-GsdCli {
  $canonical = Get-Command gsd -ErrorAction SilentlyContinue
  if ($canonical) {
    return [pscustomobject]@{ Exe = ($canonical.Source | Out-String).Trim().Trim('"'); Style = "canonical" }
  }

  $legacy = Get-Command gsd-browser -ErrorAction SilentlyContinue
  if ($legacy) {
    return [pscustomobject]@{ Exe = ($legacy.Source | Out-String).Trim().Trim('"'); Style = "legacy" }
  }

  return $null
}

function Test-InteractiveConsole {
  try {
    if ([Console]::IsInputRedirected) { return $false }
    if ([Console]::IsOutputRedirected) { return $false }
    return $true
  } catch {
    return $false
  }
}

function Read-YesNo {
  param(
    [Parameter(Mandatory = $true)][string]$Prompt,
    [bool]$DefaultYes = $true
  )
  $suffix = if ($DefaultYes) { "[Y/n]" } else { "[y/N]" }
  $ans = ""
  try { $ans = Read-Host "$Prompt $suffix" } catch { return $DefaultYes }
  if (-not $ans) { return $DefaultYes }
  $a = $ans.Trim().ToLowerInvariant()
  return $a.StartsWith("y")
}

function Protect-PrivateFile {
  param([Parameter(Mandatory = $true)][string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) { return }

  $isWindows = ($env:OS -eq "Windows_NT")
  if (-not $isWindows) {
    $chmod = Get-Command chmod -ErrorAction SilentlyContinue
    if ($chmod) {
      try { & $chmod.Source 600 $Path *> $null } catch { }
    }
    return
  }

  $icacls = Get-Command icacls -ErrorAction SilentlyContinue
  if (-not $icacls) { return }

  try {
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & $icacls.Source $Path /inheritance:r /grant:r "${user}:(F)" /grant:r "*S-1-5-18:(F)" /grant:r "*S-1-5-32-544:(F)" *> $null
  } catch {
    return
  }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = (Resolve-Path (Join-Path $scriptRoot "..")).Path.TrimEnd('\', '/')
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

# Stable per-user bin dir (used by Codex/Claude configs that set `command = "gsd"`).
# pipx may choose different default bin locations across versions/platforms; keep a
# consistent `~/.gsd/bin` shim directory so PATH-based MCP hosts can always find `gsd`.
$stableBin = Join-Path $HOME ".gsd\bin"
New-Item -ItemType Directory -Force -Path $stableBin | Out-Null
Ensure-OnPathForSession -Dir $stableBin

Write-Host "Installing gsd via pipx from $rootDir ..."
try {
  Invoke-PipxInstallFromSource -PythonExe $pythonExe -SourceDir "$rootDir"
} catch {
  Write-Host ""
  Write-Host "pipx install failed; retrying with an isolated pipx home under ~/.gsd (to avoid pyenv/pipx state conflicts)..."

  $isolatedHome = Join-Path $HOME ".gsd\pipx_home"
  $isolatedBin = $stableBin
  New-Item -ItemType Directory -Force -Path $isolatedHome | Out-Null
  New-Item -ItemType Directory -Force -Path $isolatedBin | Out-Null

  $env:PIPX_HOME = $isolatedHome
  $env:PIPX_BIN_DIR = $isolatedBin
  Ensure-OnPathForSession -Dir $isolatedBin

  # Ensure PATH is persisted for future shells (best-effort).
  & $pythonExe -m pipx ensurepath --force *> $null

  Invoke-PipxInstallFromSource -PythonExe $pythonExe -SourceDir "$rootDir"
}

$env:ROOT_DIR = "$rootDir"
$version = & $pythonExe @pythonPrefix -c @"
import os
import tomllib
from pathlib import Path

root = Path(os.environ['ROOT_DIR'])
data = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
print(data['project']['version'])
"@
$version = $version.Trim()

$pipxVenv = ""
try {
  $venvsDir = Get-PipxVenvsDir -PythonExe $pythonExe -PythonPrefix $pythonPrefix
  $candidate = Join-Path $venvsDir "gsd"
  if (Test-Path -LiteralPath $candidate) { $pipxVenv = $candidate }
} catch {
  $pipxVenv = ""
}

$manifest = @{
  installed_at = (Get-Date).ToUniversalTime().ToString("o")
  version      = $version
  source       = "$rootDir"
  pipx_venv    = $pipxVenv
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $manifestFile
Write-Host "Manifest written to $manifestFile"

Write-Host ""
Write-Host "Installation complete."

$cli = Resolve-GsdCli
if ($cli) {
  Invoke-BestEffort -Exe $cli.Exe -Args @("--version")
}

# Ensure `~/.gsd/bin/gsd.exe` exists even when pipx installs shims elsewhere (e.g. ~/.gsd/pipx_bin).
# This avoids "program not found" failures in MCP hosts that only have ~/.gsd/bin on PATH.
foreach ($name in @("gsd.exe", "gsd-browser.exe")) {
  try {
    $dst = Join-Path $stableBin $name
    if (Test-Path -LiteralPath $dst) { continue }

    $src = Join-Path $pipxBin $name
    if (-not (Test-Path -LiteralPath $src)) {
      $cmdName = $name.Substring(0, $name.Length - 4)
      $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
      if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        $src = $cmd.Source
      }
    }
    if (Test-Path -LiteralPath $src) {
      Copy-Item -Force -LiteralPath $src -Destination $dst
    }
  } catch {
    # best-effort
  }
}

# Ensure FASTMCP_DOCKET_URL is present in the stable config file for running from any directory.
$envPath = Join-Path $HOME ".gsd\.env"
if (-not (Test-Path $envPath)) {
  if ($cli) {
    if ($cli.Style -eq "canonical") {
      & $cli.Exe config init *> $null
    } else {
      & $cli.Exe init-env *> $null
    }
  } else {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $envPath) | Out-Null
    New-Item -ItemType File -Force -Path $envPath | Out-Null
  }
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
Protect-PrivateFile -Path $envPath

Write-Host ""
Write-Host "Configured FASTMCP_DOCKET_URL in $envPath"
Write-Host "Valkey container: $valkeyContainerName (port 6379)"

if ($cli) {
  if ($cli.Style -eq "canonical") {
    Write-Host "Tip: run 'gsd config set' to add API keys."
    Write-Host "Ensuring a local browser is available (Chrome/Edge)..."
    Invoke-BestEffort -Exe $cli.Exe -Args @("browser", "ensure", "--write-config")
  } else {
    Write-Host "Tip: run 'gsd-browser configure' to add API keys (legacy alias; prefer 'gsd config set')."
    Write-Host "Ensuring a local browser is available (Chrome/Edge)..."
    Invoke-BestEffort -Exe $cli.Exe -Args @("ensure-browser", "--write-config")
  }

  $interactive = Test-InteractiveConsole

  if (Get-Command codex -ErrorAction SilentlyContinue) {
    if ($interactive) {
      if (Read-YesNo -Prompt "Add gsd MCP server to Codex config?" -DefaultYes $true) {
        if ($cli.Style -eq "canonical") {
          Invoke-BestEffort -Exe $cli.Exe -Args @("mcp", "add", "codex")
        } else {
          Invoke-BestEffort -Exe $cli.Exe -Args @("mcp-config-add", "codex")
        }
      }
    } else {
      if ($cli.Style -eq "canonical") {
        Write-Host "Tip: run 'gsd mcp add codex' to add the MCP server to Codex."
      } else {
        Write-Host "Tip: run 'gsd-browser mcp-config-add codex' to add the MCP server to Codex."
      }
    }
  }

  if (Get-Command claude -ErrorAction SilentlyContinue) {
    if ($interactive) {
      if (Read-YesNo -Prompt "Add gsd MCP server to Claude Code config?" -DefaultYes $true) {
        if ($cli.Style -eq "canonical") {
          Invoke-BestEffort -Exe $cli.Exe -Args @("mcp", "add", "claude")
        } else {
          Invoke-BestEffort -Exe $cli.Exe -Args @("mcp-config-add", "claude")
        }
      }
    } else {
      if ($cli.Style -eq "canonical") {
        Write-Host "Tip: run 'gsd mcp add claude' to add the MCP server to Claude Code."
      } else {
        Write-Host "Tip: run 'gsd-browser mcp-config-add claude' to add the MCP server to Claude Code."
      }
    }
  }
} else {
  Write-Host "Note: 'gsd' was not found on PATH after installation. Re-open your shell (or ensure pipx bin dir is on PATH) to run gsd commands."
}

Write-Host "Run: 'gsd mcp serve' or 'gsd dev diagnose'."
