# Docker Cache Invalidation Strategy

This document explains how to ensure Docker cache is properly cleared or rebuilt when code changes are pushed.

---

## ⚠️ Problem
Docker's layer caching means that when you make code changes and rebuild, Docker will reuse cached layers if the Dockerfile instruction hasn't changed. This can lead to:
- Old code being packaged in the image
- Stale dependencies
- Outdated application state

---

## ✅ Solution: Multi-Strategy Approach

### **Strategy 1: Git-Based Cache Invalidation (RECOMMENDED)**

Add a build argument that changes with every commit, forcing a rebuild:

```bash
# Tag with commit hash to force cache invalidation
git_hash=$(git rev-parse --short HEAD)
docker build \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  --build-arg VCS_REF=$git_hash \
  -t real-estate-env:$git_hash \
  -t real-estate-env:latest \
  .
```

**Updated Dockerfile:**
```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=0.1.0

LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.version=$VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# This ARG placement forces rebuild on every new VCS_REF
ARG VCS_REF
RUN echo "Building from commit: $VCS_REF"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
```

---

### **Strategy 2: Manual Cache Clearing**

**Before pushing, clear old images locally:**
```bash
# Remove old images (before pushing)
docker rmi real-estate-env:latest

# Remove dangling images (orphaned layers)
docker image prune -f

# Remove ALL images and rebuild fresh
docker system prune -a --volumes  # ⚠️ Warning: Very aggressive
```

**Build command that ignores cache:**
```bash
docker build --no-cache -t real-estate-env .
```

---

### **Strategy 3: Automated CI/CD Pipeline (GitHub Actions)**

Create `.github/workflows/docker-build.yml`:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
    paths:
      - 'requirements.txt'
      - 'Dockerfile'
      - 'app.py'
      - 'server/**'
      - 'real_estate_pipeline/**'

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Get commit info
        id: commit
        run: |
          echo "sha=$(git rev-parse --short HEAD)" >> $GITHUB_OUTPUT
          echo "date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" >> $GITHUB_OUTPUT
      
      - name: Build Docker image (No cache)
        run: |
          docker build \
            --no-cache \
            --build-arg BUILD_DATE=${{ steps.commit.outputs.date }} \
            --build-arg VCS_REF=${{ steps.commit.outputs.sha }} \
            -t real-estate-env:${{ steps.commit.outputs.sha }} \
            -t real-estate-env:latest \
            .
      
      - name: Verify image
        run: |
          docker run real-estate-env:latest python comprehensive_grader_test.py
      
      - name: Clean up old images
        run: docker image prune -af
```

---

### **Strategy 4: Git Hooks (Local Development)**

Create `.git/hooks/pre-push` to clean cache before pushing:

```bash
#!/bin/bash
# .git/hooks/pre-push - Clear Docker cache before pushing

echo "🧹 Cleaning Docker cache before push..."

# Remove old images
docker rmi real-estate-env:latest 2>/dev/null || true

# Prune dangling images
docker image prune -f 2>/dev/null || true

echo "✅ Docker cache cleared. Proceeding with push..."
exit 0
```

**Make it executable:**
```bash
chmod +x .git/hooks/pre-push
```

---

### **Strategy 5: Timestamp-Based Invalidation**

Add a timestamp that forces cache miss on every build:

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Get current timestamp (changes every 5 minutes)
ARG BUILD_TIME=$(date +%s)
RUN echo "Build time: $BUILD_TIME" && \
    echo "This layer is invalidated every build cycle"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
```

**Build command:**
```bash
docker build --build-arg BUILD_TIME=$(date +%s) -t real-estate-env .
```

---

### **Strategy 6: Docker Compose Cleanup**

If using Docker Compose, add cleanup commands:

```yaml
# docker-compose.yml
version: '3.8'

services:
  real-estate-env:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        BUILD_TIME: ${BUILD_TIMESTAMP}
    image: real-estate-env:latest
    ports:
      - "7860:7860"
    environment:
      - PYTHONDONTWRITEBYTECODE=1
      - PYTHONUNBUFFERED=1
```

**Build script:**
```bash
#!/bin/bash
# build.sh

# Clear old images
docker-compose down
docker system prune -f

# Build with fresh cache
BUILD_TIMESTAMP=$(date +%s) docker-compose build --no-cache
docker-compose up
```

---

## 📋 Recommended Setup

### **For Local Development:**

1. Use **Strategy 1 (Git-based cache invalidation)**
2. Use **Strategy 4 (Pre-push git hook)** for safety

```bash
# Make it easy to rebuild fresh
alias docker-rebuild='docker build --no-cache -t real-estate-env . && docker run real-estate-env python comprehensive_grader_test.py'
```

### **For CI/CD (GitHub):**

1. Use **Strategy 3 (GitHub Actions workflow)**
2. Automatically builds on code changes
3. Runs tests before tagging as "latest"

### **For Production:**

1. Use **Strategy 1 + Strategy 3**
2. Tag images with git commit hash
3. Use semantic versioning (v1.0.0)
4. Keep image registry clean with garbage collection

---

## 🚀 Quick Commands

```bash
# Clear cache and rebuild (nuclear option)
docker build --no-cache -t real-estate-env .

# Remove old images only
docker rmi real-estate-env:latest

# Remove dangling layers
docker image prune -f

# Full system cleanup
docker system prune -a --volumes

# Build with git info
git_hash=$(git rev-parse --short HEAD)
docker build --build-arg VCS_REF=$git_hash -t real-estate-env:$git_hash .

# Verify new image works
docker run real-estate-env python comprehensive_grader_test.py
```

---

## ✨ Best Practices Summary

| Scenario | Action |
|----------|--------|
| **Local testing** | Use `--no-cache` flag |
| **Before pushing** | Run pre-push git hook |
| **CI/CD pipeline** | Use Build Date + VCS_REF args |
| **Suspect stale image** | `docker system prune -a` |
| **Production** | Tag with commit hash + semantic version |
| **Weekly cleanup** | Schedule `docker image prune` |

---

## Monitoring Cache Usage

```bash
# See how much space Docker is using
docker system df

# See all images (including dangling)
docker images -a

# See all layers
docker history real-estate-env:latest
```
