# Chirp

A Twitter-like microservices platform deployed on AWS EKS. The focus of this project is **not** the social media application itself — it is the **infrastructure, deployment automation, and distributed systems engineering** required to run 11 microservices in production.

---

## What This Project Demonstrates

| Area | What was built |
|------|---------------|
| **Infrastructure as Code** | Terraform modules for VPC, EKS, RDS, ElastiCache, S3, CloudFront, ECR, IAM |
| **Container Orchestration** | Kubernetes manifests for 11 services, workers, ingress, HPA, init jobs |
| **Deployment Automation** | Single `deploy.sh` script — provisions infra, builds images, runs migrations, deploys everything |
| **Database per Service** | 10 independent PostgreSQL databases on a single RDS instance |
| **Event-Driven Architecture** | Redis Streams as the event bus with at-least-once delivery |
| **API Gateway Pattern** | Gateway service aggregating 10 backend services behind a single ALB |
| **Observability** | Prometheus + Grafana monitoring stack with custom dashboards |
| **Load Testing** | k6 scripts (smoke, critical path, soak, stress) simulating real user traffic |
| **Security** | HS256 JWTs, service-level auth, RDS encryption, VPC isolation, SSL enforcement |

## Architecture

```
                    INTERNET
                       |
              +--------v--------+
              |  CloudFront CDN |  (frontend static assets)
              +--------+--------+
                       |
              +--------v--------+
              |  ALB (public)   |  (TLS termination, rate limiting)
              +--------+--------+
                       |
              +--------v--------+
              |  API Gateway    |  (port 8000, request routing)
              +--------+--------+
                       |
    +------------------+------------------+
    |         |        |        |         |
  auth     user     post     graph    timeline   ... (10 services)
 (8001)   (8002)   (8003)   (8004)   (8005)
    |         |        |        |         |
  [DB]      [DB]     [DB]     [DB]      [DB]     (10 PostgreSQL DBs)
    |         |        |        |         |
    +---------+--------+--------+---------+
                       |
              +--------v--------+
              |  Redis Streams  |  (event bus, cache)
              +-----------------+
```

**11 Services**: gateway, auth, user, post, graph, timeline, search, notification, messaging, media, moderation

**Tech Stack**: Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16, Redis 7, Docker, Kubernetes (EKS 1.31), Terraform, AWS

## Quick Start — Deploy to AWS

```bash
# One command does everything
./deploy.sh
```

This provisions the full AWS stack and deploys all services:

1. **VPC** — 3 AZs, public/private subnets, NAT gateway
2. **EKS** — managed node group (t3.small, 2 nodes)
3. **RDS** — PostgreSQL 16 (db.t3.micro)
4. **ElastiCache** — Redis 7 (cache.t3.micro)
5. **S3** — media storage + frontend hosting
6. **CloudFront** — CDN for frontend
7. **ECR** — container registry for all images
8. **Kubernetes** — all services, ingress, monitoring, migrations

### Commands

```bash
./deploy.sh              # deploy (idempotent, skips what's done)
./deploy.sh --force      # re-deploy everything
./destroy.sh             # tear down all AWS resources
```

### After Deployment

```bash
# Get the URLs
ALB_DNS=$(kubectl get ingress gateway-ingress -n chirp-prod -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
CF_DOMAIN=$(terraform -chdir=infra/terraform output -raw cloudfront_domain)

echo "API:      http://$ALB_DNS"
echo "Frontend: https://$CF_DOMAIN"
```

## Local Development

```bash
make up          # build and start everything
make health      # check service readiness
make test        # run unit tests
make seed SIZE=small   # generate test data
```

```bash
# Register a user
curl -s localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"ada@example.com","username":"ada",
       "display_name":"Ada Lovelace","password":"analytical-engine-1843"}'
```

Interactive API docs: `http://localhost:8000/docs`

## Running Tests

```bash
make test               # unit tests (SQLite, ~3s)
make test-integration   # against PostgreSQL
```

### Load Tests

```bash
k6 run --env BASE_URL=http://<ALB-DNS> loadtest/smoke.js
k6 run --env BASE_URL=http://<ALB-DNS> loadtest/critical_path.js
k6 run --env BASE_URL=http://<ALB-DNS> loadtest/soak.js
```

| Test | VUs | Duration | Purpose |
|------|-----|----------|---------|
| smoke | 1 | instant | Verify all endpoints work |
| critical_path | 85 | 30s | Core user journey (register, post, feed, search) |
| small | 10 | 30s | Light load |
| medium | 25-50 | 2min | Ramping traffic with mixed operations |
| large | 50-200 | 5min | Stress test — find the breaking point |
| soak | 50 | 30min | Memory leaks and degradation |

## Project Layout

```
chirp/
├── libs/chirp-common/         shared platform library (config, logging, errors, events)
├── services/
│   ├── auth/                  authentication, sessions, JWT tokens
│   ├── user/                  profiles, usernames, follower counters
│   ├── post/                  posts, likes, reposts, bookmarks
│   ├── graph/                 follow/unfollow, block, mute
│   ├── timeline/              fan-out-on-write home feed
│   ├── search/                full-text search + trending hashtags
│   ├── notification/          event-driven notifications
│   ├── messaging/             direct messages
│   ├── media/                 file uploads to S3
│   ├── moderation/            reports and admin actions
│   └── gateway/               API gateway (BFF pattern)
├── web/                       React frontend (Vite)
├── infra/terraform/           AWS infrastructure (VPC, EKS, RDS, Redis, S3, CloudFront)
├── k8s/
│   ├── base/                  configmap, secrets, init-db job
│   ├── services/              deployment + service + HPA + migration job per service
│   ├── ingress/               ALB ingress rules
│   └── monitoring/            Prometheus + Grafana
├── loadtest/                  k6 load testing scripts
├── tests/                     shared integration tests
├── docs/                      architecture reference, decisions, failure modes
├── deploy.sh                  one-command deployment
└── destroy.sh                 clean teardown
```

## Documentation

| Document | What it covers |
|----------|---------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Complete architecture reference (18 sections) |
| [docs/testing.md](docs/testing.md) | What is tested and how |
| [docs/scalability.md](docs/scalability.md) | What breaks at 10K, 100K, 1M users |
| [docs/failure-modes.md](docs/failure-modes.md) | What happens when each dependency dies |
| [docs/decisions.md](docs/decisions.md) | Design choices and alternatives |

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Service communication | HTTP + Redis Streams | HTTP for sync queries, events for async side effects |
| Database | PostgreSQL per service | Service data isolation, independent scaling |
| Event bus | Redis Streams | At-least-once delivery, no extra infrastructure |
| Timeline | Fan-out-on-write | O(1) feed reads, acceptable write amplification |
| Search | FTS + trigram | Combined exact and fuzzy matching |
| Auth | HS256 JWT | Local verification, no auth bottleneck |
| Deployment | EKS + RDS + ElastiCache | Managed services, production-ready |
| Instance types | t3.small | Free-tier eligible, enough for ~1M users |

## Infrastructure Costs (Estimated)

| Resource | Instance | Est. Monthly Cost |
|----------|----------|-------------------|
| EKS Cluster | — | ~$73 |
| EC2 Nodes (2x) | t3.small | ~$30 |
| RDS | db.t3.micro | ~$15 |
| ElastiCache | cache.t3.micro | ~$12 |
| S3 + CloudFront | — | ~$5 |
| NAT Gateway | — | ~$35 |
| **Total** | | **~$170/mo** |
