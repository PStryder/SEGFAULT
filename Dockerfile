FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY segfault /app/segfault

RUN pip install --no-cache-dir .

EXPOSE 8080

ENV SEGFAULT_DB_PATH=/data/segfault.db

CMD ["uvicorn", "segfault.api.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
