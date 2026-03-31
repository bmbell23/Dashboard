# Dashboard

Canonical repository for the server dashboard running at http://100.69.184.113:8001/.

This service provides:
- Dashboard UI and links for self-hosted services
- Container restart/recreate controls
- Health and infrastructure telemetry APIs
- Library scan actions for Jellyfin and Audiobookshelf

Planning docs:
- See TAILSCALE_ACCESS_PLAN.md for the container-by-container HTTPS 443 access migration plan.

## Repository Location

Canonical path on host:
- `/home/brandon/projects/Dashboard`

Legacy location (do not use for edits/deployments):
- `/home/brandon/projects/docker/dashboard`

## Local Development

1. Create env file:
```bash
cp .env.example .env
```

2. Build image:
```bash
docker compose -f compose.yml build dashboard
```

3. Start container:
```bash
docker compose -f compose.yml up -d
```

4. Check health:
```bash
curl -s http://100.69.184.113:8001/api/health
```

## Deployment

Use this repository as the single source of truth.

```bash
cd /home/brandon/projects/Dashboard
docker compose -f compose.yml up -d --build --force-recreate dashboard
```

## Versioning And Releases (gvc)

This repo is configured for the `gvc()` function from `~/projects/dotfiles/bashrc/conf.d/20-functions.sh`.

Prerequisites:
- Ensure your shell has loaded your dotfiles functions (so `gvc` is available).
- Ensure `origin` points to this repository on GitHub.

Release flow:
```bash
cd /home/brandon/projects/Dashboard
gvc "your commit message"
```

What this does:
- Reads `version.txt`
- Increments patch version automatically (X.Y.Z -> X.Y.Z+1)
- Commits with `v<version>: <message>`
- Creates annotated git tag `v<version>`
- Pushes commit and tags to `origin`

Manual version override:
```bash
gvc 1.2.0 "release message"
```

## Notes

- `compose.yml` uses `network_mode: host`, so `app.py` binds directly on port `8001`.
- The self-recreate endpoint mounts this repository path inside a short-lived sibling container; keep this path current if moved again.
- Keep secrets only in `.env` (ignored by git).
