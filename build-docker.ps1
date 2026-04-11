# build-docker.ps1 - Smart Docker build with automatic cache invalidation (PowerShell)

param(
    [switch]$NoCache = $false,
    [switch]$Push = $false,
    [switch]$Verbose = $false
)

# Colors
$Blue = "`e[0;34m"
$Green = "`e[0;32m"
$Yellow = "`e[1;33m"
$Red = "`e[0;31m"
$Reset = "`e[0m"

Write-Host "${Blue}🐳 Real Estate Pipeline Docker Build Script${Reset}`n"

# Get git information
$GitHash = (git rev-parse --short HEAD 2>$null) -replace '\n', ''
$GitBranch = (git rev-parse --abbrev-ref HEAD 2>$null) -replace '\n', ''
$BuildDate = (Get-Date -u -Format 'yyyy-MM-ddTHH:mm:ssZ')
$Version = ((Select-String -Path "pyproject.toml" -Pattern 'version = "(.*?)"' | ForEach-Object { $_.Matches.Groups[1].Value }) | Select-Object -First 1)

Write-Host "${Yellow}Build Information:${Reset}"
Write-Host "  Git Hash: $GitHash"
Write-Host "  Git Branch: $GitBranch"
Write-Host "  Build Date: $BuildDate"
Write-Host "  Version: $Version"
Write-Host ""

# Check for uncommitted changes
$UncommittedChanges = (git status --porcelain 2>$null | Measure-Object).Count

if ($UncommittedChanges -gt 0) {
    Write-Host "${Red}⚠️  WARNING: You have uncommitted changes!${Reset}"
    Write-Host "    These changes will NOT be included in the Docker image."
    Write-Host "    Stage and commit changes before building."
    Write-Host ""
    $Confirm = Read-Host "Continue anyway? (y/n)"
    if ($Confirm -ne 'y') {
        Write-Host "Build cancelled."
        exit 1
    }
}

# Determine cache flags
$CacheFlag = ""
if ($NoCache) {
    $CacheFlag = "--no-cache"
    Write-Host "${Yellow}🗑️  Cache Mode: DISABLED (fresh build)${Reset}"
}
else {
    Write-Host "${Yellow}⚡ Cache Mode: ENABLED (faster builds)${Reset}"
}
Write-Host ""

# Clean up old dangling images before build
Write-Host "${Yellow}🧹 Cleaning up old dangling images...${Reset}"
docker image prune -f --filter "until=24h" 2>$null
Write-Host "${Green}✓ Cleanup complete${Reset}`n"

# Build the image
Write-Host "${Yellow}📦 Building Docker image...${Reset}"
$BuildCmd = "docker build $CacheFlag " +
    "--build-arg BUILD_DATE=`"$BuildDate`" " +
    "--build-arg VCS_REF=`"$GitHash`" " +
    "--build-arg VERSION=`"$Version`" " +
    "-t real-estate-env:latest " +
    "-t real-estate-env:$GitHash " +
    "-t real-estate-env:v$Version " +
    "-f Dockerfile " +
    "."

if ($Verbose) {
    Write-Host "Build command: $BuildCmd`n"
}

Invoke-Expression $BuildCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "${Red}❌ Build failed!${Reset}"
    exit 1
}

Write-Host "${Green}✓ Build successful${Reset}`n"

# Run verification tests
Write-Host "${Yellow}🧪 Running verification tests...${Reset}"
docker run --rm real-estate-env:latest python comprehensive_grader_test.py 2>&1 | Tee-Object -Variable TestOutput
if ($LASTEXITCODE -eq 0) {
    Write-Host "${Green}✓ Grader tests passed${Reset}"
}
else {
    Write-Host "${Red}❌ Grader tests failed!${Reset}"
    Write-Host $TestOutput
    exit 1
}

# Quick container test
Write-Host "${Yellow}💨 Running quick container sanity check...${Reset}"
docker run --rm real-estate-env:latest python -c "from server.graders import EasyGrader; print('✓ Imports OK')"
if ($LASTEXITCODE -eq 0) {
    Write-Host "${Green}✓ Container sanity check passed${Reset}"
}
else {
    Write-Host "${Red}❌ Container sanity check failed!${Reset}"
    exit 1
}

Write-Host ""

# Display image info
Write-Host "${Yellow}📊 Image Information:${Reset}"
docker images --filter "reference=real-estate-env" --format "table {{.Repository}}`t{{.Tag}}`t{{.Size}}`t{{.CreatedAt}}"

Write-Host ""
Write-Host "${Green}✅ Build Complete!${Reset}"
Write-Host ""

# Show next steps
Write-Host "${Blue}Next steps:${Reset}"
Write-Host "  Test locally:"
Write-Host "    docker run -p 7860:7860 real-estate-env:latest"
Write-Host ""
Write-Host "  View image details:"
Write-Host "    docker history real-estate-env:latest"
Write-Host "    docker inspect real-estate-env:latest"
Write-Host ""
Write-Host "  Push to registry:"
Write-Host "    docker tag real-estate-env:$GitHash subho-bm18/real-estate-env:$GitHash"
Write-Host "    docker push subho-bm18/real-estate-env:$GitHash"
