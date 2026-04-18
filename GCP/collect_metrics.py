from datetime import datetime, timedelta, timezone

from google.cloud import monitoring_v3


client = monitoring_v3.MetricServiceClient()


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

    aggregation = monitoring_v3.Aggregation(
        {
            "alignment_period": {"seconds": 60},
            "per_series_aligner": monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
        }
    )

    metrics = {
        "request_count": 'metric.type="run.googleapis.com/request_count"',
        "request_latencies": 'metric.type="run.googleapis.com/request_latencies"',
        "container_start_latencies": 'metric.type="run.googleapis.com/container/start_latencies"',
    }

    resource_filter = (
        'resource.type="cloud_run_revision" '
        f'AND resource.labels.service_name="{function_name}" '
        f'AND resource.labels.location="{region}"'
    )

    results = {}
    for name, metric_filter in metrics.items():
        request = monitoring_v3.ListTimeSeriesRequest(
            {
                "name": project_name,
                "filter": f"{metric_filter} AND {resource_filter}",
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                "aggregation": aggregation,
            }
        )
        series = client.list_time_series(request=request)
        results[name] = [
            {
                "metric": point.value,
                "interval_end": point.interval.end_time.isoformat(),
            }
            for item in series
            for point in item.points
        ]
    return results
