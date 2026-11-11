FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS dependencies
WORKDIR /build
COPY requirements-service.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: --prefix=/install -r requirements-service.txt

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY --from=dependencies /install /usr/local
WORKDIR /app
COPY --chown=10001:10001 steam_service ./steam_service
COPY --chown=10001:10001 model ./model
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/app/model \
    AUTH_MODE=entra \
    MAX_CONCURRENT_PREDICTIONS=4 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    HOME=/tmp
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]
CMD ["python", "-m", "uvicorn", "steam_service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "32", "--backlog", "128", "--timeout-keep-alive", "5", "--timeout-graceful-shutdown", "30", "--no-access-log"]
