# --- Base stage: Python + uv + dependencies ---
FROM python:3.12-slim AS base
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


# --- Watcher stage: add Chromium for Selenium ---
FROM base AS watcher

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

COPY uscis_watcher.py summary.py db.py ./

CMD ["uv", "run", "uscis_watcher.py", "--daemon", "--headless"]


# --- Web stage: Flask only, no browser needed ---
FROM base AS web

COPY web.py db.py summary.py ./
COPY templates/ templates/

EXPOSE 8080
CMD ["uv", "run", "python", "web.py"]
