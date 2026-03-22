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

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    if (-not (Test-Path $PathValue)) {
        throw "Required path does not exist: $PathValue"
    }
}
