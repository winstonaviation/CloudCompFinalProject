for i in $(seq 1 10); do
  echo "=== Cold start iteration $i ==="

  aws lambda update-function-configuration \
    --function-name AWSCloudproject-ApiHandler-7Zt4naS4hl9Y \
    --environment "Variables={TEST_BUCKET=$BUCKET,RUN_ID=cold_${i}}" --region us-east-1 > /dev/null &
  aws lambda update-function-configuration \
    --function-name AWSCloudproject-ImageResizer-NXVHlqwurwya \
    --environment "Variables={TEST_BUCKET=$BUCKET,RUN_ID=cold_${i}}" --region us-east-1 > /dev/null &
  aws lambda update-function-configuration \
    --function-name AWSCloudproject-CpuSort-dZd7kkiraGtO \
    --environment "Variables={TEST_BUCKET=$BUCKET,RUN_ID=cold_${i}}" --region us-east-1 > /dev/null &
  wait

  sleep 5

  k6 run -e ENDPOINT=$API_EP    --out json=results/cold_api_run1_iter${i}.json    cold_start.js &
  k6 run -e ENDPOINT=$RESIZE_EP --out json=results/cold_resize_run1_iter${i}.json cold_start.js &
  k6 run -e ENDPOINT=$SORT_EP   --out json=results/cold_sort_run1_iter${i}.json   cold_start.js &
  wait

  echo "Iteration $i complete. Idling 5 minutes..."
  sleep 300
done

echo "=== Cold start run 1 complete ==="