# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PINGPLOTTER_HOST=0.0.0.0 \
    PINGPLOTTER_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates iputils-ping traceroute \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r requirements.txt

COPY alerts.py api.py baseline.py collector.py digest.py main.py speedtest_runner.py storage.py ./
COPY static/ ./static/
RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PINGPLOTTER_PORT', '8000') + '/', timeout=3).close()"

CMD ["python", "main.py"]
