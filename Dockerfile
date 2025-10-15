# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS base

ARG DEBIAN_MIRROR=https://deb.debian.org/debian
ARG DEBIAN_SECURITY_MIRROR=https://security.debian.org/debian-security

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow

WORKDIR /app

RUN set -eux; \
    printf '%s\n' \
        'Acquire::Retries "5";' \
        'Acquire::http::Timeout "30";' \
        'Acquire::https::Timeout "30";' \
        'Acquire::ForceIPv4 "true";' \
        > /etc/apt/apt.conf.d/80-retries; \
    if [ -n "$DEBIAN_MIRROR" ] && [ -f /etc/apt/sources.list ]; then \
        sed -ri "s|https?://deb\.debian\.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list; \
    fi; \
    if [ -n "$DEBIAN_SECURITY_MIRROR" ] && [ -f /etc/apt/sources.list ]; then \
        sed -ri "s|https?://security\.debian\.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" /etc/apt/sources.list; \
    fi; \
    if [ -n "$DEBIAN_MIRROR" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -ri "s|URIs: https?://deb\.debian\.org/debian|URIs: ${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -n "$DEBIAN_SECURITY_MIRROR" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -ri "s|URIs: https?://security\.debian\.org/debian-security|URIs: ${DEBIAN_SECURITY_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        iputils-ping; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
