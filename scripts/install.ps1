param([switch]$PluginOnly)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Get-Command python, codex, git -ErrorAction Stop | Out-Null
if (-not $PluginOnly) {
    python -m pip install --user $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw 'CLI installation failed.' }
}
codex plugin marketplace add $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Marketplace registration failed.' }
codex plugin add astra-autopilot@astra-autopilot-marketplace
if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed.' }
Write-Host 'Installed. Start a new Codex app task or CLI session to load Astra Autopilot.'
Write-Host 'If astra-autopilot is not on PATH, use python -m astra_supervisor.'
