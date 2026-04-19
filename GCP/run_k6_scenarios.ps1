param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId = "leafy-bond-493717-c4",

    [Parameter(Mandatory = $false)]
    [string]$Region = "us-east1",

    [Parameter(Mandatory = $false)]
    [string]$BucketName = "gcp-testing-kt",

    [Parameter(Mandatory = $false)]
    [string]$OutputPath = ".\k6_results.json"
)

$ErrorActionPreference = "Stop"

if (Get-Command gcloud -ErrorAction SilentlyContinue) {
    $gcloudCmd = "gcloud"
} elseif (Test-Path "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd") {
    $gcloudCmd = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
} elseif (Test-Path "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd") {
    $gcloudCmd = "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
} else {
    throw "gcloud was not found in PATH or common install locations."
}

$apiHandler = & $gcloudCmd functions describe api-handler --gen2 --region=$Region --format="value(serviceConfig.uri)"
$imageResizer = & $gcloudCmd functions describe image-resizer --gen2 --region=$Region --format="value(serviceConfig.uri)"
$cpuSort = & $gcloudCmd functions describe cpu-sort --gen2 --region=$Region --format="value(serviceConfig.uri)"

if (-not $apiHandler -or -not $imageResizer -or -not $cpuSort) {
    throw "Unable to resolve one or more deployed function URLs."
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} else {
    throw "Python was not found in PATH."
}

& $pythonCmd .\run_k6_scenarios.py `
    --project-id $ProjectId `
    --region $Region `
    --api-handler $apiHandler `
    --image-resizer $imageResizer `
    --cpu-sort $cpuSort `
    --bucket $BucketName `
    --out $OutputPath
