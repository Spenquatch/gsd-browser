param(
  [switch]$PurgeConfig = $false
)

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

function Invoke-NativeBestEffort {
  param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string[]]$Args
  )
  $prevEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Exe @Args 2>&1 | Out-Host
  } catch {
    # ignore
  } finally {
    $ErrorActionPreference = $prevEap
  }
}

function Resolve-PythonBestEffort {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return [pscustomobject]@{ Exe = ($python.Source | Out-String).Trim().Trim('"'); Prefix = @() }
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return [pscustomobject]@{ Exe = ($py.Source | Out-String).Trim().Trim('"'); Prefix = @("-3") }
  }

  return $null
}

$configDir = Join-Path $HOME ".gsd"
$manifestFile = Join-Path $configDir "install.json"

function Read-ManifestBestEffort {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return $null }
  try {
    return (Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Remove-TreeBestEffort {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  try { Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue } catch { }
}

function Remove-FileBestEffort {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { return }
  try { Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue } catch { }
}

function Remove-GsdShimsBestEffort {
  param([Parameter(Mandatory = $true)][string]$BinDir)
  if (-not (Test-Path -LiteralPath $BinDir)) { return }
  $names = @(
    "gsd.exe",
    "gsd.exe.manifest",
    "gsd-script.py",
    "gsd-browser.exe",
    "gsd-browser.exe.manifest",
    "gsd-browser-script.py"
  )
  foreach ($n in $names) {
    Remove-FileBestEffort -Path (Join-Path $BinDir $n)
  }
}

$manifest = Read-ManifestBestEffort -Path $manifestFile

$candidateVenvPaths = New-Object System.Collections.Generic.List[string]
if ($manifest -and $manifest.pipx_venv) {
  $candidateVenvPaths.Add(($manifest.pipx_venv | Out-String).Trim())
}
$candidateVenvPaths.Add((Join-Path $HOME "pipx\\venvs\\gsd"))
$candidateVenvPaths.Add((Join-Path $HOME ".local\\pipx\\venvs\\gsd"))
$candidateVenvPaths.Add((Join-Path $HOME ".gsd\\pipx_home\\venvs\\gsd"))

$candidateBinDirs = @(
  (Join-Path $HOME ".local\\bin"),
  (Join-Path $HOME ".gsd\\bin")
)

# Best-effort pipx uninstall. Not required for cleanup (we also remove venv + shims directly).
$pythonCmd = Resolve-PythonBestEffort
if ($pythonCmd) {
  $pythonExe = $pythonCmd.Exe
  $pythonPrefix = $pythonCmd.Prefix

  # Prefer the real interpreter path (helps with pyenv shims).
  try {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $resolved = & $pythonExe @pythonPrefix -c "import sys; print(sys.executable)" 2>$null
    $ErrorActionPreference = $prevEap
    if ($LASTEXITCODE -eq 0 -and $resolved) {
      $pythonExe = ($resolved | Out-String).Trim().Trim('"')
      $pythonPrefix = @()
    }
  } catch {
    # ignore
  } finally {
    $ErrorActionPreference = $prevEap
  }

  $env:PIPX_DEFAULT_PYTHON = $pythonExe

  # Try uninstall in both the default and the isolated pipx homes used by install.ps1.
  $pipxHomes = @(
    $null,
    (Join-Path $HOME ".gsd\\pipx_home")
  )
  if ($manifest -and $manifest.pipx_venv) {
    try {
      $venv = ($manifest.pipx_venv | Out-String).Trim()
      $venvsDir = Split-Path -Parent $venv
      $homeFromManifest = Split-Path -Parent $venvsDir
      if ($homeFromManifest -and -not ($pipxHomes -contains $homeFromManifest)) {
        $pipxHomes += $homeFromManifest
      }
    } catch {
      # ignore
    }
  }

  foreach ($pipxHomeCandidate in $pipxHomes) {
    if ($pipxHomeCandidate) {
      $env:PIPX_HOME = $pipxHomeCandidate
      $env:PIPX_BIN_DIR = (Join-Path $HOME ".gsd\\bin")
    } else {
      Remove-Item Env:PIPX_HOME -ErrorAction SilentlyContinue
      Remove-Item Env:PIPX_BIN_DIR -ErrorAction SilentlyContinue
    }

    # Only attempt pipx if it exists for this interpreter.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonExe @pythonPrefix -m pipx --version *> $null
    $pipxOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap

    if ($pipxOk) {
      Invoke-NativeBestEffort -Exe $pythonExe -Args @($pythonPrefix + @("-m", "pipx", "uninstall", "gsd"))
    }
  }
} else {
  Write-Host "python/pipx not found; removing files directly where possible."
}

# Remove venv directories directly (covers broken pipx state / removed interpreters).
foreach ($venvPath in $candidateVenvPaths) {
  if (-not $venvPath) { continue }
  Remove-TreeBestEffort -Path $venvPath
}

# Remove shims that pipx leaves behind (especially for isolated bin dir).
foreach ($binDir in $candidateBinDirs) {
  if ($binDir) { Remove-GsdShimsBestEffort -BinDir $binDir }
}

if (Test-Path $manifestFile) {
  Remove-Item -Force $manifestFile -ErrorAction SilentlyContinue
  Write-Host "Removed manifest $manifestFile"
}

if ($PurgeConfig -and (Test-Path $configDir)) {
  Remove-Item -Recurse -Force $configDir -ErrorAction SilentlyContinue
  Write-Host "Removed config dir $configDir"
}

try {
  $docker = Get-Command docker -ErrorAction SilentlyContinue
  if ($docker) {
    $exists = & docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $valkeyContainerName }
    if ($exists) {
      Write-Host "Removing Valkey container: $valkeyContainerName"
      & docker rm -f $valkeyContainerName | Out-Null
    }
  }
} catch {
  # best-effort
}

Write-Host "Uninstall complete."
Write-Host "Remove $HOME\\.local\\bin (and/or $HOME\\.gsd\\bin) from PATH manually if desired."
