FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN curl -fsSL https://deb.nodesource.com/setup_current.x | bash -

WORKDIR /code

RUN apt-get update && apt-get install -y build-essential \
    libpq-dev \
    python3-pip \
    git \
    postfix \
    libmagic1 \
    libmagic-dev \
    postgresql \
    postgresql-contrib \
    nginx \
    libpq-dev \
    wkhtmltopdf \
    nodejs \
    libxmlsec1-openssl \
    libxml2-dev \
    libxmlsec1-dev \
    pkg-config \
    netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy prod example to prod settings
RUN cp main/settings/prod_example.py main/settings/prod.py

EXPOSE 8264
