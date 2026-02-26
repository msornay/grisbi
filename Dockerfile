FROM python:3-slim

ARG AGE_VERSION=1.3.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSfL "https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-linux-amd64.tar.gz" \
       | tar xz --strip-components=1 -C /usr/local/bin age/age age/age-keygen age/age-plugin-batchpass \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ruff

WORKDIR /app
