param(
  [switch]$Refresh,
  [ValidateRange(0, 5000)]
  [int]$DelayMs = 200
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$RawRoot = Join-Path $Repo 'data\raw\iccra_full'
$ObjectRoot = Join-Path $RawRoot 'objects'
$SnapshotPath = Join-Path $Repo 'data\iccra_snapshots_full.csv'
$EdgePath = Join-Path $Repo 'data\iccra_crawl_edges_full.csv'
$RunRetrievedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$UserAgent = 'CropCircleAtlas/1.0 (+public research dataset; respectful archival crawl)'

[IO.Directory]::CreateDirectory($ObjectRoot) | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.Web

$Client = [Net.Http.HttpClient]::new()
$Client.Timeout = [TimeSpan]::FromSeconds(45)
$Client.DefaultRequestHeaders.UserAgent.ParseAdd($UserAgent)
$Entries = @{}
$Edges = [System.Collections.Generic.List[object]]::new()
$Prior = @{}

if ((Test-Path -LiteralPath $SnapshotPath) -and -not $Refresh) {
  foreach ($Row in (Import-Csv -LiteralPath $SnapshotPath)) {
    $Prior[$Row.url] = $Row
  }
}

function Get-Sha256Bytes([byte[]]$Bytes) {
  $Hasher = [Security.Cryptography.SHA256]::Create()
  try {
    return ([BitConverter]::ToString($Hasher.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant()
  } finally {
    $Hasher.Dispose()
  }
}

function Get-Sha256Text([string]$Text) {
  return Get-Sha256Bytes ([Text.Encoding]::UTF8.GetBytes($Text))
}

function ConvertTo-CanonicalUrl([string]$Url, [string]$BaseUrl = '') {
  if ([string]::IsNullOrWhiteSpace($Url)) { return $null }
  $Decoded = [Web.HttpUtility]::HtmlDecode($Url.Trim())
  if ($Decoded -match '^(?i)(mailto|javascript|data|tel):') { return $null }
  try {
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
      $Uri = [Uri]$Decoded
    } else {
      $Uri = [Uri]::new([Uri]$BaseUrl, $Decoded)
    }
  } catch {
    return $null
  }
  if ($Uri.Scheme -notin @('http', 'https')) { return $null }
  $HostName = $Uri.DnsSafeHost.ToLowerInvariant()
  if ($HostName -eq 'www.iccra.org') { $HostName = 'iccra.org' }
  if ($HostName -ne 'iccra.org') { return $null }
  $PathAndQuery = $Uri.GetComponents(
    [UriComponents]::PathAndQuery,
    [UriFormat]::UriEscaped
  )
  if (-not $PathAndQuery.StartsWith('/')) { $PathAndQuery = '/' + $PathAndQuery }
  return 'https://iccra.org' + $PathAndQuery
}

function Get-CacheExtension([string]$Url, [string]$ContentType = '') {
  try { $Extension = [IO.Path]::GetExtension(([Uri]$Url).AbsolutePath).ToLowerInvariant() }
  catch { $Extension = '' }
  if ($Extension -in @('.htm', '.html', '.pdf', '.gif', '.jpg', '.jpeg', '.png', '.txt')) {
    return $Extension
  }
  if ($ContentType -match '(?i)html') { return '.html' }
  if ($ContentType -match '(?i)pdf') { return '.pdf' }
  if ($ContentType -match '(?i)image/jpeg') { return '.jpg' }
  if ($ContentType -match '(?i)image/png') { return '.png' }
  if ($ContentType -match '(?i)image/gif') { return '.gif' }
  if ($ContentType -match '(?i)text/plain') { return '.txt' }
  return '.bin'
}

function ConvertTo-RepoRelativePath([string]$Path) {
  $FullRepo = [IO.Path]::GetFullPath($Repo).TrimEnd('\')
  $FullPath = [IO.Path]::GetFullPath($Path)
  if (-not $FullPath.StartsWith($FullRepo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Cache path is outside the repository: $FullPath"
  }
  return $FullPath.Substring($FullRepo.Length + 1).Replace('\', '/')
}

function Register-Url(
  [string]$Url,
  [string]$Role,
  [string]$DiscoveredFrom = '',
  [string]$AnchorText = ''
) {
  $Canonical = ConvertTo-CanonicalUrl $Url $DiscoveredFrom
  if ($null -eq $Canonical) { return $null }
  if (-not $Entries.ContainsKey($Canonical)) {
    $Entries[$Canonical] = [ordered]@{
      url = $Canonical
      roles = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
      discovered_from = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
      anchor_text = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
      http_status = ''
      retrieved_at = ''
      sha256 = ''
      bytes = 0
      cache_path = ''
      content_type = ''
      error = ''
    }
  }
  $Entry = $Entries[$Canonical]
  if (-not [string]::IsNullOrWhiteSpace($Role)) { $Entry.roles.Add($Role) | Out-Null }
  if (-not [string]::IsNullOrWhiteSpace($DiscoveredFrom)) {
    $Entry.discovered_from.Add($DiscoveredFrom) | Out-Null
  }
  if (-not [string]::IsNullOrWhiteSpace($AnchorText)) {
    $Entry.anchor_text.Add(($AnchorText -replace '\s+', ' ').Trim()) | Out-Null
  }
  if (-not [string]::IsNullOrWhiteSpace($DiscoveredFrom)) {
    $Edges.Add([pscustomobject]@{
      discovered_from = $DiscoveredFrom
      url = $Canonical
      role = $Role
      anchor_text = ($AnchorText -replace '\s+', ' ').Trim()
    })
  }
  return $Canonical
}

function Get-EntryCachePath([Collections.IDictionary]$Entry) {
  if (-not [string]::IsNullOrWhiteSpace([string]$Entry.cache_path)) {
    return Join-Path $Repo ([string]$Entry.cache_path).Replace('/', '\')
  }
  $PriorRow = $Prior[[string]$Entry.url]
  if ($null -ne $PriorRow -and -not [string]::IsNullOrWhiteSpace($PriorRow.cache_path)) {
    return Join-Path $Repo $PriorRow.cache_path.Replace('/', '\')
  }
  $Stem = Get-Sha256Text ([string]$Entry.url)
  $Extension = Get-CacheExtension ([string]$Entry.url)
  return Join-Path $ObjectRoot ($Stem + $Extension)
}

function Fetch-Url([string]$Url) {
  $Entry = $Entries[$Url]
  if ($null -eq $Entry) { throw "URL is not registered: $Url" }
  $Path = Get-EntryCachePath $Entry
  $PriorRow = $Prior[$Url]
  if ((Test-Path -LiteralPath $Path) -and -not $Refresh) {
    $Bytes = [IO.File]::ReadAllBytes($Path)
    $Entry.http_status = if ($null -ne $PriorRow -and $PriorRow.http_status -match '^2\d\d$') {
      $PriorRow.http_status
    } else { '200' }
    $Entry.retrieved_at = if ($null -ne $PriorRow) { $PriorRow.retrieved_at } else {
      ([IO.File]::GetLastWriteTimeUtc($Path)).ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    $Entry.sha256 = Get-Sha256Bytes $Bytes
    $Entry.bytes = $Bytes.Length
    $Entry.cache_path = ConvertTo-RepoRelativePath $Path
    $Entry.content_type = if ($null -ne $PriorRow) { $PriorRow.content_type } else { '' }
    return $Path
  }

  try {
    $Response = $Client.GetAsync($Url).GetAwaiter().GetResult()
    $Entry.http_status = [int]$Response.StatusCode
    $Entry.retrieved_at = $RunRetrievedAt
    $Entry.content_type = [string]$Response.Content.Headers.ContentType
    if ($Response.IsSuccessStatusCode) {
      $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
      $DesiredExtension = Get-CacheExtension $Url $Entry.content_type
      $Path = Join-Path $ObjectRoot ((Get-Sha256Text $Url) + $DesiredExtension)
      [IO.File]::WriteAllBytes($Path, $Bytes)
      $Entry.sha256 = Get-Sha256Bytes $Bytes
      $Entry.bytes = $Bytes.Length
      $Entry.cache_path = ConvertTo-RepoRelativePath $Path
    }
  } catch {
    $Entry.http_status = '-1'
    $Entry.retrieved_at = $RunRetrievedAt
    $Entry.error = $_.Exception.GetBaseException().Message
  }
  if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
  if (Test-Path -LiteralPath $Path) { return $Path }
  return $null
}

function Get-Html([string]$Url) {
  $Entry = $Entries[$Url]
  if ($null -eq $Entry -or [string]::IsNullOrWhiteSpace([string]$Entry.cache_path)) { return '' }
  $Path = Join-Path $Repo $Entry.cache_path.Replace('/', '\')
  if (-not (Test-Path -LiteralPath $Path)) { return '' }
  $Bytes = [IO.File]::ReadAllBytes($Path)
  # ICCRA's legacy pages mix ISO-8859-1 and Windows-1252 declarations. Hrefs
  # are ASCII-compatible under both encodings; Windows-1252 preserves smart punctuation.
  return [Text.Encoding]::GetEncoding(1252).GetString($Bytes)
}

function Get-PageLinks([string]$Url) {
  $Html = Get-Html $Url
  $Rows = [System.Collections.Generic.List[object]]::new()
  if ([string]::IsNullOrWhiteSpace($Html)) { return $Rows }
  $Pattern = '<a\b(?<pre>[^>]*?)\bhref\s*=\s*(?:"(?<dq>[^"]*)"|''(?<sq>[^'']*)''|(?<uq>[^\s>]+))(?<post>[^>]*)>(?<body>.*?)</a\s*>'
  foreach ($Match in [regex]::Matches($Html, $Pattern, 'IgnoreCase,Singleline')) {
    $Href = $Match.Groups['dq'].Value
    if ([string]::IsNullOrEmpty($Href)) { $Href = $Match.Groups['sq'].Value }
    if ([string]::IsNullOrEmpty($Href)) { $Href = $Match.Groups['uq'].Value }
    $Body = [regex]::Replace($Match.Groups['body'].Value, '<[^>]+>', ' ')
    $Text = [Web.HttpUtility]::HtmlDecode(($Body -replace '\s+', ' ').Trim())
    $Resolved = ConvertTo-CanonicalUrl $Href $Url
    $Rows.Add([pscustomobject]@{ href = $Href; url = $Resolved; text = $Text })
  }
  return $Rows
}

function Test-UiImage([string]$Url) {
  if ([string]::IsNullOrWhiteSpace($Url)) { return $true }
  $Name = [IO.Path]::GetFileName(([Uri]$Url).AbsolutePath).ToLowerInvariant()
  $Stem = [IO.Path]::GetFileNameWithoutExtension($Name)
  if ($Stem -match '^(?:iccraheader|line|smcc|bbcc|mbcc|spacer|blank|clear|clearpixel)$') { return $true }
  if ($Stem -match '^(?:next|prev|previous|back|forward|up|home)(?:[_-]?(?:button|arrow|page))?$') { return $true }
  return $false
}

function Get-PageImages([string]$Url) {
  $Html = Get-Html $Url
  $Rows = [System.Collections.Generic.List[object]]::new()
  if ([string]::IsNullOrWhiteSpace($Html)) { return $Rows }
  $Seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $ImgPattern = '<img\b(?<attrs>[^>]*)>'
  foreach ($Match in [regex]::Matches($Html, $ImgPattern, 'IgnoreCase,Singleline')) {
    $Attrs = $Match.Groups['attrs'].Value
    $SrcMatch = [regex]::Match($Attrs, '\bsrc\s*=\s*(?:"(?<dq>[^"]*)"|''(?<sq>[^'']*)''|(?<uq>[^\s>]+))', 'IgnoreCase')
    if (-not $SrcMatch.Success) { continue }
    $Src = $SrcMatch.Groups['dq'].Value
    if ([string]::IsNullOrEmpty($Src)) { $Src = $SrcMatch.Groups['sq'].Value }
    if ([string]::IsNullOrEmpty($Src)) { $Src = $SrcMatch.Groups['uq'].Value }
    $Resolved = ConvertTo-CanonicalUrl $Src $Url
    if ($null -eq $Resolved -or (Test-UiImage $Resolved) -or -not $Seen.Add($Resolved)) { continue }
    $AltMatch = [regex]::Match($Attrs, '\balt\s*=\s*(?:"(?<dq>[^"]*)"|''(?<sq>[^'']*)'')', 'IgnoreCase')
    $Alt = $AltMatch.Groups['dq'].Value
    if ([string]::IsNullOrEmpty($Alt)) { $Alt = $AltMatch.Groups['sq'].Value }
    $Rows.Add([pscustomobject]@{ url = $Resolved; text = [Web.HttpUtility]::HtmlDecode($Alt); kind = 'embedded' })
  }
  foreach ($Link in (Get-PageLinks $Url)) {
    if ($null -ne $Link.url -and ([Uri]$Link.url).AbsolutePath -match '(?i)\.(?:jpg|jpeg|png|gif)$' -and
        -not (Test-UiImage $Link.url) -and $Seen.Add($Link.url)) {
      $Rows.Add([pscustomobject]@{ url = $Link.url; text = $Link.text; kind = 'linked' })
    }
  }
  return $Rows
}

function Fetch-Registered([string]$Url, [string]$Role, [string]$From = '', [string]$Text = '') {
  $Canonical = Register-Url $Url $Role $From $Text
  if ($null -ne $Canonical) { Fetch-Url $Canonical | Out-Null }
  return $Canonical
}

function Test-HtmlOrPdfPath([string]$Url) {
  if ([string]::IsNullOrWhiteSpace($Url)) { return $false }
  return ([Uri]$Url).AbsolutePath -match '(?i)(\.html?|\.pdf|/index\.htm)$'
}

try {
  $Robots = Fetch-Registered 'https://iccra.org/robots.txt' 'robots'
  $RobotsText = Get-Html $Robots
  if ($RobotsText -notmatch '(?im)^\s*Allow\s*:\s*/\s*$') {
    throw ("ICCRA robots.txt did not explicitly allow the site root; crawl stopped closed (url={0}, decoded_bytes={1})." -f $Robots, $RobotsText.Length)
  }

  $Landing = Fetch-Registered 'https://iccra.org/usaformations.htm' 'formation_landing'
  $ByYear = Fetch-Registered 'https://iccra.org/byyear/usaformations-byyear.htm' 'byyear_index'
  $ByState = Fetch-Registered 'https://iccra.org/bystate/usaformations-bystate.htm' 'bystate_index'
  $Reports = Fetch-Registered 'https://iccra.org/reports.htm' 'reports_index'
  $Historical = Fetch-Registered 'https://iccra.org/reports/historical_reports.htm' 'historical_index'
  $NewsRoot = Fetch-Registered 'https://iccra.org/news.htm' 'news_index'

  $YearIndexes = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $StateIndexes = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $DetailPages = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $NewsIndexes = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $ReportDocuments = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $HistoricalAssets = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $ImageAssets = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

  foreach ($Link in (Get-PageLinks $ByYear)) {
    if ($null -eq $Link.url) { continue }
    $Path = ([Uri]$Link.url).AbsolutePath
    if ($Path -match '(?i)^/byyear/ICCRA_\d{4}\.(?:htm|html)$') {
      Register-Url $Link.url 'year_index' $ByYear $Link.text | Out-Null
      $YearIndexes.Add($Link.url) | Out-Null
    } elseif ($Path -match '(?i)^/byyear/ICCRA_\d{4}_.+\.(?:htm|html)$' -or
              $Path -match '(?i)^/bystate/.+\.(?:htm|html)$') {
      Register-Url $Link.url 'formation_detail' $ByYear $Link.text | Out-Null
      $DetailPages.Add($Link.url) | Out-Null
    } elseif ($Path -match '(?i)^/news(?:-\d{4})?\.html?$') {
      Register-Url $Link.url 'news_index' $ByYear $Link.text | Out-Null
      $NewsIndexes.Add($Link.url) | Out-Null
    }
  }

  foreach ($Link in (Get-PageLinks $ByState)) {
    if ($null -eq $Link.url) { continue }
    if (([Uri]$Link.url).AbsolutePath -match '(?i)^/bystate/.+/ICCRA_[A-Za-z]+\.(?:htm|html)$') {
      Register-Url $Link.url 'state_index' $ByState $Link.text | Out-Null
      $StateIndexes.Add($Link.url) | Out-Null
    }
  }

  foreach ($Url in @($YearIndexes)) { Fetch-Url $Url | Out-Null }
  foreach ($Url in @($StateIndexes)) { Fetch-Url $Url | Out-Null }

  foreach ($IndexUrl in @($YearIndexes)) {
    foreach ($Link in (Get-PageLinks $IndexUrl)) {
      if ($null -eq $Link.url) { continue }
      $Path = ([Uri]$Link.url).AbsolutePath
      if (($Path -match '(?i)^/bystate/.+\.(?:htm|html)$') -or
          ($Path -match '(?i)^/byyear/ICCRA_\d{4}_.+\.(?:htm|html)$')) {
        Register-Url $Link.url 'formation_detail' $IndexUrl $Link.text | Out-Null
        $DetailPages.Add($Link.url) | Out-Null
      }
    }
  }

  foreach ($IndexUrl in @($StateIndexes)) {
    foreach ($Link in (Get-PageLinks $IndexUrl)) {
      if ($null -eq $Link.url) { continue }
      $Path = ([Uri]$Link.url).AbsolutePath
      if ($Path -match '(?i)^/bystate/[^/]+/.+' -and (Test-HtmlOrPdfPath $Link.url) -and
          $Link.url -ne $IndexUrl) {
        Register-Url $Link.url 'formation_detail' $IndexUrl $Link.text | Out-Null
        $DetailPages.Add($Link.url) | Out-Null
      }
    }
  }

  $NewsIndexes.Add($NewsRoot) | Out-Null
  foreach ($Link in (Get-PageLinks $NewsRoot)) {
    if ($null -ne $Link.url -and ([Uri]$Link.url).AbsolutePath -match '(?i)^/news-\d{4}\.html?$') {
      Register-Url $Link.url 'news_index' $NewsRoot $Link.text | Out-Null
      $NewsIndexes.Add($Link.url) | Out-Null
    }
  }
  # Follow the archive footer one level from every discovered news page. This
  # captures 2009-2015 without guessing which archive years exist.
  $NewsQueue = [Collections.Generic.Queue[string]]::new()
  foreach ($Url in @($NewsIndexes)) { $NewsQueue.Enqueue($Url) }
  $NewsVisited = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  while ($NewsQueue.Count -gt 0) {
    $NewsUrl = $NewsQueue.Dequeue()
    if (-not $NewsVisited.Add($NewsUrl)) { continue }
    Fetch-Url $NewsUrl | Out-Null
    foreach ($Link in (Get-PageLinks $NewsUrl)) {
      if ($null -eq $Link.url) { continue }
      $Path = ([Uri]$Link.url).AbsolutePath
      if ($Path -match '(?i)^/news-\d{4}\.html?$') {
        Register-Url $Link.url 'news_index' $NewsUrl $Link.text | Out-Null
        if ($NewsIndexes.Add($Link.url)) { $NewsQueue.Enqueue($Link.url) }
      } elseif (($Path -match '(?i)^/bystate/.+\.(?:htm|html)$') -or
                ($Path -match '(?i)^/ICCRA.+\.(?:htm|html)$')) {
        Register-Url $Link.url 'formation_detail' $NewsUrl $Link.text | Out-Null
        $DetailPages.Add($Link.url) | Out-Null
      }
    }
  }

  foreach ($Link in (Get-PageLinks $Reports)) {
    if ($null -eq $Link.url) { continue }
    $Path = ([Uri]$Link.url).AbsolutePath
    if ($Path -match '(?i)^/reports/.+\.(?:htm|html|pdf)$' -and
        $Path -notmatch '(?i)/historical_reports\.htm$') {
      Register-Url $Link.url 'report_document' $Reports $Link.text | Out-Null
      $ReportDocuments.Add($Link.url) | Out-Null
    }
  }

  foreach ($Link in (Get-PageLinks $Historical)) {
    if ($null -eq $Link.url) { continue }
    $Path = ([Uri]$Link.url).AbsolutePath
    if ($Path -match '(?i)^/(?:Historical%20Research|Historical Research)/.+\.(?:pdf|gif|jpg|jpeg|png)$' -or
        $Path -match '(?i)^/images/Original_Mowing_Devil_1678\.gif$') {
      Register-Url $Link.url 'historical_evidence' $Historical $Link.text | Out-Null
      $HistoricalAssets.Add($Link.url) | Out-Null
    }
  }

  foreach ($Url in @($DetailPages)) { Fetch-Url $Url | Out-Null }
  foreach ($Url in @($ReportDocuments)) { Fetch-Url $Url | Out-Null }
  foreach ($Url in @($HistoricalAssets)) { Fetch-Url $Url | Out-Null }

  # Formation pages sometimes point to a more complete ICCRA-hosted PDF. Fetch
  # those documents, but deliberately do not bulk-download linked photographs.
  foreach ($DetailUrl in @($DetailPages)) {
    foreach ($Link in (Get-PageLinks $DetailUrl)) {
      if ($null -eq $Link.url) { continue }
      if (([Uri]$Link.url).AbsolutePath -match '(?i)\.pdf$') {
        $Pdf = Register-Url $Link.url 'formation_supporting_document' $DetailUrl $Link.text
        if ($null -ne $Pdf -and -not $ReportDocuments.Contains($Pdf)) {
          $ReportDocuments.Add($Pdf) | Out-Null
          Fetch-Url $Pdf | Out-Null
        }
      }
    }
  }

  # Preserve formation imagery as private raw research cache only. Public
  # redistribution remains prohibited until each asset's rights are reviewed.
  $ImageSourcePages = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  foreach ($Url in @($DetailPages)) { $ImageSourcePages.Add($Url) | Out-Null }
  foreach ($Url in @($StateIndexes)) { $ImageSourcePages.Add($Url) | Out-Null }
  foreach ($Url in @($NewsIndexes)) { $ImageSourcePages.Add($Url) | Out-Null }
  foreach ($Url in @($ReportDocuments)) {
    if (([Uri]$Url).AbsolutePath -match '(?i)\.html?$') { $ImageSourcePages.Add($Url) | Out-Null }
  }
  foreach ($SourceUrl in @($ImageSourcePages)) {
    foreach ($Image in (Get-PageImages $SourceUrl)) {
      $Role = if ($DetailPages.Contains($SourceUrl)) { 'formation_image' } else { 'archive_image' }
      $ImageUrl = Register-Url $Image.url $Role $SourceUrl ((@($Image.kind, $Image.text) -join ': ').Trim())
      if ($null -ne $ImageUrl) { $ImageAssets.Add($ImageUrl) | Out-Null }
    }
  }
  foreach ($Url in @($ImageAssets)) { Fetch-Url $Url | Out-Null }

  $SnapshotRows = foreach ($Key in ($Entries.Keys | Sort-Object)) {
    $Entry = $Entries[$Key]
    [pscustomobject]@{
      url = $Entry.url
      roles = (@($Entry.roles) | Sort-Object) -join ';'
      discovered_from = (@($Entry.discovered_from) | Sort-Object) -join ';'
      anchor_text = (@($Entry.anchor_text) | Sort-Object) -join ' | '
      retrieved_at = $Entry.retrieved_at
      http_status = $Entry.http_status
      sha256 = $Entry.sha256
      bytes = $Entry.bytes
      cache_path = $Entry.cache_path
      content_type = $Entry.content_type
      error = $Entry.error
    }
  }
  $SnapshotRows | Export-Csv -LiteralPath $SnapshotPath -NoTypeInformation -Encoding UTF8
  $Edges | Sort-Object discovered_from, url, role, anchor_text -Unique |
    Export-Csv -LiteralPath $EdgePath -NoTypeInformation -Encoding UTF8

  $Successful = @($SnapshotRows | Where-Object { $_.http_status -match '^2\d\d$' }).Count
  $Failed = @($SnapshotRows | Where-Object { $_.http_status -notmatch '^2\d\d$' }).Count
  Write-Output ('iccra_urls={0} successful={1} failed={2} year_indexes={3} state_indexes={4} formation_details={5} news_indexes={6} report_documents={7} historical_assets={8} images={9}' -f
    $SnapshotRows.Count, $Successful, $Failed, $YearIndexes.Count, $StateIndexes.Count,
    $DetailPages.Count, $NewsIndexes.Count, $ReportDocuments.Count, $HistoricalAssets.Count,
    $ImageAssets.Count)
} finally {
  $Client.Dispose()
}
