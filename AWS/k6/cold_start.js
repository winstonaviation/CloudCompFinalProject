import http from 'k6/http';
import { sleep } from 'k6';

export const options = { vus: 1, iterations: 1 };

export default function () {
  const res = http.get(__ENV.ENDPOINT);
  console.log(`status=${res.status} duration=${res.timings.duration}ms`);
}