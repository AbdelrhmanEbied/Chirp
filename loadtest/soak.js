import { sleep } from 'k6';
import {
  generateUser,
  registerUser,
  followUser,
  createPost,
  getHomeFeed,
  searchPosts,
} from './helpers.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export const options = {
  vus: 50,
  duration: '30m',
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    errors: ['rate<0.05'],
  },
};

let userTokens = [];

export function setup() {
  console.log('Setting up soak test...');

  for (let i = 0; i < 20; i++) {
    const user = generateUser();
    const auth = registerUser(user);
    if (auth) {
      userTokens.push(auth.access_token);

      for (let j = Math.max(0, i - 5); j < i; j++) {
        
      }
    }
    sleep(0.1);
  }

  for (let i = 0; i < 10; i++) {
    if (userTokens[i % userTokens.length]) {
      createPost(
        userTokens[i % userTokens.length],
        `Soak test seed post ${i}: testing long-running performance`
      );
    }
  }

  console.log(`Soak test setup complete: ${userTokens.length} users created`);
  return { userTokens };
}

export default function (data) {
  if (!data.userTokens || data.userTokens.length === 0) return;

  const token = data.userTokens[__VU % data.userTokens.length];

  const rand = Math.random();

  if (rand < 0.4) {
    
    getHomeFeed(token, 20);
  } else if (rand < 0.6) {
    
    createPost(token, `Soak test post from VU ${__VU} at iteration ${__ITER}`);
  } else if (rand < 0.8) {
    
    const queries = ['test', 'load', 'performance', 'soak'];
    searchPosts(token, queries[Math.floor(Math.random() * queries.length)]);
  } else {
    
  }

  sleep(Math.random() * 3 + 1); 
}

export function teardown(data) {
  console.log('Soak test complete');
}
