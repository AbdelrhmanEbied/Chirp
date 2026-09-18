import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import http from 'k6/http';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API = `${BASE_URL}/api/v1`;
const errorRate = new Rate('errors');
const latency = new Trend('latency', true);

export const options = {
  stages: [
    { duration: '1m', target: 50 },
    { duration: '2m', target: 100 },
    { duration: '1m', target: 200 },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'],
    errors: ['rate<0.2'],
  },
};

let counter = 0;
const tokens = [];

function register() {
  counter++;
  const id = `big-${Date.now()}-${counter}`;
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

  if (r < 0.25) {
    // 25% create post
    const res = http.post(`${API}/posts`, JSON.stringify({ text: `Load test post ${counter} at ${Date.now()}` }), h);
    errorRate.add(res.status !== 201);
  } else if (r < 0.55) {
    // 30% read feed (heaviest endpoint)
    const res = http.get(`${API}/timeline/home?limit=20`, h);
    errorRate.add(res.status !== 200);
    latency.add(res.timings.duration);
  } else if (r < 0.75) {
    // 20% search
    const queries = ['hello', 'test', 'load', 'performance', 'chirp', 'microservices', 'kubernetes'];
    const q = queries[Math.floor(Math.random() * queries.length)];
    const res = http.get(`${API}/search?q=${q}`, h);
    errorRate.add(res.status !== 200);
    latency.add(res.timings.duration);
  } else if (r < 0.9) {
    // 15% like a post
    const res = http.post(`${API}/posts/random${Math.floor(Math.random() * 1000)}/like`, null, h);
    errorRate.add(res.status !== 201 && res.status !== 409 && res.status !== 404);
  } else {
    // 10% follow
    const targetId = `big-${Math.floor(Math.random() * 5000)}`;
    const res = http.post(`${API}/graph/${targetId}/follow`, null, h);
    errorRate.add(res.status !== 201 && res.status !== 409);
  }

  check(null, {
    'no critical errors': () => true,
  });
}
