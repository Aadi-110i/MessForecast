# Fetch and self-host the Dusk theme typefaces (Wix Madefor Display / Text).
#
# The redesign adopts Hallmark's Dusk theme, whose type voice is Wix Madefor
# Display over Wix Madefor Text. This project ships a tablet that runs in a
# kitchen with no guaranteed internet, and the existing stylesheet deliberately
# fetched nothing from a CDN. Self-hosting keeps the theme's typography exact
# without putting the kitchen screen back on the network.
#
# Wix Madefor Display ships as a variable font: one file per subset carries
# every weight, so the script collapses identical downloads into a single
# file and declares the weight range on it. Wix Madefor Text ships as static
# faces, one file per weight.
#
# Usage:  powershell -File scripts/fetch_dusk_fonts.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$fontDir = Join-Path $root 'static\fonts'
$cssOut = Join-Path $root 'static\css\fonts.css'

$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
$url = 'https://fonts.googleapis.com/css2?family=Wix+Madefor+Display:wght@400;500;600&family=Wix+Madefor+Text:wght@400;500;600&display=swap'

New-Item -ItemType Directory -Force -Path $fontDir | Out-Null

Write-Host 'Fetching font manifest...'
$css = (Invoke-WebRequest -Uri $url -UserAgent $ua -UseBasicParsing -TimeoutSec 30).Content

# Google serves one @font-face per subset, each introduced by a /* subset */
# comment. Keep only latin and latin-ext: the interface is English, and the
# smaller payload is what a tablet has to hold in its cache.
$keep = @('latin', 'latin-ext')
$pattern = '/\*\s*([a-z\-]+)\s*\*/\s*(@font-face\s*\{[^}]*\})'
$matches = [regex]::Matches($css, $pattern)

$faces = New-Object System.Collections.Generic.List[object]

foreach ($m in $matches) {
    $subset = $m.Groups[1].Value
    if ($keep -notcontains $subset) { continue }
    $block = $m.Groups[2].Value

    $family = ([regex]::Match($block, "font-family:\s*'([^']+)'")).Groups[1].Value
    $weight = [int](([regex]::Match($block, 'font-weight:\s*(\d+)')).Groups[1].Value)
    $src = ([regex]::Match($block, 'url\((https://[^)]+\.woff2)\)')).Groups[1].Value
    $range = ([regex]::Match($block, 'unicode-range:\s*([^;]+);')).Groups[1].Value
    if (-not $family -or -not $src) { continue }

    $faces.Add([pscustomobject]@{
        Family  = $family
        Weight  = $weight
        Subset  = $subset
        Src     = $src
        Range   = $range
        Slug    = ''
        Hash    = ''
    })
}

# Download each file, then collapse identical ones onto a single @font-face
# with a weight range, which is what a variable font needs. The final filename
# can only be decided once the group is known, so every download lands in a
# temporary file first and is moved into place at the end.
$byHash = @{}
foreach ($f in $faces) {
    $temp = Join-Path $fontDir ('.tmp-' + [System.IO.Path]::GetFileName(([Uri]$f.Src).AbsolutePath))
    if (-not (Test-Path $temp)) {
        Write-Host "  downloading $($f.Family) $($f.Weight) $($f.Subset)"
        Invoke-WebRequest -Uri $f.Src -OutFile $temp -UseBasicParsing -TimeoutSec 60
    }
    $hash = (Get-FileHash $temp -Algorithm SHA256).Hash
    $key = "$($f.Family)|$($f.Subset)|$hash"

    if (-not $byHash.ContainsKey($key)) {
        $byHash[$key] = [pscustomobject]@{
            Family  = $f.Family
            Subset  = $f.Subset
            Range   = $f.Range
            Temp    = $temp
            Weights = New-Object System.Collections.Generic.List[int]
        }
    }
    $byHash[$key].Weights.Add($f.Weight)
}

# Name each group: a single weight keeps the weight in the filename, a
# variable range does not, because one file carries the whole range.
foreach ($g in $byHash.Values) {
    $lo = ($g.Weights | Measure-Object -Minimum).Minimum
    $hi = ($g.Weights | Measure-Object -Maximum).Maximum
    $slug = if ($lo -eq $hi) {
        ($g.Family -replace '\s+', '') + '-' + $lo + '-' + $g.Subset + '.woff2'
    } else {
        ($g.Family -replace '\s+', '') + '-' + $g.Subset + '.woff2'
    }
    $dest = Join-Path $fontDir $slug
    if (Test-Path $dest) { Remove-Item $dest -Force }
    Move-Item $g.Temp $dest -Force
    $g | Add-Member -NotePropertyName Slug -NotePropertyValue $slug
}

# Remove any stale download left over from an earlier run.
Get-ChildItem $fontDir -Filter '.tmp-*' -ErrorAction SilentlyContinue | Remove-Item -Force

$blocks = New-Object System.Collections.Generic.List[string]
foreach ($g in ($byHash.Values | Sort-Object Family, Subset)) {
    $lo = ($g.Weights | Measure-Object -Minimum).Minimum
    $hi = ($g.Weights | Measure-Object -Maximum).Maximum
    $weightDecl = if ($lo -eq $hi) { "$lo" } else { "$lo $hi" }
    $blocks.Add(@"
@font-face {
  font-family: '$($g.Family)';
  font-style: normal;
  font-weight: $weightDecl;
  font-display: swap;
  src: url('../fonts/$($g.Slug)') format('woff2');
  unicode-range: $($g.Range);
}
"@)
}

$header = @"
/* =========================================================================
   MessForecast - self-hosted typefaces
   -------------------------------------------------------------------------
   Wix Madefor Display and Wix Madefor Text, the type voice of Hallmark's Dusk
   theme, served from this origin so the kitchen tablet keeps working with no
   internet. Generated by scripts/fetch_dusk_fonts.ps1.
   ========================================================================= */
"@

# Written without a byte-order mark: a CSS file that starts with one is served
# with a stray U+FEFF ahead of the first rule by some static file servers.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($cssOut, ($header + "`n" + ($blocks -join "`n")), $utf8NoBom)
Write-Host "Wrote $cssOut with $($blocks.Count) faces and $($byHash.Count) font files."
