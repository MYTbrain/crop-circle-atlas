param(
  [switch]$Refresh
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Raw = Join-Path $Repo 'data\raw'
$SnapshotPath = Join-Path $Repo 'data\source_snapshots.csv'
$RetrievedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http
$Client = [Net.Http.HttpClient]::new()
$Client.DefaultRequestHeaders.UserAgent.ParseAdd('CropCircleAtlas/0.1 (+research catalog; respectful crawl)')
$Snapshots = [System.Collections.Generic.List[object]]::new()

function Get-Sha256([byte[]]$Bytes) {
  $Hasher = [Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
  finally { $Hasher.Dispose() }
}

function Get-Source([string]$Url, [string]$RelativePath, [int]$DelayMs = 180) {
  $Path = Join-Path $Raw $RelativePath
  $Parent = Split-Path -Parent $Path
  [IO.Directory]::CreateDirectory($Parent) | Out-Null
  $Status = 0
  $Bytes = $null
  if ((Test-Path -LiteralPath $Path) -and -not $Refresh) {
    $Bytes = [IO.File]::ReadAllBytes($Path)
    $Status = 200
  } else {
    try {
      $Response = $Client.GetAsync($Url).GetAwaiter().GetResult()
      $Status = [int]$Response.StatusCode
      if ($Response.IsSuccessStatusCode) {
        $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        [IO.File]::WriteAllBytes($Path, $Bytes)
      }
    } catch {
      $Status = -1
    }
    if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
  }
  if ($null -ne $Bytes) {
    $Snapshots.Add([pscustomobject]@{
      url = $Url
      retrieved_at = $RetrievedAt
      http_status = $Status
      sha256 = Get-Sha256 $Bytes
      bytes = $Bytes.Length
      cache_path = $RelativePath.Replace('\', '/')
    })
  }
  return $Path
}

try {
  Get-Source 'https://www.cropcirclecenter.com/' 'cropcirclecenter\index.html' | Out-Null
  for ($Year = 2010; $Year -le [DateTime]::UtcNow.Year; $Year++) {
    # Month 13 is the archive's explicit "unknown date" bucket.
    for ($Month = 1; $Month -le 13; $Month++) {
      $Ym = '{0}{1:00}' -f $Year, $Month
      $Url = "https://www.cropcirclecenter.com/date/$Year/$Ym.html"
      Get-Source $Url "cropcirclecenter\date\$Year\$Ym.html" | Out-Null
    }
  }

  $IccraIndex = Get-Source 'https://iccra.org/byyear/usaformations-byyear.htm' 'iccra\usaformations-byyear.htm'
  Get-Source 'https://iccra.org/reports.htm' 'iccra\reports.htm' | Out-Null
  $IndexHtml = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($IccraIndex))
  $Hrefs = [regex]::Matches($IndexHtml, 'href\s*=\s*["'']([^"'']+)["'']', 'IgnoreCase') |
    ForEach-Object { $_.Groups[1].Value } |
    Where-Object { $_ -match 'ICCRA[_ -]*\d{4}\.(html?|HTML?)$' } |
    Sort-Object -Unique
  $Base = [Uri]'https://iccra.org/byyear/usaformations-byyear.htm'
  foreach ($Href in $Hrefs) {
    $Resolved = [Uri]::new($Base, $Href).AbsoluteUri
    $Name = [IO.Path]::GetFileName(([Uri]$Resolved).LocalPath)
    Get-Source $Resolved "iccra\byyear\$Name" | Out-Null
  }

  for ($Year = 2014; $Year -le [DateTime]::UtcNow.Year; $Year++) {
    Get-Source "https://cropcircleconnector.com/$Year/$Year.html" "connector\$Year\index.html" | Out-Null
  }
  Get-Source 'https://www.cropcircleconnector.com/anasazi/ImageUsePolicy2004.html' 'connector\image-use-policy.html' | Out-Null
  Get-Source 'https://www.dcca.nl/dcca.htm' 'discovery\dcca.html' | Out-Null
  Get-Source 'https://www.bltresearch.com/labreports.php' 'discovery\blt-lab-reports.html' | Out-Null
  Get-Source 'https://www.vigay.com/cropcircles/articles/index.html' 'discovery\vigay-articles.html' | Out-Null
  Get-Source 'https://www.ufobc.ca/Supernatural/Cropcircles/cccrnnews.htm' 'discovery\cccrn-news.html' | Out-Null
  Get-Source 'https://circleresearcharchive.com/mast/the-database/' 'discovery\circle-research-archive.html' | Out-Null
  Get-Source 'https://cropdecoder.com/' 'discovery\cropdecoder.html' | Out-Null

  Get-Source 'https://download.geonames.org/export/dump/cities500.zip' 'geonames\cities500.zip' 0 | Out-Null
  Get-Source 'https://download.geonames.org/export/dump/US.zip' 'geonames\US.zip' 0 | Out-Null
  Get-Source 'https://download.geonames.org/export/dump/admin1CodesASCII.txt' 'geonames\admin1CodesASCII.txt' 0 | Out-Null
  Get-Source 'https://download.geonames.org/export/dump/countryInfo.txt' 'geonames\countryInfo.txt' 0 | Out-Null

  $GeoDir = Join-Path $Raw 'geonames'
  foreach ($ZipName in @('cities500.zip', 'US.zip')) {
    $ZipPath = Join-Path $GeoDir $ZipName
    $Dest = Join-Path $GeoDir ([IO.Path]::GetFileNameWithoutExtension($ZipName))
    if ((Test-Path $ZipPath) -and ((-not (Test-Path $Dest)) -or $Refresh)) {
      if (Test-Path $Dest) { Remove-Item -LiteralPath $Dest -Recurse -Force }
      Expand-Archive -LiteralPath $ZipPath -DestinationPath $Dest -Force
    }
  }

  [IO.Directory]::CreateDirectory((Split-Path -Parent $SnapshotPath)) | Out-Null
  $Snapshots | Sort-Object url | Export-Csv -LiteralPath $SnapshotPath -NoTypeInformation -Encoding UTF8
  Write-Output ("snapshots={0}" -f $Snapshots.Count)
} finally {
  $Client.Dispose()
}
