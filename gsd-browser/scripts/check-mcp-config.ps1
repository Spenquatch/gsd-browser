$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$targetName = "gsd"

function Show-Section {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Label
  )

  if (-not (Test-Path $Path)) {
    Write-Host "$Label not found ($Path)"
    Write-Host ""
    return
  }

  Write-Host "Checking $Label ($Path)"
  try {
    $raw = Get-Content -Raw -Path $Path -ErrorAction Stop
    $json = $raw | ConvertFrom-Json -ErrorAction Stop
  } catch {
    Write-Host "  Failed to parse JSON: $($_.Exception.Message)"
    Write-Host ""
    return
  }

  $entry = $null
  if ($json.mcpServers -and $json.mcpServers.$targetName) {
    $entry = $json.mcpServers.$targetName
  }

  if ($entry) {
    Write-Host "  Found entry:"
    ($entry | ConvertTo-Json -Depth 8) -split "`n" | ForEach-Object { Write-Host "  $_" }
  } else {
    Write-Host "  No entry for $targetName"
  }
  Write-Host ""
}

Show-Section -Path (Join-Path $HOME ".claude.json") -Label "Global config"
Show-Section -Path (Join-Path (Get-Location) ".claude.json") -Label "Project config"
