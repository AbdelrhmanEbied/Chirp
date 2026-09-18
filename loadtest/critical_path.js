import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import {
  generateUser,
  registerUser,
  followUser,
  createPost,
  getHomeFeed,
  searchPosts,
  authHeaders,
} from './helpers.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

const errors = new Rate('errors');
const registerDuration = new Trend('register_duration', true);
const followDuration = new Trend('follow_duration', true);
const postDuration = new Trend('post_duration', true);
const feedDuration = new Trend('feed_duration', true);
const searchDuration = new Trend('search_duration', true);

export const options = {
  scenarios: {
    
    registration: {
      executor: 'constant-vus',
      vus: 5,
      duration: '30s',
    },
    
    feed_readers: {
      executor: 'constant-vus',
      vus: 50,
      duration: '30s',
      startTime: '5s',
    },
    
    posters: {
      executor: 'constant-vus',
      vus: 20,
      duration: '30s',
      startTime: '5s',
    },
    
    searchers: {
      executor: 'constant-vus',
      vus: 10,
      duration: '30s',
      startTime: '5s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    errors: ['rate<0.1'],
    register_duration: ['p(95)<1000'],
    feed_duration: ['p(95)<300'],
    post_duration: ['p(95)<300'],
    search_duration: ['p(95)<500'],
  },
};

let feedToken = null;
let postToken = null;
let searchToken = null;

export function setup() {
  console.log('Setting up load test...');

  const feedUser = generateUser();
  const feedAuth = registerUser(feedUser);
  if (feedAuth) feedToken = feedAuth.access_token;

  const postUser = generateUser();
  const postAuth = registerUser(postUser);
  if (postAuth) postToken = postAuth.access_token;

  const searchUser = generateUser();
  const searchAuth = registerUser(searchUser);
  if (searchAuth) searchToken = searchAuth.access_token;

  if (feedToken && postToken) {
    followUser(feedToken, postToken.user_id);
    for (let i = 0; i < 10; i++) {
      createPost(postToken, `Load test post ${i}: testing the timeline feed with some sample content`);
      sleep(0.1);
    }
  }

  if (searchToken) {
    for (let i = 0; i < 5; i++) {
      createPost(searchToken, `Search test post ${i}: machine learning and artificial intelligence`);
      sleep(0.1);
    }
  }

  console.log('Setup complete');
  return { feedToken, postToken, searchToken };
}

export default function (data) {
  const scenario = __SCENARIO;

  if (scenario === 'registration') {
    group('New User Registration', () => {
      const user = generateUser();
      const start = Date.now();
      const auth = registerUser(user);
      registerDuration.add(Date.now() - start);

      if (auth) {
        
        sleep(0.5);
        createPost(auth.access_token, `Hello world! This is my first post from load test user ${user.username}`);
      }
    });
  }

  if (scenario === 'feed_readers' && data.feedToken) {
    group('Feed Reading', () => {
      const start = Date.now();
      const feed = getHomeFeed(data.feedToken, 20);
      feedDuration.add(Date.now() - start);

      if (feed) {
        check(feed, {
          'feed has entries': (f) => f.entries && f.entries.length > 0,
        });
      }
    });
  }

  if (scenario === 'posters' && data.postToken) {
    group('Post Creation', () => {
      const text = `Load test post at ${new Date().toISOString()}: ${Math.random().toString(36).substring(7)}`;
      const start = Date.now();
      createPost(data.postToken, text);
      postDuration.add(Date.now() - start);
    });
  }

  if (scenario === 'searchers' && data.searchToken) {
    group('Search', () => {
      const queries = ['machine learning', 'hello world', 'load test', 'artificial intelligence'];
      const query = queries[Math.floor(Math.random() * queries.length)];

      const start = Date.now();
      const results = searchPosts(data.searchToken, query);
      searchDuration.add(Date.now() - start);

      if (results) {
        check(results, {
          'search returned results': (r) => r.results && r.results.length > 0,
        });
      }
    });
  }

  sleep(1);
}

export function teardown(data) {
  console.log('Load test complete');
}
