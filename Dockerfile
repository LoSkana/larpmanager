FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.12
RUN apt-get update && \
    apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    curl \
    ca-certificates \
    gnupg && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# Install Node.js 18.x
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN python --version && uv --version && node -v && npm -v

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
COPY requirements.txt .

EXPOSE 8264
