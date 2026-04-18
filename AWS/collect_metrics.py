import boto3, json
from datetime import datetime, timedelta, timezone

cw = boto3.client('cloudwatch', region_name='us-east-1')

def get_lambda_metrics(function_name, start, end):
    metrics = ['Duration', 'Invocations', 'Errors', 'Throttles', 'InitDuration']
    results = {}
    for m in metrics:
        resp = cw.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName=m,
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start,
            EndTime=end,
            Period=60,
            Statistics=['Sum', 'Average', 'Maximum'],
        )
        results[m] = resp['Datapoints']
    return results