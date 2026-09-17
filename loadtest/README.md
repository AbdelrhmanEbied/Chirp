# Load Testing

K6-based load tests for the Chirp platform.

## Prerequisites

Install k6: https://k6.io/docs/get-started/installation/

## Tests

### Smoke Test
Quick verification that all endpoints work:
```bash
k6 run loadtest/smoke.js
```

### Critical Path Test
Simulates the core user journey (register → follow → post → feed → search):
```bash
# Default: 10 VUs for 30s
k6 run loadtest/critical_path.js

# Sustained load: 100 VUs for 5 minutes
k6 run --vus 100 --duration 5m loadtest/critical_path.js

# Against a specific URL
k6 run --env BASE_URL=http://your-alb-url loadtest/critical_path.js
```

### Soak Test
Extended 30-minute test to find memory leaks and performance degradation:
```bash
k6 run loadtest/soak.js
```

## Metrics

The tests track:
- `http_req_duration` - HTTP request latency (p50, p95, p99)
- `errors` - Error rate
- `register_duration` - Registration latency
- `feed_duration` - Feed read latency
- `post_duration` - Post creation latency
- `search_duration` - Search latency

## Thresholds

Default thresholds (configurable in each script):
- p95 latency < 500ms
- p99 latency < 1000ms
- Error rate < 10%

## Expected Baseline (1M users)

For a 1M user platform:
- **Auth**: ~500 RPS, p95 < 200ms
- **Post creation**: ~200 RPS, p95 < 150ms
- **Feed read**: ~2000 RPS, p95 < 100ms (fan-out-on-write)
- **Search**: ~500 RPS, p95 < 200ms

These are targets; actual numbers depend on hardware and database tuning.
