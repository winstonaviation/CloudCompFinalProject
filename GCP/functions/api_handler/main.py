import json
import time


def handler(request):
    start = time.perf_counter()
    result = sum(i * i for i in range(1000))
    duration_ms = (time.perf_counter() - start) * 1000
    body = {"result": result, "compute_ms": round(duration_ms, 3)}
    return (json.dumps(body), 200, {"Content-Type": "application/json"})
