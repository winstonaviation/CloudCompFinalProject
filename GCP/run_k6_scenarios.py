import argparse
import json
import math
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
K6_DIR = ROOT / "k6"
GCLOUD_CANDIDATES = [
    shutil.which("gcloud"),
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Google",
        "Cloud SDK",
        "google-cloud-sdk",
        "bin",
        "gcloud.cmd",
    ),
    r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
]
SCENARIOS = {
    "low_load": K6_DIR / "low_load.js",
    "medium_load": K6_DIR / "medium_load.js",
    "burst": K6_DIR / "burst.js",
    "cold_start": K6_DIR / "cold_start.js",
}


def read_summary_metric(summary, metric_name):
    metric = summary.get("metrics", {}).get(metric_name, {})
    return metric.get("values", {})


def percentile(values, pct):
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]

    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize_k6_points(json_output_path):
    durations = []
    failed_samples = []
    iteration_samples = 0

    with json_output_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            if record.get("type") != "Point":
                continue

            metric_name = record.get("metric")
            value = record.get("data", {}).get("value")

            if metric_name == "http_req_duration":
                durations.append(float(value))
            elif metric_name == "http_req_failed":
                failed_samples.append(float(value))
            elif metric_name == "iteration_duration":
                iteration_samples += 1

    return {
        "http_req_duration_ms": {
            "avg": (sum(durations) / len(durations)) if durations else None,
            "min": min(durations) if durations else None,
            "med": percentile(durations, 0.50),
            "p90": percentile(durations, 0.90),
            "p95": percentile(durations, 0.95),
            "max": max(durations) if durations else None,
        },
        "iterations": iteration_samples,
        "requests": len(durations),
        "http_req_failed_rate": (
            sum(failed_samples) / len(failed_samples) if failed_samples else None
        ),
    }


def run_scenario(scenario_name, endpoint):
    script_path = SCENARIOS[scenario_name]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = Path(tmp.name)

    command = [
        "k6",
        "run",
        str(script_path),
        "-e",
        f"ENDPOINT={endpoint}",
        "--out",
        f"json={output_path}",
    ]

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"k6 failed for {scenario_name} against {endpoint}:\n{completed.stderr or completed.stdout}"
        )

    scenario_result = summarize_k6_points(output_path)
    output_path.unlink(missing_ok=True)
    scenario_result["script"] = script_path.name
    return scenario_result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run all GCP k6 scenarios and save summarized timings."
    )
    parser.add_argument("--project-id", required=False)
    parser.add_argument("--region", required=False, default="us-east1")
    parser.add_argument("--api-handler", required=True, help="URL for api-handler")
    parser.add_argument("--image-resizer", required=True, help="URL for image-resizer")
    parser.add_argument("--cpu-sort", required=True, help="URL for cpu-sort")
    parser.add_argument(
        "--out",
        required=False,
        default=str(ROOT / "k6_results.json"),
        help="Path to write the combined scenario summary JSON",
    )
    parser.add_argument(
        "--bucket",
        required=False,
        help="Optional GCS bucket name to upload the JSON summary into",
    )
    return parser.parse_args()


def upload_to_bucket(file_path, destination):
    gcloud_path = next(
        (candidate for candidate in GCLOUD_CANDIDATES if candidate and Path(candidate).exists()),
        None,
    )
    if not gcloud_path:
        raise RuntimeError("gcloud was not found in PATH or common install locations.")

    command = [gcloud_path, "storage", "cp", str(file_path), destination]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Failed to upload results to {destination}:\n{completed.stderr or completed.stdout}"
        )
    return destination


def main():
    args = parse_args()
    services = {
        "api-handler": args.api_handler,
        "image-resizer": args.image_resizer,
        "cpu-sort": args.cpu_sort,
    }

    results = {
        "project_id": args.project_id,
        "region": args.region,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "services": {},
    }

    for service_name in services:
        results["services"][service_name] = {}

    for scenario_name in SCENARIOS:
        with ThreadPoolExecutor(max_workers=len(services)) as executor:
            future_map = {
                executor.submit(run_scenario, scenario_name, endpoint): service_name
                for service_name, endpoint in services.items()
            }

            for future, service_name in future_map.items():
                results["services"][service_name][scenario_name] = future.result()

    out_path = Path(args.out)
    if args.bucket:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        uploaded_to = f"gs://{args.bucket}/k6-results/{timestamp}.json"
        results["uploaded_to"] = uploaded_to
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    if args.bucket:
        upload_to_bucket(out_path, uploaded_to)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
