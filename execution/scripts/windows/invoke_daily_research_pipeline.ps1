param(
    [string]$DataEndDate = "",
    [string[]]$StrategyConfigs = @(),
    [switch]$RefreshMetadata,
    [switch]$IgnoreTimeWindow
)

. "$PSScriptRoot\_common.ps1"

$repoRoot = Get-RepoRoot
$nyNow = Get-NewYorkNow

if (-not $IgnoreTimeWindow -and -not (Test-NewYorkTimeWindow -StartTime "16:10" -EndTime "20:00")) {
    Write-Host "[skip] Outside post-close New York research window."
    Write-Host ("[skip] New York time now: " + $nyNow.ToString("yyyy-MM-dd HH:mm:ss"))
    exit 0
}

if ([string]::IsNullOrWhiteSpace($DataEndDate)) {
    $DataEndDate = $nyNow.ToString("yyyy-MM-dd")
}
$dataEndDateCompact = $DataEndDate.Replace("-", "")

if ($StrategyConfigs.Count -eq 0) {
    $StrategyConfigs = Get-DefaultStrategyConfigs -RepoRoot $repoRoot
}

$alpacaDataEnvPrefix = "ALPACA_ZERO_SHOT"
try {
    $firstConfig = Get-Content (Resolve-Path $StrategyConfigs[0]) -Raw | ConvertFrom-Json
    if (-not [string]::IsNullOrWhiteSpace([string]$firstConfig.paper_env_prefix)) {
        $alpacaDataEnvPrefix = [string]$firstConfig.paper_env_prefix
    }
}
catch {
    Write-Warning ("Unable to infer Alpaca data prefix from strategy config, fallback to " + $alpacaDataEnvPrefix)
}

$briefStatus = "success"
$briefNotes = New-Object System.Collections.Generic.List[string]
$briefNotes.Add("Data end date: $DataEndDate")
$briefNotes.Add("Market data provider: Alpaca ($alpacaDataEnvPrefix)")
if ($RefreshMetadata) {
    $briefNotes.Add("Metadata refresh enabled.")
}
$fatalError = $null

try {

$universeSymbols = "configs/stock_universe_us_large_cap_30.txt"
$metadataCsv = "data/interim/alpaca/universes/us_large_cap_30_metadata.csv"
$researchTitle = ([string]([char]0x591C) + [string]([char]0x95F4) + [string]([char]0x7814) + [string]([char]0x7A76) + [string]([char]0x7B80) + [string]([char]0x62A5) + " - " + $DataEndDate)

Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "data_module/fetchers/scripts/fetch_stock_universe.py",
    "--provider", "alpaca",
    "--symbols-file", $universeSymbols,
    "--name", "us_large_cap_30",
    "--start", "2020-01-01",
    "--end", $DataEndDate,
    "--alpaca-env-prefix", $alpacaDataEnvPrefix,
    "--alpaca-feed", "iex",
    "--continue-on-error"
)

if ($RefreshMetadata -or -not (Test-Path (Join-Path $repoRoot $metadataCsv))) {
    Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
        "data_module/fetchers/scripts/fetch_stock_metadata.py",
        "--provider", "wikipedia_sp500",
        "--symbols-file", $universeSymbols,
        "--output-csv", $metadataCsv
    )
}

$latestUniverseCsv = Get-ChildItem (Join-Path $repoRoot "data/interim/alpaca/universes/us_large_cap_30_20200101_*_hfq_normalized.csv") |
    Sort-Object Name |
    Select-Object -Last 1

if ($null -eq $latestUniverseCsv) {
    throw "No normalized U.S. universe CSV found after fetch."
}

$aShareModelPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/validation_20260322/zero_shot_a_share_train/model.txt"
    xgboost     = "model_prediction/xgboost/artifacts/validation_20260322/zero_shot_a_share_train/model.json"
    catboost    = "model_prediction/catboost/artifacts/validation_20260322/zero_shot_a_share_train/model.cbm"
    lstm        = "model_prediction/lstm/artifacts/validation_20260322/zero_shot_a_share_train/model.pt"
    transformer = "model_prediction/transformer/artifacts/validation_20260322/zero_shot_a_share_train/model.pt"
}
$aShareMetricsPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/validation_20260322/zero_shot_a_share_train/metrics.json"
    xgboost     = "model_prediction/xgboost/artifacts/validation_20260322/zero_shot_a_share_train/metrics.json"
    catboost    = "model_prediction/catboost/artifacts/validation_20260322/zero_shot_a_share_train/metrics.json"
    lstm        = "model_prediction/lstm/artifacts/validation_20260322/zero_shot_a_share_train/metrics.json"
    transformer = "model_prediction/transformer/artifacts/validation_20260322/zero_shot_a_share_train/metrics.json"
}
$usFullModelPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/validation_20260322/us_full_train/model.txt"
    xgboost     = "model_prediction/xgboost/artifacts/validation_20260322/us_full_train/model.json"
    catboost    = "model_prediction/catboost/artifacts/validation_20260322/us_full_train/model.cbm"
    lstm        = "model_prediction/lstm/artifacts/validation_20260322/us_full_train/model.pt"
    transformer = "model_prediction/transformer/artifacts/validation_20260322/us_full_train/model.pt"
}
$usFullMetricsPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/validation_20260322/us_full_train/metrics.json"
    xgboost     = "model_prediction/xgboost/artifacts/validation_20260322/us_full_train/metrics.json"
    catboost    = "model_prediction/catboost/artifacts/validation_20260322/us_full_train/metrics.json"
    lstm        = "model_prediction/lstm/artifacts/validation_20260322/us_full_train/metrics.json"
    transformer = "model_prediction/transformer/artifacts/validation_20260322/us_full_train/metrics.json"
}

foreach ($pathValue in @(
    $metadataCsv,
    $aShareModelPaths.lightgbm, $aShareModelPaths.xgboost, $aShareModelPaths.catboost, $aShareModelPaths.lstm, $aShareModelPaths.transformer,
    $aShareMetricsPaths.lightgbm, $aShareMetricsPaths.xgboost, $aShareMetricsPaths.catboost, $aShareMetricsPaths.lstm, $aShareMetricsPaths.transformer,
    $usFullModelPaths.lightgbm, $usFullModelPaths.xgboost, $usFullModelPaths.catboost, $usFullModelPaths.lstm, $usFullModelPaths.transformer,
    $usFullMetricsPaths.lightgbm, $usFullMetricsPaths.xgboost, $usFullMetricsPaths.catboost, $usFullMetricsPaths.lstm, $usFullMetricsPaths.transformer
)) {
    Assert-PathExists -PathValue (Join-Path $repoRoot $pathValue)
}

$evalStart = "2024-01-01"
$zeroShotRoot = "model_prediction"
$zeroShotName = "us_zeroshot_a_share_multi_daily"
$usFullName = "us_full_multi_expert_daily"
$latestUniverseRelative = $latestUniverseCsv.FullName.Substring($repoRoot.Length + 1)

Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/lightgbm/scripts/predict_lightgbm.py",
    $latestUniverseRelative,
    "--model-path", $aShareModelPaths.lightgbm,
    "--reference-metrics", $aShareMetricsPaths.lightgbm,
    "--output-dir", "model_prediction/lightgbm/artifacts/$zeroShotName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/xgboost/scripts/predict_xgboost.py",
    $latestUniverseRelative,
    "--model-path", $aShareModelPaths.xgboost,
    "--reference-metrics", $aShareMetricsPaths.xgboost,
    "--output-dir", "model_prediction/xgboost/artifacts/$zeroShotName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/catboost/scripts/predict_catboost.py",
    $latestUniverseRelative,
    "--model-path", $aShareModelPaths.catboost,
    "--reference-metrics", $aShareMetricsPaths.catboost,
    "--output-dir", "model_prediction/catboost/artifacts/$zeroShotName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/lstm/scripts/predict_lstm.py",
    $latestUniverseRelative,
    "--model-path", $aShareModelPaths.lstm,
    "--reference-metrics", $aShareMetricsPaths.lstm,
    "--output-dir", "model_prediction/lstm/artifacts/$zeroShotName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/transformer/scripts/predict_transformer.py",
    $latestUniverseRelative,
    "--model-path", $aShareModelPaths.transformer,
    "--reference-metrics", $aShareMetricsPaths.transformer,
    "--output-dir", "model_prediction/transformer/artifacts/$zeroShotName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/ensemble/scripts/predict_ensemble.py",
    "model_prediction/lightgbm/artifacts/$zeroShotName/test_predictions.csv",
    "--prediction-csv", "model_prediction/xgboost/artifacts/$zeroShotName/test_predictions.csv",
    "--prediction-csv", "model_prediction/catboost/artifacts/$zeroShotName/test_predictions.csv",
    "--prediction-csv", "model_prediction/lstm/artifacts/$zeroShotName/test_predictions.csv",
    "--prediction-csv", "model_prediction/transformer/artifacts/$zeroShotName/test_predictions.csv",
    "--method", "mean_score",
    "--min-experts", "5",
    "--model-name", "ensemble_mean_score",
    "--output-dir", "model_prediction/ensemble/artifacts/$zeroShotName"
)

Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/lightgbm/scripts/predict_lightgbm.py",
    $latestUniverseRelative,
    "--model-path", $usFullModelPaths.lightgbm,
    "--reference-metrics", $usFullMetricsPaths.lightgbm,
    "--output-dir", "model_prediction/lightgbm/artifacts/$usFullName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/xgboost/scripts/predict_xgboost.py",
    $latestUniverseRelative,
    "--model-path", $usFullModelPaths.xgboost,
    "--reference-metrics", $usFullMetricsPaths.xgboost,
    "--output-dir", "model_prediction/xgboost/artifacts/$usFullName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/catboost/scripts/predict_catboost.py",
    $latestUniverseRelative,
    "--model-path", $usFullModelPaths.catboost,
    "--reference-metrics", $usFullMetricsPaths.catboost,
    "--output-dir", "model_prediction/catboost/artifacts/$usFullName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/lstm/scripts/predict_lstm.py",
    $latestUniverseRelative,
    "--model-path", $usFullModelPaths.lstm,
    "--reference-metrics", $usFullMetricsPaths.lstm,
    "--output-dir", "model_prediction/lstm/artifacts/$usFullName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/transformer/scripts/predict_transformer.py",
    $latestUniverseRelative,
    "--model-path", $usFullModelPaths.transformer,
    "--reference-metrics", $usFullMetricsPaths.transformer,
    "--output-dir", "model_prediction/transformer/artifacts/$usFullName",
    "--eval-start", $evalStart,
    "--eval-end", $DataEndDate
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "model_prediction/ensemble/scripts/predict_ensemble.py",
    "model_prediction/lightgbm/artifacts/$usFullName/test_predictions.csv",
    "--prediction-csv", "model_prediction/xgboost/artifacts/$usFullName/test_predictions.csv",
    "--prediction-csv", "model_prediction/catboost/artifacts/$usFullName/test_predictions.csv",
    "--prediction-csv", "model_prediction/lstm/artifacts/$usFullName/test_predictions.csv",
    "--prediction-csv", "model_prediction/transformer/artifacts/$usFullName/test_predictions.csv",
    "--method", "mean_score",
    "--min-experts", "5",
    "--model-name", "ensemble_mean_score",
    "--output-dir", "model_prediction/ensemble/artifacts/$usFullName"
)

Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "risk_management/white_box/scripts/run_white_box_risk.py",
    "model_prediction/ensemble/artifacts/$zeroShotName/test_predictions.csv",
    "--metadata-csv", $metadataCsv,
    "--rebalance-step", "1",
    "--top-k", "5",
    "--min-score", "0",
    "--min-confidence", "0.7",
    "--min-close", "5",
    "--min-amount", "100000000",
    "--group-column", "industry_group",
    "--max-per-group", "1",
    "--secondary-group-column", "amount_bucket",
    "--secondary-max-per-group", "2",
    "--weighting", "score_confidence",
    "--max-position-weight", "0.35",
    "--max-gross-exposure", "0.85",
    "--confidence-target", "0.90",
    "--min-gross-exposure", "0.55",
    "--transaction-cost-bps", "10",
    "--output-dir", "risk_management/white_box/runtime/us_zeroshot_a_share_multi_expert_daily"
)
Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "risk_management/white_box/scripts/run_white_box_risk.py",
    "model_prediction/ensemble/artifacts/$usFullName/test_predictions.csv",
    "--metadata-csv", $metadataCsv,
    "--rebalance-step", "1",
    "--top-k", "5",
    "--min-score", "0",
    "--min-confidence", "0.7",
    "--min-close", "5",
    "--min-amount", "100000000",
    "--group-column", "industry_group",
    "--max-per-group", "1",
    "--secondary-group-column", "amount_bucket",
    "--secondary-max-per-group", "2",
    "--weighting", "score_confidence",
    "--max-position-weight", "0.35",
    "--max-gross-exposure", "0.90",
    "--confidence-target", "0.85",
    "--min-gross-exposure", "0.60",
    "--transaction-cost-bps", "10",
    "--output-dir", "risk_management/white_box/runtime/us_full_multi_expert_daily"
)
}
catch {
    $briefStatus = "failed"
    $briefNotes.Add($_.Exception.Message)
    $fatalError = $_
}
finally {
    try {
        $briefPayload = Invoke-OperationBrief `
            -RepoRoot $repoRoot `
            -Phase "research" `
            -StrategyConfigs $StrategyConfigs `
            -Title $researchTitle `
            -Status $briefStatus `
            -Notes $briefNotes.ToArray() `
            -Notify
    }
    catch {
        if ($null -eq $fatalError) {
            throw
        }
        Write-Warning ("Brief generation failed after research error: " + $_.Exception.Message)
    }
}

if ($null -ne $fatalError) {
    throw $fatalError
}

Write-Host ("[done] Daily research pipeline finished for end date " + $DataEndDate)
