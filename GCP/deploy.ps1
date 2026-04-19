param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "us-central1",

    [Parameter(Mandatory = $false)]
    [string]$BucketName = "",

    [Parameter(Mandatory = $false)]
    [switch]$SkipEnableServices
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param(
        [string]$Message
    )

    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

if (-not $BucketName) {
    $BucketName = "$ProjectId-cloudcomp-test-bucket"
}

gcloud config set project $ProjectId | Out-Null
Assert-LastExitCode "Failed to set the active gcloud project to $ProjectId."

$services = @(
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com"
)

if (-not $SkipEnableServices) {
    gcloud services enable $services | Out-Null
    Assert-LastExitCode (
        "Failed to enable required Google Cloud services. " +
        "Your account likely needs Service Usage Admin permissions " +
        "(roles/serviceusage.serviceUsageAdmin), project owner access, " +
        "or the APIs must be enabled by an administrator first."
    )
}

$bucketUri = "gs://$BucketName"
gcloud storage buckets describe $bucketUri --project=$ProjectId 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gcloud storage buckets create $bucketUri --location=$Region --project=$ProjectId | Out-Null
    Assert-LastExitCode (
        "Failed to create bucket $bucketUri. Bucket names are globally unique, so " +
        "this usually means the name is already taken or the project lacks permission."
    )
}

gcloud storage buckets describe $bucketUri --project=$ProjectId | Out-Null
Assert-LastExitCode "Bucket $bucketUri still is not accessible after creation."

$envVars = "TEST_BUCKET=$BucketName"
$metricsEnvVars = "PROJECT_ID=$ProjectId,REGION=$Region,BUCKET_NAME=$BucketName"

gcloud functions deploy api-handler `
    --gen2 `
    --runtime=python312 `
    --region=$Region `
    --source=functions/api_handler `
    --entry-point=handler `
    --trigger-http `
    --allow-unauthenticated `
    --memory=512Mi `
    --timeout=30s `
    --set-env-vars=$envVars | Out-Null
Assert-LastExitCode "Failed to deploy api-handler."

gcloud functions deploy image-resizer `
    --gen2 `
    --runtime=python312 `
    --region=$Region `
    --source=functions/image_resizer `
    --entry-point=handler `
    --trigger-http `
    --allow-unauthenticated `
    --memory=512Mi `
    --timeout=30s `
    --set-env-vars=$envVars | Out-Null
Assert-LastExitCode "Failed to deploy image-resizer."

gcloud functions deploy cpu-sort `
    --gen2 `
    --runtime=python312 `
    --region=$Region `
    --source=functions/cpu_sort `
    --entry-point=handler `
    --trigger-http `
    --allow-unauthenticated `
    --memory=512Mi `
    --timeout=30s | Out-Null
Assert-LastExitCode "Failed to deploy cpu-sort."

gcloud functions deploy metrics-collector `
    --gen2 `
    --runtime=python312 `
    --region=$Region `
    --source=functions/metrics_collector `
    --entry-point=handler `
    --trigger-http `
    --allow-unauthenticated `
    --memory=512Mi `
    --timeout=30s `
    --set-env-vars=$metricsEnvVars | Out-Null
Assert-LastExitCode "Failed to deploy metrics-collector."

Write-Host "Deployment complete."
Write-Host "Bucket: $bucketUri"
Write-Host "api-handler URL:" (gcloud functions describe api-handler --gen2 --region=$Region --format="value(serviceConfig.uri)")
Write-Host "image-resizer URL:" (gcloud functions describe image-resizer --gen2 --region=$Region --format="value(serviceConfig.uri)")
Write-Host "cpu-sort URL:" (gcloud functions describe cpu-sort --gen2 --region=$Region --format="value(serviceConfig.uri)")
Write-Host "metrics-collector URL:" (gcloud functions describe metrics-collector --gen2 --region=$Region --format="value(serviceConfig.uri)")
