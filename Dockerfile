FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[browser,docs,yaml]" \
    && python -m playwright install --with-deps chromium

RUN mkdir -p /app/data /app/work/reports /app/work/source_audit /app/work/download_audit /app/work/extracted_text

EXPOSE 8765

CMD ["python", "-m", "tender_radar.ui_server", "--host", "0.0.0.0", "--port", "8765"]
