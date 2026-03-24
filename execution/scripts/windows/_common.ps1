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

    $overridePython = [string]$env:QSF_REPO_PYTHON
    if ([string]::IsNullOrWhiteSpace($overridePython)) {
        $overridePython = [Environment]::GetEnvironmentVariable("QSF_REPO_PYTHON", "User")
    }
    if ([string]::IsNullOrWhiteSpace($overridePython)) {
        $overridePython = [Environment]::GetEnvironmentVariable("QSF_REPO_PYTHON", "Machine")
    }
    if (-not [string]::IsNullOrWhiteSpace($overridePython)) {
        $resolvedOverride = $overridePython.Trim()
        if (Test-Path $resolvedOverride) {
            return $resolvedOverride
        }
        throw "QSF_REPO_PYTHON is set but not found: $resolvedOverride"
    }

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
        & $python -X utf8 @Arguments
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
        $output = & $python -X utf8 @Arguments
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

    $includeZeroShot = $false
    $includeSingleLightgbmCompare = $false
    $rawIncludeZeroShot = [string]$env:QSF_INCLUDE_ZERO_SHOT
    if ([string]::IsNullOrWhiteSpace($rawIncludeZeroShot)) {
        $rawIncludeZeroShot = [Environment]::GetEnvironmentVariable("QSF_INCLUDE_ZERO_SHOT", "User")
    }
    if ([string]::IsNullOrWhiteSpace($rawIncludeZeroShot)) {
        $rawIncludeZeroShot = [Environment]::GetEnvironmentVariable("QSF_INCLUDE_ZERO_SHOT", "Machine")
    }

    $rawIncludeSingleLightgbmCompare = [string]$env:QSF_COMPARE_SINGLE_LIGHTGBM
    if ([string]::IsNullOrWhiteSpace($rawIncludeSingleLightgbmCompare)) {
        $rawIncludeSingleLightgbmCompare = [Environment]::GetEnvironmentVariable("QSF_COMPARE_SINGLE_LIGHTGBM", "User")
    }
    if ([string]::IsNullOrWhiteSpace($rawIncludeSingleLightgbmCompare)) {
        $rawIncludeSingleLightgbmCompare = [Environment]::GetEnvironmentVariable("QSF_COMPARE_SINGLE_LIGHTGBM", "Machine")
    }
    if (-not [string]::IsNullOrWhiteSpace($rawIncludeZeroShot)) {
        $normalizedIncludeZeroShot = $rawIncludeZeroShot.Trim().ToLowerInvariant()
        if ($normalizedIncludeZeroShot -in @("1", "true", "yes", "y", "on")) {
            $includeZeroShot = $true
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($rawIncludeSingleLightgbmCompare)) {
        $normalizedIncludeSingleLightgbmCompare = $rawIncludeSingleLightgbmCompare.Trim().ToLowerInvariant()
        if ($normalizedIncludeSingleLightgbmCompare -in @("1", "true", "yes", "y", "on")) {
            $includeSingleLightgbmCompare = $true
        }
    }

    $configs = New-Object System.Collections.Generic.List[string]

    if ($includeZeroShot) {
        $configs.Add((Join-Path $RepoRoot "execution\strategies\us_zeroshot_a_share_multi_expert_daily.json"))
    }

    $configs.Add((Join-Path $RepoRoot "execution\strategies\us_full_multi_expert_daily.json"))

    if ($includeSingleLightgbmCompare) {
        $singleLightgbmConfig = Join-Path $RepoRoot "execution\strategies\us_full_single_lightgbm_daily.json"
        if (Test-Path $singleLightgbmConfig) {
            $configs.Add($singleLightgbmConfig)
        }
        else {
            Write-Warning ("QSF_COMPARE_SINGLE_LIGHTGBM=true but strategy config missing: " + $singleLightgbmConfig)
        }
    }

    return $configs.ToArray()
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
        [string[]]$Notes = @(),
        [switch]$Notify
    )

    $arguments = @(
        "-m", "execution.managed.apps.paper_brief",
        "--phase", $Phase,
        "--status", $Status
    )
    if (-not [string]::IsNullOrWhiteSpace($Title)) {
        $arguments += @("--title", $Title)
    }
    if ($Notify) {
        $arguments += "--notify"
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
        if ($null -ne $briefPayload.notification) {
            $notify = $briefPayload.notification
            $notifySummary = "enabled=$($notify.enabled); sent=$($notify.sent)"
            if (-not [string]::IsNullOrWhiteSpace([string]$notify.reason)) {
                $notifySummary += "; reason=$($notify.reason)"
            }
            if (-not [string]::IsNullOrWhiteSpace([string]$notify.error)) {
                $notifySummary += "; error=$($notify.error)"
            }
            Write-Host ("[brief] Notify: " + $notifySummary)
        }
    }
    return $briefPayload
}

function Publish-OperationBriefNotification {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$BriefPayload
    )

    $notifyConfig = Get-FeishuNotificationConfig
    if ([string]::IsNullOrWhiteSpace($notifyConfig.WebhookUrl)) {
        Write-Host "[notify] Feishu webhook is not configured. Skipping outbound notification."
        return
    }

    $message = Format-OperationBriefMessage -BriefPayload $BriefPayload
    $payload = @{
        msg_type = "text"
        content = @{
            text = $message
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($notifyConfig.Secret)) {
        $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
        $stringToSign = "$timestamp`n$($notifyConfig.Secret)"
        $hmac = [System.Security.Cryptography.HMACSHA256]::new([System.Text.Encoding]::UTF8.GetBytes($stringToSign))
        try {
            $signature = [Convert]::ToBase64String($hmac.ComputeHash([byte[]]@()))
        }
        finally {
            $hmac.Dispose()
        }
        $payload.timestamp = $timestamp
        $payload.sign = $signature
    }
    $body = $payload | ConvertTo-Json -Depth 10

    Invoke-RestMethod -Uri $notifyConfig.WebhookUrl -Method Post -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
    Write-Host "[notify] Feishu brief sent."
}

function Get-FeishuNotificationConfig {
    $repoRoot = Get-RepoRoot
    $configPath = Join-Path $repoRoot "configs\ops_notifications.local.json"

    $webhook = ""
    $secret = ""

    if (Test-Path $configPath) {
        try {
            $config = Get-Content $configPath -Raw | ConvertFrom-Json -Depth 20
            if ($null -ne $config -and $null -ne $config.feishu) {
                if ($config.feishu.enabled -eq $false) {
                    return [pscustomobject]@{
                        WebhookUrl = ""
                        Secret = ""
                    }
                }
                $webhook = [string]$config.feishu.webhook_url
                $secret = [string]$config.feishu.secret
            }
        }
        catch {
            Write-Warning ("Failed to parse ops_notifications.local.json: " + $_.Exception.Message)
        }
    }

    if ([string]::IsNullOrWhiteSpace($webhook)) {
        $webhook = $env:QSF_FEISHU_WEBHOOK_URL
    }
    if ([string]::IsNullOrWhiteSpace($webhook)) {
        $webhook = [Environment]::GetEnvironmentVariable("QSF_FEISHU_WEBHOOK_URL", "User")
    }
    if ([string]::IsNullOrWhiteSpace($secret)) {
        $secret = $env:QSF_FEISHU_WEBHOOK_SECRET
    }
    if ([string]::IsNullOrWhiteSpace($secret)) {
        $secret = [Environment]::GetEnvironmentVariable("QSF_FEISHU_WEBHOOK_SECRET", "User")
    }

    return [pscustomobject]@{
        WebhookUrl = $webhook
        Secret = $secret
    }
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
