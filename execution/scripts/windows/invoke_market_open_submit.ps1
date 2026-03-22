param(
    [string[]]$StrategyConfigs = @(),
    [switch]$AllowUnhealthy,
    [switch]$SkipSessionGuard,
    [switch]$IgnoreTimeWindow
)

. "$PSScriptRoot\_common.ps1"

$repoRoot = Get-RepoRoot
$nyNow = Get-NewYorkNow

if (-not $IgnoreTimeWindow -and -not (Test-NewYorkTimeWindow -StartTime "09:31" -EndTime "10:00")) {
    Write-Host "[skip] Outside New York market-open submit window."
    Write-Host ("[skip] New York time now: " + $nyNow.ToString("yyyy-MM-dd HH:mm:ss"))
    exit 0
}

if ($StrategyConfigs.Count -eq 0) {
    $StrategyConfigs = Get-DefaultStrategyConfigs -RepoRoot $repoRoot
}

$python = Get-RepoPython -RepoRoot $repoRoot
$briefStatus = "success"
$briefNotes = New-Object System.Collections.Generic.List[string]
if ($AllowUnhealthy) {
    $briefNotes.Add("AllowUnhealthy enabled.")
}
if ($SkipSessionGuard) {
    $briefNotes.Add("SkipSessionGuard enabled.")
}
$fatalError = $null
$skippedStrategies = New-Object System.Collections.Generic.List[string]

try {

foreach ($strategyConfig in $StrategyConfigs) {
    $resolvedConfig = Resolve-Path $strategyConfig
    $strategyJson = Get-Content $resolvedConfig -Raw | ConvertFrom-Json
    $prefix = [string]$strategyJson.paper_env_prefix

    $clockScript = @'
import json
import sys
from execution.alpaca.client import AlpacaBroker, load_alpaca_credentials

prefix = sys.argv[1]
broker = AlpacaBroker(load_alpaca_credentials(prefix))
clock = broker.get_clock()
print(json.dumps({
    "prefix": prefix,
    "is_open": bool(clock.get("is_open", False)),
    "timestamp": clock.get("timestamp"),
    "next_open": clock.get("next_open"),
    "next_close": clock.get("next_close"),
}, ensure_ascii=False))
'@

    Push-Location $repoRoot
    try {
        $clockJson = $clockScript | & $python - $prefix
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to query Alpaca clock for $prefix"
        }
    }
    finally {
        Pop-Location
    }

    $clock = $clockJson | ConvertFrom-Json
    if (-not [bool]$clock.is_open) {
        Write-Host ("[skip] Broker clock closed for " + $resolvedConfig)
        $skippedStrategies.Add([string]$resolvedConfig)
        continue
    }

    Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
        "-m", "execution.managed.apps.paper_daily",
        $resolvedConfig,
        "healthcheck"
    )

    $runArgs = @(
        "-m", "execution.managed.apps.paper_daily",
        $resolvedConfig,
        "run",
        "--submit",
        "--require-paper"
    )
    if ($AllowUnhealthy) {
        $runArgs += "--allow-unhealthy"
    }
    if ($SkipSessionGuard) {
        $runArgs += "--skip-session-guard"
    }
    Invoke-RepoPython -RepoRoot $repoRoot -Arguments $runArgs

    Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
        "-m", "execution.managed.apps.paper_ops",
        $resolvedConfig,
        "latest-run"
    )
}
}
catch {
    $briefStatus = "failed"
    $briefNotes.Add($_.Exception.Message)
    $fatalError = $_
}
finally {
    if ($skippedStrategies.Count -gt 0 -and $briefStatus -eq "success") {
        $briefStatus = "partial"
        $briefNotes.Add("Broker closed for: " + ($skippedStrategies.ToArray() -join ", "))
    }
    try {
        $briefPayload = Invoke-OperationBrief `
            -RepoRoot $repoRoot `
            -Phase "submit" `
            -StrategyConfigs $StrategyConfigs `
            -Title ("Market Open Submit Brief - " + $nyNow.ToString("yyyy-MM-dd")) `
            -Status $briefStatus `
            -Notes $briefNotes.ToArray()
        if ($null -ne $briefPayload) {
            Publish-OperationBriefNotification -BriefPayload $briefPayload
        }
    }
    catch {
        if ($null -eq $fatalError) {
            throw
        }
        Write-Warning ("Brief generation failed after submit error: " + $_.Exception.Message)
    }
}

if ($null -ne $fatalError) {
    throw $fatalError
}

Write-Host "[done] Market-open submit wrapper finished."
