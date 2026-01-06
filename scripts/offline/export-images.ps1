param(
  [string]$OutputDir = "offline/images",
  [string]$ComposeFile = "docker-compose.yml",
  [string]$ExtraComposeFile = "docker-compose.offline.yml",
  [switch]$IncludeOllamaProfile
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Sanitize-FileName([string]$Image) {
  $name = $Image -replace "[/\\\\:]", "_"
  $name = $name -replace "[^a-zA-Z0-9_.-]", "_"
  return $name
}

Ensure-Dir $OutputDir

$composeArgs = @("-f", $ComposeFile)
if (Test-Path $ExtraComposeFile) {
  $composeArgs += @("-f", $ExtraComposeFile)
}
if ($IncludeOllamaProfile) {
  $composeArgs += @("--profile", "with-ollama")
}

Write-Host "Collecting images from docker compose config..."
$images = (& docker compose @composeArgs config --images) | Where-Object { $_ -and $_.Trim() } | Sort-Object -Unique

if (-not $images -or $images.Count -eq 0) {
  throw "No images found from compose config. Check $ComposeFile."
}

Write-Host "Found $($images.Count) images:"
$images | ForEach-Object { Write-Host "  - $_" }

$manifest = @()
foreach ($image in $images) {
  Write-Host ""
  Write-Host "Exporting image: $image"

  $inspect = & docker image inspect $image 2>$null | ConvertFrom-Json
  if (-not $inspect) {
    throw "Image not found locally: $image. Build/pull it first, then re-run export."
  }

  $fileBase = Sanitize-FileName $image
  $tarPath = Join-Path $OutputDir "$fileBase.tar"

  Write-Host "  -> docker save $image"
  & docker save -o $tarPath $image | Out-Null

  $hash = (Get-FileHash -Algorithm SHA256 -Path $tarPath).Hash.ToLowerInvariant()
  $sizeBytes = (Get-Item $tarPath).Length

  $manifest += [pscustomobject]@{
    image      = $image
    imageId    = $inspect[0].Id
    created    = $inspect[0].Created
    tarFile    = (Split-Path -Leaf $tarPath)
    sha256     = $hash
    sizeBytes  = $sizeBytes
  }

  Write-Host "  -> saved: $tarPath"
  Write-Host "  -> sha256: $hash"
}

$manifestPath = Join-Path $OutputDir "manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $manifestPath

Write-Host ""
Write-Host "Done."
Write-Host "Images exported to: $OutputDir"
Write-Host "Manifest: $manifestPath"

