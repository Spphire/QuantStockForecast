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

$briefStatus = "success"
$briefNotes = New-Object System.Collections.Generic.List[string]
$briefNotes.Add("Data end date: $DataEndDate")
if ($RefreshMetadata) {
    $briefNotes.Add("Metadata refresh enabled.")
}
$fatalError = $null

try {

$universeSymbols = "configs/stock_universe_us_large_cap_30.txt"
$metadataCsv = "data/interim/stooq/universes/us_large_cap_30_metadata.csv"

Invoke-RepoPython -RepoRoot $repoRoot -Arguments @(
    "data_module/fetchers/scripts/fetch_stock_universe.py",
    "--provider", "stooq",
    "--symbols-file", $universeSymbols,
    "--name", "us_large_cap_30",
    "--start", "2020-01-01",
    "--end", $DataEndDate,
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

$latestUniverseCsv = Get-ChildItem (Join-Path $repoRoot "data/interim/stooq/universes/us_large_cap_30_20200101_*_hfq_normalized.csv") |
    Sort-Object Name |
    Select-Object -Last 1

if ($null -eq $latestUniverseCsv) {
    throw "No normalized U.S. universe CSV found after fetch."
}

$aShareModelPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/model.txt"
    xgboost     = "model_prediction/xgboost/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/model.json"
    catboost    = "execution/experiments/us_a_share_expert_suite/catboost_regression_balanced/train/model.cbm"
    lstm        = "execution/experiments/us_a_share_expert_suite/lstm_regression_balanced/train/model.pt"
    transformer = "execution/experiments/us_a_share_expert_suite/transformer_regression_balanced/train/model.pt"
}
$aShareMetricsPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/metrics.json"
    xgboost     = "model_prediction/xgboost/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/metrics.json"
    catboost    = "execution/experiments/us_a_share_expert_suite/catboost_regression_balanced/train/metrics.json"
    lstm        = "execution/experiments/us_a_share_expert_suite/lstm_regression_balanced/train/metrics.json"
    transformer = "execution/experiments/us_a_share_expert_suite/transformer_regression_balanced/train/metrics.json"
}
$usFullModelPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/us_large_cap_30_full_regression_5d/model.txt"
    xgboost     = "model_prediction/xgboost/artifacts/us_large_cap_30_full_regression_5d/model.json"
    catboost    = "model_prediction/catboost/artifacts/us_large_cap_30_full_regression_5d/model.cbm"
    lstm        = "model_prediction/lstm/artifacts/us_large_cap_30_full_regression_5d/model.pt"
    transformer = "model_prediction/transformer/artifacts/us_large_cap_30_full_regression_5d_lb20/model.pt"
}
$usFullMetricsPaths = @{
    lightgbm    = "model_prediction/lightgbm/artifacts/us_large_cap_30_full_regression_5d/metrics.json"
    xgboost     = "model_prediction/xgboost/artifacts/us_large_cap_30_full_regression_5d/metrics.json"
    catboost    = "model_prediction/catboost/artifacts/us_large_cap_30_full_regression_5d/metrics.json"
    lstm        = "model_prediction/lstm/artifacts/us_large_cap_30_full_regression_5d/metrics.json"
    transformer = "model_prediction/transformer/artifacts/us_large_cap_30_full_regression_5d_lb20/metrics.json"
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
            -Title ("Nightly Research Brief - " + $DataEndDate) `
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
        Write-Warning ("Brief generation failed after research error: " + $_.Exception.Message)
    }
}

if ($null -ne $fatalError) {
    throw $fatalError
}

Write-Host ("[done] Daily research pipeline finished for end date " + $DataEndDate)
