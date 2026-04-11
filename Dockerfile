# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

# Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Cache layer: Copy only requirements.txt first
# This layer is cached until requirements.txt changes
COPY requirements.txt .

# Install dependencies with BuildKit cache mount for faster rebuilds
# Use: docker buildx build --with-cache -t real-estate-env .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Application code layer (rebuilds when app code changes)
COPY . .

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
