FROM node:18

RUN apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3-pip

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

RUN python --version && pip --version && node -v && npm -v

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
    libxmlsec1-openssl \
    libxml2-dev \
    libxmlsec1-dev \
    pkg-config \
    netcat-openbsd \
    gettext \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install --no-cache-dir  -r requirements.txt

COPY . .

# Copy prod example to prod settings
RUN cp main/settings/prod_example.py main/settings/prod.py

EXPOSE 8264
