# syntax=docker/dockerfile:1.6
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    GSD_BROWSER_EXECUTABLE_PATH=/usr/bin/google-chrome-stable \
    IN_DOCKER=true \
    TIMEOUT_BrowserStartEvent=60 \
    TIMEOUT_BrowserLaunchEvent=60

WORKDIR /app

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends git curl ca-certificates gnupg && \
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /app/scripts
COPY docs /app/docs
COPY config /app/config

RUN pip install --upgrade pip && pip install .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5009
ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
