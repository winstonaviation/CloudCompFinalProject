param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "us-central1",

    [Parameter(Mandatory = $false)]
    [string]$BucketName = ""
)

if (-not $BucketName) {
    $BucketName = "$ProjectId-cloudcomp-test-bucket"
}

gcloud config set project $ProjectId | Out-Null

$services = @(
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com"
)

gcloud services enable $services | Out-Null

$bucketExists = gcloud storage buckets describe "gs://$BucketName" 2>$null
if (-not $?) {
    gcloud storage buckets create "gs://$BucketName" --location=$Region | Out-Null
}

$envVars = "TEST_BUCKET=$BucketName"

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

Write-Host "Deployment complete."
Write-Host "Bucket: gs://$BucketName"
Write-Host "api-handler URL:" (gcloud functions describe api-handler --gen2 --region=$Region --format="value(serviceConfig.uri)")
Write-Host "image-resizer URL:" (gcloud functions describe image-resizer --gen2 --region=$Region --format="value(serviceConfig.uri)")
Write-Host "cpu-sort URL:" (gcloud functions describe cpu-sort --gen2 --region=$Region --format="value(serviceConfig.uri)")
