import http from 'k6/http';
import { check } from 'k6';
import { generateUser, registerUser, authHeaders, createPost, getHomeFeed, searchPosts, followUser } from './helpers.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  vus: 1,
  iterations: 1,
};

export default function () {
  console.log('Running smoke test...');

  const user = generateUser();
  const auth = registerUser(user);
  check(auth, { 'auth: registered': (a) => a && a.access_token });

  if (!auth) {
    console.error('Registration failed, aborting');
    return;
  }

  const post = createPost(auth.access_token, 'Smoke test post: verifying all endpoints work');
  check(post, { 'post: created': (p) => p && p.id });

  const feed = getHomeFeed(auth.access_token);
  check(feed, { 'feed: returned': (f) => f && f.entries !== undefined });

  const search = searchPosts(auth.access_token, 'smoke test');
  check(search, { 'search: returned': (s) => s && s.results !== undefined });

  const otherUser = generateUser();
  const otherAuth = registerUser(otherUser);
  if (otherAuth) {
    createPost(otherAuth.access_token, 'Post from another user for feed testing');
    followUser(auth.access_token, otherAuth.user_id);

    const feed2 = getHomeFeed(auth.access_token);
    check(feed2, { 'feed after follow: has entries': (f) => f && f.entries && f.entries.length > 0 });
  }

  console.log('Smoke test complete');
}
