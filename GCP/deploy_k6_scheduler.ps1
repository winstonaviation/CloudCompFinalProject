param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "us-east1",

    [Parameter(Mandatory = $false)]
    [string]$BucketName = "gcp-testing-kt",

    [Parameter(Mandatory = $false)]
    [string]$ServiceName = "k6-runner",

    [Parameter(Mandatory = $false)]
    [string]$SchedulerJobName = "k6-runner-every-15m",

    [Parameter(Mandatory = $false)]
    [switch]$SkipEnableServices
)

$ErrorActionPreference = "Stop"

if ($null -ne (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Resolve-Gcloud {
    $localGcloud = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path $localGcloud) {
        return $localGcloud
    }

    $programFilesGcloud = "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (Test-Path $programFilesGcloud) {
        return $programFilesGcloud
    }

    $gcloudCommand = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($gcloudCommand) {
        if ($gcloudCommand.Source -like "*.ps1") {
            $cmdSibling = [System.IO.Path]::ChangeExtension($gcloudCommand.Source, ".cmd")
            if (Test-Path $cmdSibling) {
                return $cmdSibling
            }
        }

        return $gcloudCommand.Source
    }

    throw "gcloud was not found in PATH or common install locations."
}

function Assert-LastExitCode {
    param(
        [string]$Message
    )

    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

function Test-GcloudSuccess {
    param(
        [string[]]$Args
    )

    try {
        & $gcloudCmd @Args *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$gcloudCmd = Resolve-Gcloud

& $gcloudCmd config set project $ProjectId | Out-Null
Assert-LastExitCode "Failed to set the active gcloud project to $ProjectId."

$runServiceAccountName = "k6-runner-sa"
$runServiceAccount = "$runServiceAccountName@$ProjectId.iam.gserviceaccount.com"

$schedulerInvokerName = "k6-scheduler-invoker"
$schedulerInvokerAccount = "$schedulerInvokerName@$ProjectId.iam.gserviceaccount.com"

$services = @(
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com"
)

if (-not $SkipEnableServices) {
    & $gcloudCmd services enable $services | Out-Null
    Assert-LastExitCode (
        "Failed to enable required Google Cloud services. " +
        "You may need Service Usage Admin or project owner permissions."
    )
}

$bucketUri = "gs://$BucketName"
if (-not (Test-GcloudSuccess @("storage", "buckets", "describe", $bucketUri, "--project=$ProjectId"))) {
    $bucketCreateOutput = (& $gcloudCmd storage buckets create $bucketUri --location=$Region --project=$ProjectId 2>&1 | Out-String)
    if (
        $LASTEXITCODE -ne 0 `
        -and $bucketCreateOutput -notmatch "already own it" `
        -and -not (Test-GcloudSuccess @("storage", "buckets", "describe", $bucketUri, "--project=$ProjectId"))
    ) {
        throw "Failed to create bucket $bucketUri."
    }
}

if (-not (Test-GcloudSuccess @("iam", "service-accounts", "describe", $runServiceAccount))) {
    & $gcloudCmd iam service-accounts create $runServiceAccountName `
        --display-name="K6 Runner Service Account" | Out-Null
    Assert-LastExitCode "Failed to create service account $runServiceAccount."
}

if (-not (Test-GcloudSuccess @("iam", "service-accounts", "describe", $schedulerInvokerAccount))) {
    & $gcloudCmd iam service-accounts create $schedulerInvokerName `
        --display-name="K6 Scheduler Invoker" | Out-Null
    Assert-LastExitCode "Failed to create service account $schedulerInvokerAccount."
}

$apiHandler = & $gcloudCmd functions describe api-handler --gen2 --region=$Region --format="value(serviceConfig.uri)"
Assert-LastExitCode "Failed to resolve api-handler URL."

$imageResizer = & $gcloudCmd functions describe image-resizer --gen2 --region=$Region --format="value(serviceConfig.uri)"
Assert-LastExitCode "Failed to resolve image-resizer URL."

$cpuSort = & $gcloudCmd functions describe cpu-sort --gen2 --region=$Region --format="value(serviceConfig.uri)"
Assert-LastExitCode "Failed to resolve cpu-sort URL."

& $gcloudCmd storage buckets add-iam-policy-binding $bucketUri `
    --member="serviceAccount:$runServiceAccount" `
    --role="roles/storage.objectAdmin" | Out-Null
Assert-LastExitCode "Failed to grant bucket write access on $bucketUri to $runServiceAccount."

$envVars = @(
    "PROJECT_ID=$ProjectId",
    "REGION=$Region",
    "BUCKET_NAME=$BucketName",
    "API_HANDLER_URL=$apiHandler",
    "IMAGE_RESIZER_URL=$imageResizer",
    "CPU_SORT_URL=$cpuSort"
) -join ","

& $gcloudCmd run deploy $ServiceName `
    --source=.\k6_runner_service `
    --region=$Region `
    --service-account=$runServiceAccount `
    --cpu=2 `
    --memory=2Gi `
    --timeout=1200 `
    --concurrency=1 `
    --max-instances=1 `
    --no-allow-unauthenticated `
    --set-env-vars=$envVars | Out-Null
Assert-LastExitCode "Failed to deploy Cloud Run service $ServiceName."

$serviceUrl = & $gcloudCmd run services describe $ServiceName --region=$Region --format="value(status.url)"
Assert-LastExitCode "Failed to resolve Cloud Run service URL."

& $gcloudCmd run services add-iam-policy-binding $ServiceName `
    --region=$Region `
    --member="serviceAccount:$schedulerInvokerAccount" `
    --role="roles/run.invoker" | Out-Null
Assert-LastExitCode "Failed to grant Cloud Run Invoker on $ServiceName to $schedulerInvokerAccount."

if (Test-GcloudSuccess @("scheduler", "jobs", "describe", $SchedulerJobName, "--location=$Region")) {
    & $gcloudCmd scheduler jobs update http $SchedulerJobName `
        --location=$Region `
        --schedule="*/15 * * * *" `
        --uri=$serviceUrl `
        --http-method=POST `
        --oidc-service-account-email=$schedulerInvokerAccount `
        --oidc-token-audience=$serviceUrl `
        --attempt-deadline=1200s | Out-Null
    Assert-LastExitCode "Failed to update Cloud Scheduler job $SchedulerJobName."
} else {
    & $gcloudCmd scheduler jobs create http $SchedulerJobName `
        --location=$Region `
        --schedule="*/15 * * * *" `
        --uri=$serviceUrl `
        --http-method=POST `
        --oidc-service-account-email=$schedulerInvokerAccount `
        --oidc-token-audience=$serviceUrl `
        --attempt-deadline=1200s | Out-Null
    Assert-LastExitCode "Failed to create Cloud Scheduler job $SchedulerJobName."
}

Write-Host "Cloud Run k6 scheduler deployed."
Write-Host "Service URL:" $serviceUrl
Write-Host "Scheduler job:" $SchedulerJobName
Write-Host "Bucket target: $bucketUri/k6-results/"
Write-Host "Runner service account:" $runServiceAccount
Write-Host "Scheduler invoker account:" $schedulerInvokerAccount
