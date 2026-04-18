import json
import random


SEED = 42
SIZE = 100_000


def handler(request):
    rng = random.Random(SEED)
    data = [rng.random() for _ in range(SIZE)]
    sorted_data = sorted(data)
    body = {"first": sorted_data[0], "last": sorted_data[-1]}
    return (json.dumps(body), 200, {"Content-Type": "application/json"})
