FROM python:3.11-slim

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
