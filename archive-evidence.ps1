# archive-evidence.ps1 - freeze this event's public records into the Internet Archive
#
# Why: the official scoreboard host (2026.faustctf.net) is expected to go away after
# the event, and a self-hosted claim proves little. Third-party timestamped snapshots
# of *organizer-owned* pages are the strongest durable evidence.
#
# Re-run this whenever something changes - in particular AFTER you join the CTFtime
# team, so that the snapshot captures your name in the member list.
#
# Usage:
#   .\archive-evidence.ps1              # save everything
#   .\archive-evidence.ps1 -Check       # only report which URLs already have snapshots
#
# NOTE FOR MAINTAINERS: keep this file ASCII-only (Windows PowerShell 5.1 reads a
# BOM-less .ps1 as ANSI and will mangle non-ASCII characters).

[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

# Ordered by evidential value: organizer data first, self-published material last.
$Targets = @(
    @{ Url = 'https://2026.faustctf.net/competition/scoreboard.json'; What = 'official frozen scoreboard (raw JSON)' }
    @{ Url = 'https://2026.faustctf.net/competition/teams.json';      What = 'official teams + flag_ids' }
    @{ Url = 'https://2026.faustctf.net/competition/scoreboard/';     What = 'official scoreboard page' }
    @{ Url = 'https://ctftime.org/event/3312';                        What = 'CTFtime event' }
    @{ Url = 'https://ctftime.org/event/3312/tasks/';                 What = 'CTFtime event tasks' }
    @{ Url = 'https://ctftime.org/team/449998';                       What = 'CTFtime team (join it first!)' }
    @{ Url = 'https://github.com/nnn493368-max/faust-ctf-2026-writeups'; What = 'our writeups repo' }
)

# Also archive the CURRENT COMMIT, pinned by SHA. A branch URL (/tree/main) changes
# on every push while the Internet Archive de-duplicates per URL, so a branch snapshot
# is always one or two commits stale. A commit URL is immutable - no such problem.
$RepoBase = 'https://github.com/nnn493368-max/faust-ctf-2026-writeups'
$head = (& git -C $PSScriptRoot rev-parse HEAD 2>$null | Out-String).Trim()
if ($head) {
    $Targets += @{ Url = "$RepoBase/tree/$head";       What = "repo at commit $($head.Substring(0,7)) (immutable)" }
    $Targets += @{ Url = "$RepoBase/blob/$head/EVIDENCE.md"; What = 'EVIDENCE.md at that commit' }
}

function Get-Snapshot($url) {
    # Use the CDX API, not the availability API: the latter is served from a cache
    # and keeps reporting "[none]" for minutes after a successful fresh save.
    $api = 'https://web.archive.org/cdx/search/cdx?url=' + [uri]::EscapeDataString($url) +
           '&output=json&limit=-1&fl=timestamp,statuscode'
    try {
        $j = (Invoke-WebRequest -Uri $api -UseBasicParsing -TimeoutSec 60).Content | ConvertFrom-Json
        if ($j.Count -gt 1) {
            $last = $j[$j.Count - 1]
            return [pscustomobject]@{ timestamp = $last[0]; statuscode = $last[1] }
        }
    } catch { }
    return $null
}

Write-Host ''
Write-Host '=== Wayback status ===' -ForegroundColor Cyan

foreach ($t in $Targets) {
    $snap = Get-Snapshot $t.Url
    if ($snap) {
        Write-Host ('  [have] {0}  {1}' -f $snap.timestamp, $t.Url)
        Write-Host ('         {0}' -f $snap.url) -ForegroundColor DarkGray
    } else {
        Write-Host ('  [none] {0}' -f $t.Url) -ForegroundColor Yellow
    }
}

if ($Check) { Write-Host ''; exit 0 }

Write-Host ''
Write-Host '=== Saving fresh snapshots ===' -ForegroundColor Cyan
Write-Host '  (Save Page Now is rate limited; this can take a minute per URL)'
Write-Host ''

$results = @()
foreach ($t in $Targets) {
    Write-Host ('  saving: {0}  ({1})' -f $t.Url, $t.What)
    $stamp = $null
    try {
        $r = Invoke-WebRequest -Uri ('https://web.archive.org/save/' + $t.Url) `
                               -UseBasicParsing -TimeoutSec 180 -MaximumRedirection 5
        $final = $r.BaseResponse.ResponseUri.ToString()
        if ($final -match '/web/(\d{14})/') { $stamp = $matches[1] }
        if (-not $stamp) { $stamp = 'submitted' }
        Write-Host ('    ok  {0}' -f $stamp) -ForegroundColor Green
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            Write-Host ('    HTTP {0}' -f [int]$resp.StatusCode) -ForegroundColor Yellow
            $stamp = 'http-' + [int]$resp.StatusCode
        } else {
            Write-Host ('    ERR {0}' -f $_.Exception.Message.Split([char]10)[0]) -ForegroundColor Red
            $stamp = 'error'
        }
    }
    $results += [pscustomobject]@{ Url = $t.Url; Stamp = $stamp; What = $t.What }
    Start-Sleep -Seconds 3
}

Write-Host ''
Write-Host '=== Result ===' -ForegroundColor Cyan
Write-Host ''
Write-Host ('  {0,-14} {1}' -f 'TIMESTAMP', 'URL')
foreach ($r in $results) {
    Write-Host ('  {0,-14} {1}' -f $r.Stamp, $r.Url)
}

Write-Host ''
Write-Host '  Next: paste the new timestamps into EVIDENCE.md (the "archive" lines),' -ForegroundColor Yellow
Write-Host '  then commit and push so the repo snapshot stays consistent.' -ForegroundColor Yellow
Write-Host ''

# Handy direct links for the two that matter most.
foreach ($r in $results) {
    if ($r.Stamp -match '^\d{14}$' -and $r.Url -match 'scoreboard\.json|team/449998') {
        Write-Host ('  {0}' -f $r.Url)
        Write-Host ('    https://web.archive.org/web/{0}id_/{1}' -f $r.Stamp, $r.Url) -ForegroundColor Green
    }
}
Write-Host ''
