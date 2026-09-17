// Shared helpers for k6 load tests
import http from 'k6/http';
import { check, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Custom metrics
export const errorRate = new Rate('errors');
export const authLatency = new Trend('auth_latency', true);
export const postLatency = new Trend('post_latency', true);
export const feedLatency = new Trend('feed_latency', true);
export const searchLatency = new Trend('search_latency', true);

// Config
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_PREFIX = `${BASE_URL}/api/v1`;

// Generate unique user data
let userCounter = 0;
export function generateUser() {
  userCounter++;
  const id = `loadtest-${Date.now()}-${userCounter}`;
  return {
    email: `${id}@loadtest.example.com`,
    username: id,
    display_name: `Load Test User ${userCounter}`,
    password: 'LoadTest-Password-123!',
  };
}

// Auth helper: register and return tokens
export function registerUser(user) {
  const payload = JSON.stringify({
    email: user.email,
    username: user.username,
    display_name: user.display_name,
    password: user.password,
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(`${API_PREFIX}/auth/register`, payload, params);

  const success = check(res, {
    'register: status 201': (r) => r.status === 201,
  });
  errorRate.add(!success);

  if (res.status === 201) {
    const body = res.json();
    return {
      access_token: body.access_token,
      refresh_token: body.refresh_token,
      user_id: body.user_id,
    };
  }

  // Try login if registration fails (user might already exist)
  return loginUser(user);
}

export function loginUser(user) {
  const payload = JSON.stringify({
    username: user.username,
    password: user.password,
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(`${API_PREFIX}/auth/login`, payload, params);

  const success = check(res, {
    'login: status 200': (r) => r.status === 200,
  });
  errorRate.add(!success);

  if (res.status === 200) {
    const body = res.json();
    return {
      access_token: body.access_token,
      refresh_token: body.refresh_token,
      user_id: body.user_id,
    };
  }
  return null;
}

// Auth header helper
export function authHeaders(token) {
  return {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  };
}

// Follow a user
export function followUser(token, followeeId) {
  const res = http.post(
    `${API_PREFIX}/graph/${followeeId}/follow`,
    null,
    authHeaders(token)
  );
  return res.status === 201 || res.status === 409; // 409 = already following
}

// Create a post
export function createPost(token, text) {
  const payload = JSON.stringify({ text });
  const res = http.post(
    `${API_PREFIX}/posts`,
    payload,
    authHeaders(token)
  );

  const success = check(res, {
    'create post: status 201': (r) => r.status === 201,
  });
  errorRate.add(!success);

  return res.status === 201 ? res.json() : null;
}

// Read home feed
export function getHomeFeed(token, limit = 20) {
  const res = http.get(
    `${API_PREFIX}/timeline/home?limit=${limit}`,
    authHeaders(token)
  );

  const success = check(res, {
    'home feed: status 200': (r) => r.status === 200,
  });
  errorRate.add(!success);

  return res.status === 200 ? res.json() : null;
}

// Search posts
export function searchPosts(token, query) {
  const res = http.get(
    `${API_PREFIX}/search/posts?q=${encodeURIComponent(query)}`,
    authHeaders(token)
  );

  const success = check(res, {
    'search: status 200': (r) => r.status === 200,
  });
  errorRate.add(!success);

  return res.status === 200 ? res.json() : null;
}
