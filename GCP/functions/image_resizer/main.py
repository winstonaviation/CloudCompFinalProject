import json
import os
from io import BytesIO

from google.cloud import storage
from PIL import Image


BUCKET = os.environ["TEST_BUCKET"]
KEY = "test_image.jpg"
TARGET = (800, 600)
storage_client = storage.Client()


def handler(request):
    bucket = storage_client.bucket(BUCKET)
    blob = bucket.blob(KEY)
    img = Image.open(BytesIO(blob.download_as_bytes()))

    buf = BytesIO()
    img.resize(TARGET, Image.LANCZOS).save(buf, format="JPEG")

    body = {"bytes_out": buf.tell()}
    return (json.dumps(body), 200, {"Content-Type": "application/json"})
