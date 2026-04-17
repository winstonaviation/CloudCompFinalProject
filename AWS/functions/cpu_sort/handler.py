import json, random

SEED, SIZE = 42, 100_000

def handler(event, context):
    rng = random.Random(SEED)
    data = [rng.random() for _ in range(SIZE)]
    sorted_data = sorted(data)
    return {"statusCode": 200, "body": json.dumps({"first": sorted_data[0], "last": sorted_data[-1]})}