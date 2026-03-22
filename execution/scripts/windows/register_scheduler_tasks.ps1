param(
    [switch]$WhatIf
)

. "$PSScriptRoot\_common.ps1"

$repoRoot = Get-RepoRoot

$taskSpecs = @(
    @{
        Name = "QuantStockForecast-NightlyResearch-0530"
        Days = "TUE,WED,THU,FRI,SAT"
        Time = "05:30"
        ScriptPath = (Join-Path $repoRoot "execution\scripts\windows\invoke_daily_research_pipeline.ps1")
    },
    @{
        Name = "QuantStockForecast-NightlyResearch-0630"
        Days = "TUE,WED,THU,FRI,SAT"
        Time = "06:30"
        ScriptPath = (Join-Path $repoRoot "execution\scripts\windows\invoke_daily_research_pipeline.ps1")
    },
    @{
        Name = "QuantStockForecast-MarketOpenSubmit-2135"
        Days = "MON,TUE,WED,THU,FRI"
        Time = "21:35"
        ScriptPath = (Join-Path $repoRoot "execution\scripts\windows\invoke_market_open_submit.ps1")
    },
    @{
        Name = "QuantStockForecast-MarketOpenSubmit-2235"
        Days = "MON,TUE,WED,THU,FRI"
        Time = "22:35"
        ScriptPath = (Join-Path $repoRoot "execution\scripts\windows\invoke_market_open_submit.ps1")
    }
)

foreach ($spec in $taskSpecs) {
    Assert-PathExists -PathValue $spec.ScriptPath
    $taskCommand = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $spec.ScriptPath)
    if ($WhatIf) {
        Write-Host ("[whatif] schtasks /Create /TN {0} /SC WEEKLY /D {1} /ST {2} /TR {3} /F" -f $spec.Name, $spec.Days, $spec.Time, $taskCommand)
        continue
    }

    schtasks /Create /TN $spec.Name /SC WEEKLY /D $spec.Days /ST $spec.Time /TR $taskCommand /F | Out-Host
}

if (-not $WhatIf) {
    foreach ($spec in $taskSpecs) {
        schtasks /Query /TN $spec.Name /FO LIST /V | Out-Host
    }
}
