param(
  [string]$InputDir = "offline/images"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $InputDir)) {
  throw "InputDir not found: $InputDir"
}

$tars = Get-ChildItem -Path $InputDir -Filter "*.tar" | Sort-Object Name
if (-not $tars -or $tars.Count -eq 0) {
  throw "No .tar files found in: $InputDir"
}

Write-Host "Loading $($tars.Count) image tar(s) from $InputDir ..."

foreach ($tar in $tars) {
  Write-Host ""
  Write-Host "docker load -i $($tar.FullName)"
  & docker load -i $tar.FullName
  if ($LASTEXITCODE -ne 0) {
    throw "docker load failed for $($tar.FullName)"
  }
}

Write-Host ""
Write-Host "Done. Images are loaded."
Write-Host "Next:"
Write-Host "  docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d"

