# Dashboard Container Restart Troubleshooting

## ⚠️ Known Issue: Permission Denied on Restart

The dashboard container sometimes gets into a state where it **cannot be restarted** using normal Docker commands.

### Symptoms:
```bash
$ docker compose restart
Error response from daemon: Cannot restart container: permission denied

$ sudo docker compose restart
Error response from daemon: Cannot restart container: permission denied

$ sudo docker compose down
Error response from daemon: cannot stop container: permission denied
```

---

## ✅ Solution: Kill Process + Rebuild

When you need to apply changes to the dashboard (like updating `static/index.html`), follow these steps:

### Step 1: Find the Container PID
```bash
sudo docker inspect e6dace6a7508_dashboard | grep -A 5 "Pid"
# Or check the current container name first:
docker ps | grep dashboard
```

### Step 2: Kill the Process Directly
```bash
# Replace 6020 with the actual PID from step 1
sudo kill -9 6020
```

### Step 3: Rebuild and Start
```bash
cd /home/brandon/projects/Dashboard
sudo docker compose up -d --build --force-recreate
```

**Alternative (if you know the PID):**
```bash
sudo kill -9 <PID> && sleep 2 && sudo docker compose up -d
```

---

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
# Use the actual container name from docker ps
docker logs e6dace6a7508_dashboard --tail 50
```

### Find the process PID:
```bash
sudo docker inspect <container_name> | grep '"Pid"'
```

### Nuclear option (kill + rebuild):
```bash
# Find PID first
PID=$(sudo docker inspect e6dace6a7508_dashboard | grep '"Pid"' | head -1 | grep -o '[0-9]*')
# Kill and rebuild
sudo kill -9 $PID && sleep 2 && sudo docker compose up -d --build --force-recreate
```

---

## 🎯 Adding New Services to Dashboard

When adding a new service card to the dashboard:

1. **Edit** `static/index.html`
2. **Find** the appropriate category section (Media, Downloads, Tools, etc.)
3. **Copy** an existing service card and modify it
4. **Rebuild** the container using the steps above
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

## 🐛 Why Does This Happen?

The dashboard container mounts `/var/run/docker.sock` to control other containers. This sometimes causes permission issues with the Docker daemon when trying to stop/restart the container itself.

The `pkill` method we tried before doesn't always work because the Python process inside the container is isolated. Killing the container's main PID directly is the most reliable method.

---

## 📅 Last Updated
2026-01-29 - Added after successfully adding Deemix service to dashboard

