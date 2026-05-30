# Dashboard Container Restart / Rebuild Guide

## 🔄 When to Rebuild

You need to **rebuild** the dashboard container when:
- ✅ You edit `static/index.html` (adding/removing services)
- ✅ You edit `app.py` (changing backend logic)
- ✅ You edit `requirements.txt` (adding Python dependencies)
- ✅ You edit the `Dockerfile`

You do **NOT** need to rebuild when:
- ❌ Just viewing the dashboard
- ❌ Using the restart/recreate buttons in the UI

---

## 📝 Quick Reference Commands

### Check if dashboard is running:
```bash
docker ps | grep dashboard
```

### View dashboard logs:
```bash
docker logs dashboard --tail 50
```

### Rebuild and redeploy:
```bash
cd /home/brandon/projects/Dashboard
docker compose up -d --build
```

### Restart without rebuild (e.g. config change):
```bash
cd /home/brandon/projects/Dashboard
docker compose restart dashboard
```

---

## 🎯 Adding New Services to Dashboard

When adding a new service card to the dashboard:

1. **Edit** `static/index.html`
2. **Find** the appropriate category section (Media, Downloads, Tools, etc.)
3. **Copy** an existing service card and modify it
4. **Rebuild** the container using `docker compose up -d --build`
5. **Hard refresh** your browser (Ctrl+F5 or Cmd+Shift+R)

### Example Service Card Template:
```html
<div class="service-card">
    <a href="http://100.69.184.113:PORT" class="service-link" target="_blank">
        <div class="service-header">
            <i class="service-icon fas fa-ICON"></i>
            <span class="service-name">SERVICE_NAME</span>
        </div>
        <div class="service-description">Description here</div>
    </a>
    <div class="service-footer">
        <div class="service-url">:PORT</div>
    </div>
    <div class="service-actions">
        <button class="action-btn restart-btn" onclick="restartContainer('container_name')">
            <i class="fas fa-redo"></i> Restart
        </button>
        <button class="action-btn recreate-btn" onclick="recreateContainer('container_name')">
            <i class="fas fa-hammer"></i> Recreate
        </button>
    </div>
</div>
```

---

## 📅 Last Updated
2026-04-05 - Simplified after Docker install was cleaned up; standard compose commands work normally now.

