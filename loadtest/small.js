import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import http from 'k6/http';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API = `${BASE_URL}/api/v1`;
const errorRate = new Rate('errors');
const latency = new Trend('latency', true);

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    errors: ['rate<0.1'],
  },
};

let counter = 0;

function register() {
  counter++;
  const id = `small-${Date.now()}-${counter}`;
  const res = http.post(`${API}/auth/register`, JSON.stringify({
    email: `${id}@test.com`,
    username: id,
    password: 'TestPassword123!',
  }), { headers: { 'Content-Type': 'application/json' } });
  errorRate.add(res.status !== 201);
  return res.status === 201 ? res.json() : null;
}

function authHeaders(token) {
  return { headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` } };
}

export default function () {
  const user = register();
  if (!user) return;

  const h = authHeaders(user.access_token);

  // Create a post
  const postRes = http.post(`${API}/posts`, JSON.stringify({ text: `Test post ${counter}` }), h);
  errorRate.add(postRes.status !== 201);

  // Read feed
  const feedRes = http.get(`${API}/timeline/home?limit=10`, h);
  errorRate.add(feedRes.status !== 200);
  latency.add(feedRes.timings.duration);

  // Search
  const searchRes = http.get(`${API}/search?q=test`, h);
  errorRate.add(searchRes.status !== 200);

  check(null, {
    'register ok': () => user !== null,
    'post created': () => postRes.status === 201,
    'feed readable': () => feedRes.status === 200,
    'search works': () => searchRes.status === 200,
  });
}
