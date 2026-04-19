import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  vus: 1,
  iterations: 5,
};

export default function () {
  http.get(__ENV.ENDPOINT);
  sleep(60);
}
