#!/usr/bin/env bash
# build-docker.sh - Smart Docker build with automatic cache invalidation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Real Estate Pipeline Docker Build Script${NC}\n"

# Parse arguments
NO_CACHE=${1:-false}
PUSH=${2:-false}

# Get git information
GIT_HASH=$(git rev-parse --short HEAD)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VERSION=$(grep "version" pyproject.toml | head -1 | cut -d'"' -f2)

echo -e "${YELLOW}Build Information:${NC}"
echo "  Git Hash: $GIT_HASH"
echo "  Git Branch: $GIT_BRANCH"
echo "  Build Date: $BUILD_DATE"
echo "  Version: $VERSION"
echo ""

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}⚠️  WARNING: You have uncommitted changes!${NC}"
    echo "    These changes will NOT be included in the Docker image."
    echo "    Stage and commit changes before building."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Build cancelled."
        exit 1
    fi
fi

# Determine cache flags
if [[ "$NO_CACHE" == "true" ]]; then
    CACHE_FLAG="--no-cache"
    echo -e "${YELLOW}🗑️  Cache Mode: DISABLED (fresh build)${NC}"
else
    CACHE_FLAG=""
    echo -e "${YELLOW}⚡ Cache Mode: ENABLED (faster builds)${NC}"
fi
echo ""

# Clean up old dangling images before build
echo -e "${YELLOW}🧹 Cleaning up old dangling images...${NC}"
docker image prune -f --filter "until=24h" 2>/dev/null || true
echo -e "${GREEN}✓ Cleanup complete${NC}\n"

# Build the image
echo -e "${YELLOW}📦 Building Docker image...${NC}"
docker build \
    $CACHE_FLAG \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg VCS_REF="$GIT_HASH" \
    --build-arg VERSION="$VERSION" \
    -t real-estate-env:latest \
    -t real-estate-env:$GIT_HASH \
    -t real-estate-env:v$VERSION \
    -f Dockerfile \
    . || {
        echo -e "${RED}❌ Build failed!${NC}"
        exit 1
    }

echo -e "${GREEN}✓ Build successful${NC}\n"

# Run verification tests
echo -e "${YELLOW}🧪 Running verification tests...${NC}"
if docker run --rm real-estate-env:latest python comprehensive_grader_test.py > /tmp/grader_test.log 2>&1; then
    echo -e "${GREEN}✓ Grader tests passed${NC}"
else
    echo -e "${RED}❌ Grader tests failed!${NC}"
    cat /tmp/grader_test.log
    exit 1
fi

# Quick container test
echo -e "${YELLOW}💨 Running quick container sanity check...${NC}"
if docker run --rm real-estate-env:latest python -c "from server.graders import EasyGrader; print('✓ Imports OK')"; then
    echo -e "${GREEN}✓ Container sanity check passed${NC}"
else
    echo -e "${RED}❌ Container sanity check failed!${NC}"
    exit 1
fi

echo ""

# Display image info
echo -e "${YELLOW}📊 Image Information:${NC}"
docker images --filter "reference=real-estate-env" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.Created}}"

echo ""
echo -e "${GREEN}✅ Build Complete!${NC}"
echo ""

# Show next steps
echo -e "${BLUE}Next steps:${NC}"
echo "  Test locally:"
echo "    docker run -p 7860:7860 real-estate-env:latest"
echo ""
echo "  Push tags:"
echo "    docker push subho-bm18/real-estate-env:$GIT_HASH"
echo "    docker push subho-bm18/real-estate-env:v$VERSION"
echo "    docker push subho-bm18/real-estate-env:latest"
echo ""
echo "  View image details:"
echo "    docker history real-estate-env:latest"
echo "    docker inspect real-estate-env:latest"
