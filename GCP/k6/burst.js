import http from 'k6/http';

export const options = {
  scenarios: {
    burst: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 1000 },
        { duration: '5s', target: 0 },
      ],
    },
  },
};

export default function () {
  http.get(__ENV.ENDPOINT);
}
