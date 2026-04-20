FROM python:3.13-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Node.js 18.x
RUN apt-get update && \
    apt-get install -y curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN python --version && uv --version && node -v && npm -v

WORKDIR /code

RUN apt-get update && apt-get install -y build-essential \
    libpq-dev \
    git \
    postfix \
    libmagic1 \
    libmagic-dev \
    postgresql \
    postgresql-contrib \
    nginx \
    wkhtmltopdf \
    libxmlsec1-openssl \
    libxml2-dev \
    libxmlsec1-dev \
    libcairo2-dev \
    pkg-config \
    netcat-openbsd \
    gettext \
 && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .

# Install dependencies with uv
RUN uv pip install --system -r pyproject.toml

EXPOSE 8264
