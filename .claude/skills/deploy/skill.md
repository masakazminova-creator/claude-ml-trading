---
name: deploy
description: Deploy Claude ML Trading System to production server with GitHub Actions
---

# Deploy Skill

Deploy the Claude ML Trading System to production.

## When to use
- User asks to deploy, push to production, update server
- After making code changes that need to go live
- To check deployment status or restart services

## How it works

1. **Commit and push** local changes to GitHub
2. **GitHub Actions** automatically builds and deploys
3. **Wait for deployment** (~2-3 minutes for build + restart)
4. **Verify** services are healthy on server

## Commands

```bash
# Full deploy (commit + push + wait)
cd "C:\Bot\claude_ml_system" && git add . && git commit -m "fix: description" && git push origin main

# Check deployment status
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose ps"

# View recent logs
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker-compose logs --tail=50"
```

## Post-deploy verification

After deployment completes (~3 min), verify:
```bash
# Check container health
ssh root@95.81.101.148 "docker exec claude-ml-bot python -c 'print(\"OK\")'"

# Test monitoring script
ssh root@95.81.101.148 "cd /opt/claude-ml-trading && docker exec claude-ml-bot python scripts/monitor_decisions.py --hours 1"
```

## Rollback procedure

If deployment fails:
```bash
# Revert to previous commit
cd "C:\Bot\claude_ml_system" && git revert HEAD && git push
```

## Notes
- Auto-deploy is triggered by GitHub Actions on push to main
- Server pulls latest code and rebuilds Docker image
- No manual intervention needed unless build fails
- Deployment takes ~2-3 minutes (build + restart)
