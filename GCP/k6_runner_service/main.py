import json
import math
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify
from google.cloud import storage


APP_ROOT = Path(__file__).resolve().parent
K6_DIR = APP_ROOT / "k6"
SCENARIOS = {
    "low_load": K6_DIR / "low_load.js",
    "medium_load": K6_DIR / "medium_load.js",
    "burst": K6_DIR / "burst.js",
    "cold_start": K6_DIR / "cold_start.js",
}
SERVICES = {
    "api-handler": "API_HANDLER_URL",
    "image-resizer": "IMAGE_RESIZER_URL",
    "cpu-sort": "CPU_SORT_URL",
}
storage_client = storage.Client()
app = Flask(__name__)


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
            f"k6 failed for {scenario_name} against {endpoint}:\n"
            f"{completed.stderr or completed.stdout}"
        )

    scenario_result = summarize_k6_points(output_path)
    output_path.unlink(missing_ok=True)
    scenario_result["script"] = script_path.name
    return scenario_result


def upload_results(results, bucket_name):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    object_name = f"k6-results/{timestamp}.json"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(json.dumps(results, indent=2), content_type="application/json")
    return f"gs://{bucket_name}/{object_name}"


def collect_results():
    project_id = os.environ.get("PROJECT_ID", "").strip() or None
    region = os.environ.get("REGION", "us-east1").strip()
    bucket_name = os.environ.get("BUCKET_NAME", "gcp-testing-kt").strip()
    services = {
        service_name: os.environ[env_var].strip()
        for service_name, env_var in SERVICES.items()
    }

    results = {
        "project_id": project_id,
        "region": region,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "services": {service_name: {} for service_name in services},
    }

    for scenario_name in SCENARIOS:
        with ThreadPoolExecutor(max_workers=len(services)) as executor:
            future_map = {
                executor.submit(run_scenario, scenario_name, endpoint): service_name
                for service_name, endpoint in services.items()
            }

            for future, service_name in future_map.items():
                results["services"][service_name][scenario_name] = future.result()

    results["uploaded_to"] = upload_results(results, bucket_name)
    return results


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/", methods=["GET", "POST"])
def run_all():
    try:
        return jsonify(collect_results())
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
