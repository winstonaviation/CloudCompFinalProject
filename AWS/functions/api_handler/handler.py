import json, time

def handler(event, context):
    start = time.perf_counter()
    result = sum(i * i for i in range(1000)) 
    duration_ms = (time.perf_counter() - start) * 1000
    return {
        "statusCode": 200,
        "body": json.dumps({"result": result, "compute_ms": round(duration_ms, 3)})
    }