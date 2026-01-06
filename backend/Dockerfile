ARG REGISTRY_MIRROR=docker.m.daocloud.io
FROM ${REGISTRY_MIRROR}/library/python:3.10-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (psycopg2, sentence-transformers, etc.)
ARG APT_MIRROR_BASE=https://mirrors.tuna.tsinghua.edu.cn
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|http://deb.debian.org/debian|${APT_MIRROR_BASE}/debian|g" /etc/apt/sources.list.d/debian.sources && \
      sed -i "s|http://security.debian.org/debian-security|${APT_MIRROR_BASE}/debian-security|g" /etc/apt/sources.list.d/debian.sources ; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i "s|http://deb.debian.org/debian|${APT_MIRROR_BASE}/debian|g; s|http://security.debian.org/debian-security|${APT_MIRROR_BASE}/debian-security|g" /etc/apt/sources.list ; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_TIMEOUT=1200
RUN extra_args=""; \
    if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then extra_args="--extra-index-url ${PIP_EXTRA_INDEX_URL}"; fi; \
    pip install --no-cache-dir --retries 12 --timeout ${PIP_TIMEOUT} \
      -i ${PIP_INDEX_URL} ${extra_args} \
      -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
