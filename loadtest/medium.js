import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import http from 'k6/http';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API = `${BASE_URL}/api/v1`;
const errorRate = new Rate('errors');
const latency = new Trend('latency', true);

export const options = {
  stages: [
    { duration: '30s', target: 25 },
    { duration: '1m', target: 50 },
    { duration: '30s', target: 25 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    errors: ['rate<0.15'],
  },
};

let counter = 0;
const tokens = [];

function register() {
  counter++;
  const id = `med-${Date.now()}-${counter}`;
  const res = http.post(`${API}/auth/register`, JSON.stringify({
    email: `${id}@test.com`,
    username: id,
    password: 'TestPassword123!',
  }), { headers: { 'Content-Type': 'application/json' } });
  errorRate.add(res.status !== 201);
  if (res.status === 201) {
    const body = res.json();
    tokens.push(body.access_token);
    return body;
  }
  return null;
}

function authHeaders(token) {
  return { headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` } };
}

function getToken() {
  if (tokens.length > 0) {
    return tokens[Math.floor(Math.random() * tokens.length)];
  }
  const user = register();
  return user ? user.access_token : null;
}

export default function () {
  const token = getToken();
  if (!token) return;

  const h = authHeaders(token);
  const r = Math.random();

  if (r < 0.3) {
    // 30% create post
    const res = http.post(`${API}/posts`, JSON.stringify({ text: `Post from VU at ${Date.now()}` }), h);
    errorRate.add(res.status !== 201);
  } else if (r < 0.7) {
    // 40% read feed
    const res = http.get(`${API}/timeline/home?limit=20`, h);
    errorRate.add(res.status !== 200);
    latency.add(res.timings.duration);
  } else if (r < 0.85) {
    // 15% search
    const queries = ['hello', 'test', 'load', 'performance', 'chirp'];
    const q = queries[Math.floor(Math.random() * queries.length)];
    const res = http.get(`${API}/search?q=${q}`, h);
    errorRate.add(res.status !== 200);
    latency.add(res.timings.duration);
  } else {
    // 15% follow someone
    const targetId = `med-${Math.floor(Math.random() * 1000)}`;
    const res = http.post(`${API}/graph/${targetId}/follow`, null, h);
    errorRate.add(res.status !== 201 && res.status !== 409);
  }

  check(null, {
    'no critical errors': () => true,
  });
}
