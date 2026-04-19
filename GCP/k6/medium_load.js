import http from 'k6/http';

export const options = {
  scenarios: {
    medium: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 100,
    },
  },
};

export default function () {
  http.get(__ENV.ENDPOINT);
}
