# IP Source Filtering — Technical Documentation

**Date:** 2026-03-23  
**Project:** CVAT Production Deployment  
**Scope:** IP-based source filtering on Web UI, API Server, and Angular Dashboard via Traefik middleware

---

## Overview

IP source filtering was implemented using Traefik v3's built-in `ipAllowList` middleware. The middleware is defined in a dedicated file-provider rules file and attached to the HTTPS routers of the three public-facing services. Traffic from IPs not in the allowlist receives a `403 Forbidden` response.

---

## Architecture

```
Internet
    │
    ▼
Traefik (port 443 — websecure)
    │
    ├── ip-allowlist middleware (sourceRange check)
    │       ├── ALLOW  → forward to service
    │       └── DENY   → 403 Forbidden
    │
    ├── Router: cvat          → cvat_server  (/api/, /static/, /admin, /django-rq)
    ├── Router: cvat-ui       → cvat_ui      (all other paths / catch-all)
    └── Router: angular-dashboard-https → angular_dashboard (/dashboard, /en, /ja, /hi, /ar, /es, /te)

Port 80 (web) — unfiltered, performs blanket HTTPS redirect only
Internal container-to-container traffic — unaffected (uses Docker network, not public entrypoints)
```

---

## Files Changed

### 1. `components/analytics/traefik_rules.yml` — **Created**

New Traefik file-provider rules file defining the `ip-allowlist` middleware.

Traefik already has a file provider watching `/etc/traefik/rules/` (configured via `TRAEFIK_PROVIDERS_FILE_DIRECTORY` in `docker-compose.yml`). This file is mounted into that directory, so Traefik picks it up automatically and **hot-reloads** it on any change — no container restart required.

```yaml
http:
  middlewares:
    ip-allowlist:
      ipAllowList:
        # TODO: Remove 0.0.0.0/0 when ready to restrict access to specific IPs only.
        sourceRange:
          - "0.0.0.0/0"        # temporary: allow all while validating
          - "57.181.61.79"
          - "134.231.136.93"
          - "134.231.136.94"
          - "169.224.186.89"
          - "169.224.186.0"
          - "165.85.181.188"
          - "165.85.181.171"
          - "165.85.181.170"
          - "165.85.181.169"
          - "165.85.154.78"
          - "165.85.154.7"
          - "165.85.0.174"
          - "165.85.0.157"
          - "134.231.146.225"
          - "134.231.146.226"
          - "208.127.164.90"
          - "169.224.186.205"
          - "128.77.46.13"
          - "134.231.136.202"
          - "165.85.203.52"
          - "134.231.146.249"
          - "144.125.89.251"
          - "144.125.89.252"
          - "144.125.89.253"
          - "144.125.89.254"
          - "144.125.89.255"
          - "169.224.186.64"
          - "169.224.186.48"
          - "169.224.186.47"
          - "134.231.215.45"
          - "134.231.215.44"
```

---

### 2. `docker-compose.production.yml` — **Modified**

Four changes were made to this file:

#### a) `traefik` service — new volume mount

Mounts the allowlist rules file into Traefik's file-provider directory:

```yaml
traefik:
  volumes:
    - ./components/analytics/traefik_rules.yml:/etc/traefik/rules/traefik_rules.yml:ro
```

#### b) `cvat_server` service — new label

Attaches `ip-allowlist` to the `cvat` HTTPS router (handles `/api/`, `/static/`, `/admin`, `/django-rq`):

```yaml
cvat_server:
  labels:
    traefik.http.routers.cvat.middlewares: "ip-allowlist@file"
```

#### c) `cvat_ui` service — new label

Attaches `ip-allowlist` to the `cvat-ui` HTTPS router (catch-all, serves the Web UI):

```yaml
cvat_ui:
  labels:
    traefik.http.routers.cvat-ui.middlewares: "ip-allowlist@file"
```

#### d) `angular_dashboard` service — middleware list updated

Appended `ip-allowlist@file` to the existing middleware chain on the `angular-dashboard-https` router:

```yaml
# Before
traefik.http.routers.angular-dashboard-https.middlewares: "dashboard-cors,dashboard-security"

# After
traefik.http.routers.angular-dashboard-https.middlewares: "dashboard-cors,dashboard-security,ip-allowlist@file"
```

---

## Whitelisted IPs

| # | IP Address |
|---|---|
| 1 | 57.181.61.79 |
| 2 | 134.231.136.93 |
| 3 | 134.231.136.94 |
| 4 | 169.224.186.89 |
| 5 | 169.224.186.0 |
| 6 | 165.85.181.188 |
| 7 | 165.85.181.171 |
| 8 | 165.85.181.170 |
| 9 | 165.85.181.169 |
| 10 | 165.85.154.78 |
| 11 | 165.85.154.7 |
| 12 | 165.85.0.174 |
| 13 | 165.85.0.157 |
| 14 | 134.231.146.225 |
| 15 | 134.231.146.226 |
| 16 | 208.127.164.90 |
| 17 | 169.224.186.205 |
| 18 | 128.77.46.13 |
| 19 | 134.231.136.202 |
| 20 | 165.85.203.52 |
| 21 | 134.231.146.249 |
| 22 | 144.125.89.251 |
| 23 | 144.125.89.252 |
| 24 | 144.125.89.253 |
| 25 | 144.125.89.254 |
| 26 | 144.125.89.255 |
| 27 | 169.224.186.64 |
| 28 | 169.224.186.48 |
| 29 | 169.224.186.47 |
| 30 | 134.231.215.45 |
| 31 | 134.231.215.44 |

> **Note:** `0.0.0.0/0` is currently included in the `sourceRange`, which overrides all individual IP restrictions and allows traffic from any source. This is intentional during the validation/rollout phase. Once confirmed stable, remove `0.0.0.0/0` from `components/analytics/traefik_rules.yml` to enforce the allowlist. No container restart is needed — Traefik hot-reloads the file.

---

## Protected Services

| Service | Router Name | Entry Point | Paths Protected |
|---|---|---|---|
| `cvat_server` | `cvat` | `websecure` (443) | `/api/`, `/static/`, `/admin`, `/django-rq` |
| `cvat_ui` | `cvat-ui` | `websecure` (443) | All paths (catch-all) |
| `angular_dashboard` | `angular-dashboard-https` | `websecure` (443) | `/dashboard`, `/en`, `/ja`, `/hi`, `/ar`, `/es`, `/te` |

---

## Services NOT Filtered

| Service | Reason |
|---|---|
| `cvat_grafana` | Internal analytics — not requested |
| Port 80 (`web` entrypoint) | Only performs blanket HTTP→HTTPS redirect; no content served |
| Internal container traffic | Uses Docker internal network (`cvat`), never passes through Traefik public entrypoints |

---

## How to Enforce the IP Allowlist (When Ready)

1. Open `components/analytics/traefik_rules.yml`
2. Remove the `"0.0.0.0/0"` line from `sourceRange`
3. Save the file

Traefik detects the change and reloads within seconds. **No `docker compose` restart is required.**

---

## How to Add or Remove IPs in the Future

1. Open `components/analytics/traefik_rules.yml`
2. Add or remove entries under `sourceRange`
3. Save the file — Traefik hot-reloads automatically

---

## Technical Notes

| Topic | Detail |
|---|---|
| Traefik version | v3.6 |
| Middleware type | `ipAllowList` (Traefik v3 camelCase naming) |
| Provider | File provider (`@file` suffix used in label references) |
| Blocked response | HTTP `403 Forbidden` |
| `@file` suffix | Required when a Docker label references a middleware defined in a file-provider config, not in Docker labels |
| File provider directory | `/etc/traefik/rules/` — already configured in base `docker-compose.yml` via `TRAEFIK_PROVIDERS_FILE_DIRECTORY` |
