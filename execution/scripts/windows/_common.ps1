Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
}

function Get-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Invoke-RepoPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $python = Get-RepoPython -RepoRoot $RepoRoot
    Write-Host ("[python] " + ($Arguments -join " "))
    Push-Location $RepoRoot
    try {
        & $python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-RepoPythonJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $python = Get-RepoPython -RepoRoot $RepoRoot
    Write-Host ("[python-json] " + ($Arguments -join " "))
    Push-Location $RepoRoot
    try {
        $output = & $python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python command failed with exit code $LASTEXITCODE"
        }
        $jsonText = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($jsonText)) {
            return $null
        }
        return $jsonText | ConvertFrom-Json
    }
    finally {
        Pop-Location
    }
}

function Get-NewYorkNow {
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz)
}

function Test-NewYorkTimeWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StartTime,
        [Parameter(Mandatory = $true)]
        [string]$EndTime
    )

    $now = Get-NewYorkNow
    $current = $now.TimeOfDay
    $start = [TimeSpan]::Parse($StartTime)
    $end = [TimeSpan]::Parse($EndTime)
    return ($current -ge $start -and $current -le $end)
}

function Get-DefaultStrategyConfigs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return @(
        (Join-Path $RepoRoot "execution\strategies\us_zeroshot_a_share_multi_expert_daily.json"),
        (Join-Path $RepoRoot "execution\strategies\us_full_multi_expert_daily.json")
    )
}

function Invoke-OperationBrief {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [ValidateSet("research", "submit")]
        [string]$Phase,
        [Parameter(Mandatory = $true)]
        [string[]]$StrategyConfigs,
        [string]$Title = "",
        [ValidateSet("success", "partial", "failed")]
        [string]$Status = "success",
        [string[]]$Notes = @()
    )

    $arguments = @(
        "-m", "execution.managed.apps.paper_brief",
        "--phase", $Phase,
        "--status", $Status
    )
    if (-not [string]::IsNullOrWhiteSpace($Title)) {
        $arguments += @("--title", $Title)
    }
    foreach ($note in $Notes) {
        if (-not [string]::IsNullOrWhiteSpace($note)) {
            $arguments += @("--note", $note)
        }
    }
    foreach ($strategyConfig in $StrategyConfigs) {
        $arguments += $strategyConfig
    }

    $briefPayload = Invoke-RepoPythonJson -RepoRoot $RepoRoot -Arguments $arguments
    if ($null -ne $briefPayload) {
        Write-Host ("[brief] Dashboard: " + $briefPayload.dashboard_png)
        Write-Host ("[brief] HTML: " + $briefPayload.html_path)
    }
    return $briefPayload
}

function Publish-OperationBriefNotification {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$BriefPayload
    )

    $webhook = $env:QSF_FEISHU_WEBHOOK_URL
    if ([string]::IsNullOrWhiteSpace($webhook)) {
        $webhook = [Environment]::GetEnvironmentVariable("QSF_FEISHU_WEBHOOK_URL", "User")
    }
    if ([string]::IsNullOrWhiteSpace($webhook)) {
        Write-Host "[notify] QSF_FEISHU_WEBHOOK_URL is not configured. Skipping outbound notification."
        return
    }

    $message = Format-OperationBriefMessage -BriefPayload $BriefPayload
    $body = @{
        msg_type = "text"
        content = @{
            text = $message
        }
    } | ConvertTo-Json -Depth 10

    Invoke-RestMethod -Uri $webhook -Method Post -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
    Write-Host "[notify] Feishu brief sent."
}

function Format-OperationBriefMessage {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$BriefPayload
    )

    $summary = $BriefPayload.summary
    $lines = @(
        "[QSF] $($BriefPayload.title)",
        "Status: $($BriefPayload.status_display)",
        "UTC: $($BriefPayload.generated_at_utc)",
        "Targets: $($summary.positive_target_count) | Exit: $($summary.exit_count) | Submitted: $($summary.submitted_count) | Open: $($summary.open_order_count)",
        "Dashboard: $($BriefPayload.dashboard_png)",
        "HTML: $($BriefPayload.html_path)",
        ""
    )

    foreach ($note in @($BriefPayload.notes)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$note)) {
            $lines += "Note: $note"
        }
    }
    if (@($BriefPayload.notes).Count -gt 0) {
        $lines += ""
    }

    foreach ($strategy in $BriefPayload.strategies) {
        $topPositions = @($strategy.top_positions | Select-Object -First 3 | ForEach-Object {
            if ($null -eq $_) {
                return
            }
            $weightPct = [double]($_.target_weight) * 100.0
            return ("{0} {1:N1}%" -f $_.symbol, $weightPct)
        }) -join ", "
        $headline = if ([string]::IsNullOrWhiteSpace($topPositions)) {
            $strategy.explain_like_human
        }
        else {
            "$($strategy.explain_like_human) Top: $topPositions."
        }
        $lines += "- $($strategy.strategy_id): $headline"
        if (@($strategy.alerts).Count -gt 0) {
            $alertCodes = @($strategy.alerts | Select-Object -First 3 | ForEach-Object { $_.code }) -join ", "
            $lines += "  Alerts: $alertCodes"
        }
    }

    return ($lines -join "`n").Trim()
}

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    if (-not (Test-Path $PathValue)) {
        throw "Required path does not exist: $PathValue"
    }
}
