# Docker Cache Management - Quick Reference

## 🎯 TL;DR - The Short Answer

Docker cache invalidation happens **automatically** when:
1. ✅ **Code changes** → Git commit hash changes → Forces rebuild
2. ✅ **Dependencies change** → `requirements.txt` changes → CI/CD rebuilds
3. ✅ **Build timestamp** → Every build gets new `BUILD_TIME` arg
4. ✅ **CI/CD pipeline** → GitHub Actions rebuilds on push to main

---

## 🚀 Quick Start (Choose Your Method)

### **Option 1: Automated (RECOMMENDED)**
```bash
# Uses git commit hash + build date to invalidate cache automatically
# No extra steps needed - just commit and push!
git commit -m "Your changes"
git push origin main
# GitHub Actions automatically rebuilds with fresh cache
```

### **Option 2: Manual Local Build**

**Windows (PowerShell):**
```powershell
# With cache (faster)
.\build-docker.ps1

# Without cache (fresh rebuild)
.\build-docker.ps1 -NoCache
```

**Linux/macOS (Bash):**
```bash
# With cache (faster)
./build-docker.sh

# Without cache (fresh rebuild)
./build-docker.sh true
```

### **Option 3: Direct Docker Command**
```bash
# Don't use cache (slowest but guaranteed fresh)
docker build --no-cache -t real-estate-env .

# Remove old images before/after
docker rmi real-estate-env:latest
docker image prune -f
```

---

## 📋 What Triggers Cache Invalidation?

| Trigger | Action | Result |
|---------|--------|--------|
| **Git commit hash changes** | Passed as `--build-arg VCS_REF` | ✅ Rebuilds |
| **Build timestamp changes** | Every build gets `BUILD_DATE` arg | ✅ Rebuilds |
| **requirements.txt modified** | CI/CD detects change | ✅ Full rebuild (no cache) |
| **Dockerfile modified** | Docker sees new content | ✅ Rebuilds from that layer |
| **App code changes** | COPY . . layer runs | ✅ Only that layer rebuilds |
| **Explicit --no-cache flag** | Disables all caching | ✅ Fresh rebuild |

---

## 🔍 How It Works

### **Before Push (Local Development)**

1. **Make code changes**
   ```bash
   # Edit files...
   git add .
   git commit -m "My changes"
   ```

2. **Optional: Test locally**
   ```powershell
   # Uses cache if nothing changed
   .\build-docker.ps1
   
   # Force fresh rebuild
   .\build-docker.ps1 -NoCache
   ```

3. **Push to GitHub**
   ```bash
   git push origin main
   ```

### **During Push (GitHub Actions)**

1. **Workflow triggered** → Commit pushed to main branch
2. **Build metadata extracted** → Git hash, build date, version
3. **Cache decision made** → Check if requirements.txt changed
   - ✅ If unchanged → Use cache (faster)
   - ✅ If changed → No cache (fresh install)
4. **Docker image built** → With git hash + timestamp as build args
5. **Tests run** → Verify graders work
6. **Image pushed** → Tagged with hash, version, "latest"

---

## 🧹 Force Cache Clear

If something seems stale, force a complete refresh:

```bash
# Nuclear option: removes everything
docker system prune -a --volumes

# Or just Docker images
docker image prune -af

# Remove one specific image
docker rmi real-estate-env:latest

# Rebuild
docker build -t real-estate-env .
```

---

## 📊 Check Image Details

```bash
# See all real-estate-env images
docker images real-estate-env

# See image layers and what they contain
docker history real-estate-env:latest

# See full image metadata
docker inspect real-estate-env:latest

# Check disk usage
docker system df
```

---

## 🔧 Advanced: Setup Git Hook (Optional)

Automatically clean cache before pushing:

```bash
# On Windows PowerShell, copy this:
Copy-Item pre-push-hook.bat -Destination .git/hooks/pre-push

# On Linux/macOS, create .git/hooks/pre-push with content from build-docker.sh

# Make sure to make it executable (Linux/macOS)
chmod +x .git/hooks/pre-push
```

---

## ⚡ Performance Tips

| Action | Time | Benefit |
|--------|------|---------|
| Build with cache | ~10s | Fast, uses existing layers |
| Build without cache | ~2-3m | Guaranteed fresh, installs all deps |
| First build ever | ~3-5m | All layers built from scratch |
| Change app code only | ~15s | Only COPY . . layer rebuilds |
| Change requirements.txt | ~1-2m | pip reinstalls everything |

---

## 🚨 Troubleshooting

**Problem: Image has old code**
```bash
# Solution: Force rebuild
docker build --no-cache -t real-estate-env . && docker run real-estate-env python comprehensive_grader_test.py
```

**Problem: Old image still exists**
```bash
# Solution: Remove it
docker rmi real-estate-env:old-hash
docker image prune -f
```

**Problem: Cache seems stuck**
```bash
# Solution: Complete cleanup
docker system prune -a
docker image prune -af
```

**Problem: Graders report 0.0 score (stale code)**
```bash
# Solution: Rebuild without cache
docker build --no-cache -t real-estate-env .
docker run real-estate-env python comprehensive_grader_test.py
```

---

## 📚 Additional Resources

- **Full guide:** See `DOCKER_CACHE_STRATEGY.md`
- **Build scripts:** Use `build-docker.ps1` (Windows) or `build-docker.sh` (Linux)
- **CI/CD config:** See `.github/workflows/docker-build.yml`
- **Learn more:** https://docs.docker.com/develop/dev-best-practices/dockerfile-best-practices/

---

## ✅ Verification Checklist

```bash
# Everything working?
✓ Code committed
✓ Code pushed to main
✓ GitHub Actions workflow running
✓ Docker image built with git hash  
✓ Tests pass
✓ Image tagged with version
✓ Old images cleaned up

# Image ready for deployment?
✓ docker images | grep real-estate-env
✓ docker run real-estate-env python comprehensive_grader_test.py
✓ docker inspect real-estate-env:latest
```
