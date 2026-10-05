# publish.ps1 - one-shot publish of this repo to GitHub
#
# Prerequisite: run `gh auth login` once. Everything else (preflight, git identity,
# commit, repo creation, push) is handled here.
#
# Usage:
#   .\publish.ps1                                     # default repo name; prompts for identity if unset
#   .\publish.ps1 -RepoName my-writeups               # different repo name
#   .\publish.ps1 -Private                            # create a private repo first
#   .\publish.ps1 -GitName "Alice" -GitEmail "a@b.c"  # non-interactive identity
#
# NOTE FOR MAINTAINERS: keep this file ASCII-only, or save it as UTF-8 *with BOM*.
# Windows PowerShell 5.1 reads BOM-less .ps1 files as ANSI and mangles any
# non-ASCII character, which breaks parsing. (This bit us once already.)
#
# Do NOT set $ErrorActionPreference='Stop' here. gh and git write progress and
# diagnostics to stderr, and under 'Stop' PowerShell promotes that to a
# terminating error - the script would abort on a *successful* push.
# Every native call below is checked explicitly via $LASTEXITCODE instead.

[CmdletBinding()]
param(
    [string]$RepoName = "faust-ctf-2026-writeups",
    [string]$GitName,
    [string]$GitEmail,
    [switch]$Private
)

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot

function Info($m) { Write-Host "  $m" }
function Head($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Die($m)  { Write-Host ""; Write-Host "[ABORT] $m" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------------------- #
Head "0. Locating gh"

$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    $cand = 'C:\Program Files\GitHub CLI\gh.exe'
    if (Test-Path $cand) {
        $gh = $cand
    } else {
        Die "gh not found. Open a NEW terminal (PATH is stale in this one), or install: winget install --id GitHub.cli -e"
    }
}
Info "gh = $gh"
Info ((& $gh --version | Select-Object -First 1))

# --------------------------------------------------------------------------- #
Head "1. GitHub authentication"

& $gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  Not logged in to GitHub yet. Run this once in your own terminal:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "      gh auth login" -ForegroundColor White
    Write-Host ""
    Write-Host "  Choose GitHub.com -> HTTPS -> login with a browser (or paste a PAT),"
    Write-Host "  then run this script again."
    Write-Host ""
    Write-Host "  Do NOT paste your token into any chat, including an AI assistant." -ForegroundColor Yellow
    exit 2
}
$acct = ((& $gh api user --jq .login 2>$null) | Out-String).Trim()
Info "logged in as: $acct"

# --------------------------------------------------------------------------- #
Head "2. git commit identity"

# Repo-local, NOT --global: a publish script must not silently rewrite the
# user's global git config for every other repository on the machine.
$curName  = ((& git config --local user.name  2>$null) | Out-String).Trim()
$curEmail = ((& git config --local user.email 2>$null) | Out-String).Trim()

if (-not $GitName)  { $GitName  = $curName }
if (-not $GitEmail) { $GitEmail = $curEmail }

if (-not $GitName)  { $GitName  = Read-Host "  git user.name  (will be public in the commit)" }
if (-not $GitEmail) { $GitEmail = Read-Host "  git user.email (will be public in the commit)" }

if (-not $GitName -or -not $GitEmail) { Die "identity must not be empty" }

& git config --local user.name  $GitName
& git config --local user.email $GitEmail
Info "user.name  = $GitName   (repo-local)"
Info "user.email = $GitEmail  (repo-local)"

# --------------------------------------------------------------------------- #
Head "3. Pre-publish self-check (secrets / numbers / links / numbering)"

python .\preflight.py
if ($LASTEXITCODE -ne 0) {
    Die "self-check failed - fix the items listed above before publishing."
}
Info "self-check passed"

# --------------------------------------------------------------------------- #
Head "4. Commit"

& git add -A
$staged = (& git diff --cached --numstat | Measure-Object).Count
if ($staged -eq 0) {
    Info "nothing new to commit (already committed?)"
} else {
    & git commit -m "FAUST CTF 2026 writeups: IMC bug chain, Lamp TeX header injection, Rufflecopter AVM2 reverse"
    if ($LASTEXITCODE -ne 0) { Die "git commit failed" }
    Info "committed $staged file(s)"
}

# --------------------------------------------------------------------------- #
Head "5. Create remote and push"

$visibility = '--public'
if ($Private) { $visibility = '--private' }

$hasOrigin = (& git remote) -contains 'origin'
if ($hasOrigin) {
    Info "origin already exists, pushing"
    & git push -u origin main
    if ($LASTEXITCODE -ne 0) { Die "git push failed" }
} else {
    & $gh repo create $RepoName $visibility --source=. --remote=origin --push
    if ($LASTEXITCODE -ne 0) { Die "repo create / push failed - see the error above" }
}

$url = ((& $gh repo view --json url --jq .url 2>$null) | Out-String).Trim()
Info "repo: $url"

# --------------------------------------------------------------------------- #
Head "Done - now submit to CTFtime"

Write-Host ""
Write-Host "  1. Open https://ctftime.org/writeup/add/" -ForegroundColor Green
Write-Host "  2. Event:  FAUST CTF 2026   (event id 3312)" -ForegroundColor Green
Write-Host "  3. One writeup per service. Suggested URLs:" -ForegroundColor Green
Write-Host ""
Write-Host "       IMC           $url/blob/main/writeups/imc.md"
Write-Host "       Lamp          $url/blob/main/writeups/lamp.md"
Write-Host "       Rufflecopter  $url/blob/main/writeups/rufflecopter.md"
Write-Host ""
Write-Host "  4. Language: Chinese (each writeup carries an English abstract)" -ForegroundColor Green
Write-Host ""
Write-Host "  See PUBLISHING.md for details." -ForegroundColor Green
Write-Host ""
