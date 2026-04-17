import json, os, boto3
from PIL import Image
from io import BytesIO
import load_dotenv

load_dotenv()

s3 = boto3.client("s3")
BUCKET = os.environ["TEST_BUCKET"]
KEY    = "test_image.jpg"
TARGET = (800, 600)

def handler(event, context):
    obj = s3.get_object(Bucket=BUCKET, Key=KEY)
    img = Image.open(BytesIO(obj["Body"].read()))
    buf = BytesIO()
    img.resize(TARGET, Image.LANCZOS).save(buf, format="JPEG")
    return {"statusCode": 200, "body": json.dumps({"bytes_out": buf.tell()})}