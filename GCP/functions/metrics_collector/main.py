import json
import os
import re
from datetime import datetime, timedelta, timezone

import google.auth
from google.api_core import exceptions as gcloud_exceptions
from google.cloud import monitoring_v3
from google.cloud import storage


client = monitoring_v3.MetricServiceClient()
storage_client = storage.Client()
PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
ALIGNER = monitoring_v3.Aggregation.Aligner


def resolve_project_id():
    candidates = [
        os.environ.get("PROJECT_ID"),
        os.environ.get("GOOGLE_CLOUD_PROJECT"),
        os.environ.get("GCP_PROJECT"),
        os.environ.get("GCLOUD_PROJECT"),
        storage_client.project,
    ]

    _, auth_project = google.auth.default()
    candidates.append(auth_project)

    for candidate in candidates:
        if not candidate:
            continue

        project_id = candidate.strip()
        if project_id.startswith("projects/"):
            project_id = project_id.split("/", 1)[1].strip()

        if PROJECT_ID_PATTERN.fullmatch(project_id):
            return project_id

    raise ValueError(
        "Unable to determine a valid GCP project id. "
        "Set PROJECT_ID, GOOGLE_CLOUD_PROJECT, GCP_PROJECT, or GCLOUD_PROJECT."
    )


def extract_typed_value(typed_value):
    typed_value_pb = getattr(typed_value, "_pb", typed_value)
    value_kind = typed_value_pb.WhichOneof("value")

    if value_kind == "double_value":
        return typed_value.double_value
    if value_kind == "int64_value":
        return typed_value.int64_value
    if value_kind == "bool_value":
        return typed_value.bool_value
    if value_kind == "string_value":
        return typed_value.string_value
    if value_kind == "distribution_value":
        dist = typed_value.distribution_value
        return {
            "count": dist.count,
            "mean": dist.mean,
        }

    return None


def get_function_metrics(project_id, region, function_name, minutes=30):
    project_name = f"projects/{project_id}"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)

    interval = monitoring_v3.TimeInterval(
        {
            "end_time": {"seconds": int(end_time.timestamp())},
            "start_time": {"seconds": int(start_time.timestamp())},
        }
    )

    metrics = {
        "request_count": {
            "filter": 'metric.type="run.googleapis.com/request_count"',
            "aligner": ALIGNER.ALIGN_SUM,
        },
        "request_latencies_p95": {
            "filter": 'metric.type="run.googleapis.com/request_latencies"',
            "aligner": ALIGNER.ALIGN_PERCENTILE_95,
        },
        "container_start_latencies_p95": {
            "filter": 'metric.type="run.googleapis.com/container/startup_latencies"',
            "aligner": ALIGNER.ALIGN_PERCENTILE_95,
        },
    }

    resource_filter = (
        'resource.type="cloud_run_revision" '
        f'AND resource.labels.service_name="{function_name}" '
        f'AND resource.labels.location="{region}"'
    )

    results = {}
    for name, metric_config in metrics.items():
        aggregation = monitoring_v3.Aggregation(
            {
                "alignment_period": {"seconds": 60},
                "per_series_aligner": metric_config["aligner"],
            }
        )
        request = monitoring_v3.ListTimeSeriesRequest(
            {
                "name": project_name,
                "filter": f'{metric_config["filter"]} AND {resource_filter}',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation,
            }
        )
        metric_points = []
        try:
            series = client.list_time_series(request=request)
            for item in series:
                for point in item.points:
                    metric_points.append(
                        {
                            "metric": extract_typed_value(point.value),
                            "aligner": ALIGNER(metric_config["aligner"]).name,
                            "interval_end": point.interval.end_time.isoformat(),
                        }
                    )
        except gcloud_exceptions.NotFound as exc:
            metric_points = [
                {
                    "metric": None,
                    "aligner": ALIGNER(metric_config["aligner"]).name,
                    "warning": str(exc),
                }
            ]

        results[name] = metric_points

    return results


def handler(request):
    try:
        project_id = resolve_project_id()
        region = os.environ.get("REGION", "us-central1").strip()
        bucket_name = request.args.get("bucket", "").strip()
        if not bucket_name:
            bucket_name = os.environ.get("BUCKET_NAME", "").strip()
        if not bucket_name:
            bucket_name = os.environ.get("TEST_BUCKET", "").strip()

        if not bucket_name:
            bucket_name = "gcp-testing-kt"

        print(f"DEBUG: Using Project ID: [{project_id}]")

        functions_to_check = [
            "cpu-sort",
            "image-resizer",
            "api-handler",
        ]

        all_results = {
            "project_id": project_id,
            "region": region,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "services": {},
        }

        for function_name in functions_to_check:
            all_results["services"][function_name] = get_function_metrics(
                project_id=project_id,
                region=region,
                function_name=function_name,
                minutes=30,
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        blob_name = f"metrics/{timestamp}.json"

        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            raise ValueError(
                f'Bucket "{bucket_name}" does not exist. '
                "Create it first or redeploy with BUCKET_NAME set to an existing bucket."
            )

        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            json.dumps(all_results, indent=2),
            content_type="application/json",
        )

        return (
            json.dumps(
                {
                    "status": "ok",
                    "saved_to": f"gs://{bucket_name}/{blob_name}",
                    "services_checked": functions_to_check,
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )
    except Exception as exc:
        return (
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
