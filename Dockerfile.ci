FROM mcr.microsoft.com/playwright/python:v1.42.0

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

ENV TZ=Europe/Rome

# update node
RUN curl -fsSL https://deb.nodesource.com/setup_current.x | bash -

RUN apt-get update && apt-get install -y \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    python3-dev \
    gcc \
    libmagic1 \
    libgtk-4-1 \
    libavif13 \
    gstreamer1.0-plugins-bad \
    gettext \
    curl gnupg \
    nodejs \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*


# install pip requirements
COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

ENV PYTEST_CURRENT_TEST="true"

CMD pytest
