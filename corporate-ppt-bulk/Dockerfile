# Pinned to bookworm explicitly — plain "python:3.11-slim" currently
# resolves to Debian trixie, which Playwright doesn't officially support
# yet; its --with-deps step falls back to guessing Ubuntu 20.04 package
# names (ttf-ubuntu-font-family, ttf-unifont) that don't exist in trixie's
# repos (renamed to fonts-unifont etc.), so apt fails outright. bookworm
# is an officially supported OS for Playwright.
FROM python:3.11-slim-bookworm

# poppler-utils -> pdftotext (document parsing)
# Playwright's chromium needs a handful of system libs even in --with-deps mode on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY app ./app
RUN mkdir -p /srv/data

ENV DATA_DIR=/srv/data
ENV PYTHONPATH=/srv/app
EXPOSE 8000

CMD ["uvicorn", "main:app", "--app-dir", "app", "--host", "0.0.0.0", "--port", "8000"]
