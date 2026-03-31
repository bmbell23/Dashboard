# Tailscale Access Consolidation Plan

Date: 2026-03-31
Scope: All Docker services managed from Dashboard

## Goal

Make services reachable from restrictive networks that block direct 100.x IP and non-standard ports.

Target access model:
- Primary access over HTTPS on port 443 only
- Single tailnet hostname entry point
- Container-by-container routing policy with explicit exposure decisions

Current working hostname:
- https://dockerhost.tailb8b575.ts.net

## Why Current Access Fails On Work VPN

- Many corporate networks block destination ports other than 443 and 80
- Some corporate networks also block direct traffic to 100.64.0.0/10 ranges
- Direct links like http://100.69.184.113:8001 fail even when Tailscale itself is installed

## Recommended Architecture

Use one TLS entrypoint at 443 and route internally by path prefix.

Pattern:
- Client -> https://dockerhost.tailb8b575.ts.net/<service>
- Tailscale HTTPS termination -> reverse proxy router -> container on localhost:port

Notes:
- This avoids exposing many external ports
- This keeps access compatible with restrictive networks
- Some apps do not behave well under subpaths; those are identified below

## Container Routing Matrix

Legend:
- Exposure: External means reachable through the tunnel. Internal means no direct external route.
- Route type: Path means /service. Root means / on a dedicated entrypoint.
- Phase: Rollout order.

| Container | Current Port | Exposure | Route Type | Proposed External Route | Path Compatibility | Phase | Notes |
|---|---:|---|---|---|---|---|---|
| dashboard | 8001 | External | Path | /dashboard | Good | 1 | Keep dashboard available even during migration.
| vaultwarden | 8222 | External | Root | / (existing) or /vault | Prefer root | 1 | Already working on ts.net over 443.
| booknews | 8010 | External | Path | /news | Good | 2 | Basic web app.
| greatreads_app | 8007 | External | Path | /greatreads | Good | 2 | Basic web app.
| audiobookshelf | 13378 | External | Path | /audiobookshelf | Usually good | 2 | Verify websocket endpoints after cutover.
| calibre | 8084 | External | Path | /calibre | Mixed | 3 | UI may need base URL handling.
| libby-web | 5007 | External | Path | /libby | Good | 2 | Basic web app.
| lifeforge_app | 8004 | External | Path | /lifeforge | Good | 2 | Basic web app.
| artforge | 8003 | External | Path | /artforge | Good | 2 | Basic web app.
| wordforge | 8002 | External | Path | /wordforge | Good | 2 | Basic web app.
| codeforge_app | 8005 | External | Path | /codeforge | Mixed | 3 | IDE-style apps often need websocket and prefix checks.
| kidmedia | 8006 | External | Path | /kidmedia | Good | 2 | Basic web app.
| immich | 2283 | External | Path | /immich | Mixed | 3 | May require app base URL settings.
| jellyfin | 8096 | External | Path | /jellyfin | Mixed | 3 | Usually needs base URL set to /jellyfin.
| romm | 8080 | External | Path | /romm | Mixed | 3 | Confirm static asset paths.
| qbittorrent | 2285 | External | Path | /qbittorrent | Mixed | 4 | Usually needs reverse proxy and host header settings.
| jackett | 9117 | External | Path | /jackett | Usually good | 4 | Confirm API links in UI.
| yt-dlp-web | 8998 | External | Path | /ytdlp | Mixed | 4 | Verify download URL generation.
| deemix | 6595 | External | Path | /deemix | Mixed | 4 | Verify websocket and API paths.
| trilium | 8085 | External | Path | /trilium | Mixed | 3 | Check absolute URL behavior.
| stash | 9999 | External | Path | /stash | Mixed | 3 | Confirm media route handling.
| dictionary-api | 8098 | External | Path | /dictionary | Good | 2 | API + simple UI.
| fileshare-miniserve | dynamic | External | Root/Path | Keep current quick-share URL | N/A | Existing | Keep as separate flow; short-lived by design.
| fileshare-cloudflared | dynamic | External | Root/Path | Keep current quick-share URL | N/A | Existing | Not part of persistent dashboard routing.
| immich-db | internal | Internal | None | Not exposed | N/A | Never | Database only.
| romm-db | internal | Internal | None | Not exposed | N/A | Never | Database only.
| flaresolverr | internal | Internal | None | Not exposed | N/A | Never | Downloader dependency only.
| mullvad-vpn | internal | Internal | None | Not exposed | N/A | Never | Network utility only.

## Rollout Phases

## Phase 1: Foundation And Safe Cutover

1. Keep current Vaultwarden tunnel route active.
2. Add stable routed endpoint for Dashboard at /dashboard.
3. Confirm /alive and /dashboard health checks over ts.net.
4. Update Dashboard links for Vaultwarden and Dashboard to ts.net routes first.

Success criteria:
- Vaultwarden and Dashboard reachable from work VPN using HTTPS 443 only.

## Phase 2: Low-Risk App Migration

Migrate apps with expected good subpath behavior:
- /news
- /greatreads
- /audiobookshelf
- /libby
- /lifeforge
- /artforge
- /wordforge
- /kidmedia
- /dictionary

For each app:
1. Add route.
2. Validate login/session.
3. Validate static assets and API calls.
4. Replace Dashboard link from 100.69.184.113:port to ts.net path.

## Phase 3: Medium-Risk Apps (May Need Base URL)

Apps:
- /calibre
- /codeforge
- /immich
- /jellyfin
- /romm
- /trilium
- /stash

Validation focus:
- Websocket support
- Absolute URL generation
- Redirect targets and callback URLs
- Mobile client behavior

Fallback if subpath fails:
- Keep direct Tailscale LAN access for trusted networks
- Or move app to dedicated 443 endpoint strategy (separate hostname/device identity)

## Phase 4: Download Stack

Apps:
- /qbittorrent
- /jackett
- /ytdlp
- /deemix

Validation focus:
- CSRF and origin checks
- API endpoints used by companion tools
- Download URL generation and callback links

## Phase 5: Hardening And Cleanup

1. Remove public reliance on direct 100.x:port links in Dashboard UI.
2. Keep internal-only containers internal.
3. Add an automated route health check job for all external paths.
4. Document rollback for each migrated service.

## Security Policy Per Container Type

- Password and identity systems (Vaultwarden): strict HTTPS only, no direct-port links in UI.
- Personal media/productivity apps: routed through ts.net path, protected by app auth.
- Download and network utility components: expose only when needed; prefer internal-only.
- Databases and sidecars: never externally routed.

## Dashboard Update Policy

As each service is migrated:
1. Replace card URL from 100.69.184.113:port to https://dockerhost.tailb8b575.ts.net/<service>.
2. Keep restart/recreate actions unchanged.
3. Add a small route status check in infra page if desired.

## Risks And Mitigations

- Risk: App does not support subpath.
  - Mitigation: Set app base URL where available; if not possible, use dedicated endpoint strategy.

- Risk: Websocket breakage behind proxy.
  - Mitigation: Explicit websocket proxy headers and keep-alive tuning.

- Risk: Mixed HTTP/HTTPS redirects.
  - Mitigation: Force HTTPS scheme at proxy and app-level external URL settings.

- Risk: Session/cookie scope issues.
  - Mitigation: Verify cookie path/domain after migration and test login persistence.

## Test Checklist (Per Service)

1. Page loads over ts.net route on work VPN.
2. Login works and persists after refresh.
3. Static assets load with no 404s.
4. Core workflows run (streaming, search, downloads, scans).
5. Direct 100.x:port link no longer needed for normal use.

## Definition Of Done

- Every intended external service has a working HTTPS 443 ts.net route.
- Dashboard links point to ts.net routes for migrated services.
- Internal-only containers remain unexposed.
- Work VPN access succeeds for normal workflows without raw 100.x:port URLs.