FROM chirp-base:latest AS builder

WORKDIR /srv

COPY services/gateway/pyproject.toml /srv/service/pyproject.toml
COPY services/gateway/app /srv/service/app

RUN pip install --no-cache-dir httpx redis

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-graceful-shutdown", "30", "--limit-max-requests", "10000"]
