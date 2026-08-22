FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY packages/prompt-engine /app/packages/prompt-engine
COPY apps/api /app/apps/api
RUN pip install --no-cache-dir /app/packages/prompt-engine /app/apps/api

WORKDIR /app/apps/api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
