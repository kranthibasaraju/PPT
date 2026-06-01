# Epic: PPT Infrastructure — Dedicated Home Server

**Status:** 🟡 In Progress  
**Created:** 2026-05-31  
**Owner:** Rana  

---

## Why this epic exists

The Mac Mini is doing too much — running PPT services, Ollama, Piper TTS, and
potentially Plane + dashboards all at once. An old Windows PC repurposed as a
headless Debian server offloads Docker-based services and gives PPT a dedicated
always-on infrastructure node.

This is the foundation everything else runs on.

---

## Hardware

| Spec | Detail |
|---|---|
| Machine | Old Windows laptop → headless Debian server |
| RAM | 7.7 GB |
| Storage | 1 TB HDD |
| GPU | Intel HD 620 (supports hardware transcoding) |
| Power | Plugged in always, no battery dependency |
| Network | Wired ethernet — static IP `10.0.0.50` |
| Access | SSH from Mac Mini / any LAN device |

---

## Epic Goal

> A stable always-on Debian server at `10.0.0.50` running Docker-based
> self-hosted services — Plane, Grafana, Uptime Kuma, Dashy — accessible
> from Mac and phone over the local network, secured and monitored.

---

## Stories

---

### ✅ Story 1 — OS Install & Network Setup (DONE 2026-05-31)
Get Debian running and reachable over the network.

| Task | Status | Notes |
|---|---|---|
| Install Debian 12 on the old Windows PC | ✅ Done 2026-05-31 | Desktop UI installed |
| Configure static IP `10.0.0.50/24` on `eno1` | ✅ Done 2026-05-31 | Via NetworkManager |
| Install + enable OpenSSH server | ✅ Done 2026-05-31 | |
| Confirm SSH from Mac: `ssh user@10.0.0.50` | ✅ Done 2026-05-31 | |

---

### 🟡 Story 2 — Security Hardening
Lock down the server before exposing it to Docker services.

**WHY harden before Docker:**
  Docker opens ports. If root SSH login is still on when your first container
  starts, you've created an attack surface before adding any protection.
  Harden first, then expose services.

| Task | Status | Notes |
|---|---|---|
| Add user to sudo group (non-root admin) | ✅ Done 2026-05-31 | |
| Disable root SSH login (`PermitRootLogin no`) | 🔲 Todo | Edit `/etc/ssh/sshd_config` |
| Copy Mac SSH public key → server (`ssh-copy-id`) | 🔲 Todo | Passwordless login from Mac |
| Disable SSH password auth (`PasswordAuthentication no`) | 🔲 Todo | Keys only after above step |
| Install + configure UFW firewall | 🔲 Todo | Allow: 22 (SSH), 80, 443, Docker service ports |
| Install Fail2ban | 🔲 Todo | Auto-ban IPs that fail SSH repeatedly |
| Update all packages (`sudo apt upgrade -y`) | 🔲 Todo | |
| Enable unattended security upgrades | 🔲 Todo | `sudo apt install unattended-upgrades` |

---

### 🔲 Story 3 — Docker & Compose
Runtime for all self-hosted services.

**WHY Docker:**
  Every service (Plane, Grafana, Uptime Kuma) ships an official Docker image.
  Docker Compose means one file per service stack — start/stop/upgrade in one command.
  No dependency conflicts between services.

| Task | Status | Notes |
|---|---|---|
| Install Docker Engine on Debian | 🔲 Todo | Official install script: `curl -fsSL https://get.docker.com \| sh` |
| Add user to `docker` group (no sudo needed) | 🔲 Todo | `sudo usermod -aG docker $USER` |
| Install Docker Compose v2 | 🔲 Todo | Included with Docker Engine v2 |
| Enable Docker on boot | 🔲 Todo | `sudo systemctl enable docker` |
| Create `~/services/` directory structure | 🔲 Todo | One subdir per service |
| Test: `docker run hello-world` | 🔲 Todo | Confirms install |

---

### 🔲 Story 4 — Core Services (Plane + Monitoring)
The first services running on the server.

| Task | Status | Notes |
|---|---|---|
| **Uptime Kuma** — service health monitoring | 🔲 Todo | Port 3001 · `louislam/uptime-kuma` |
| **Grafana + Prometheus** — metrics dashboards | 🔲 Todo | Ports 3000/9090 |
| **Dashy** — central homepage for all services | 🔲 Todo | Port 4000 · `lissy93/dashy` |
| **Plane** — project management (move from Mac Mini) | 🔲 Todo | Port 8000 · self-hosted |
| Create base `docker-compose.yml` in `~/services/` | 🔲 Todo | All core services in one file |
| Confirm all dashboards reachable from Mac browser | 🔲 Todo | `http://10.0.0.50:<port>` |
| Add all service URLs to Dashy homepage | 🔲 Todo | |
| Add all services to Uptime Kuma monitoring | 🔲 Todo | Alert via Telegram if any go down |

---

### 🔲 Story 5 — Remote Access (Tailscale)
Access the server from outside the home network — phone, work, anywhere.

**WHY Tailscale over port-forwarding:**
  Port-forwarding punches holes in your router for the whole internet.
  Tailscale creates a private encrypted mesh — only your devices can connect,
  no firewall rules, no dynamic DNS, no exposed ports. Free for personal use.

| Task | Status | Notes |
|---|---|---|
| Install Tailscale on Debian server | 🔲 Todo | `curl -fsSL https://tailscale.com/install.sh \| sh` |
| Install Tailscale on Mac Mini | 🔲 Todo | `brew install tailscale` |
| Install Tailscale on phone | 🔲 Todo | iOS/Android app |
| Confirm server reachable at Tailscale IP from phone | 🔲 Todo | |
| Access Dashy / Plane from phone over Tailscale | 🔲 Todo | |

---

### 🔲 Story 6 — Optional Services
Nice-to-have once core is stable.

| Task | Status | Notes |
|---|---|---|
| **Gitea** — self-hosted GitHub alternative | 🔲 Optional | Port 3030 · useful if going fully self-hosted |
| **Jellyfin** — media server | 🔲 Optional | Intel HD 620 supports hardware transcoding |
| **Portainer** — Docker web UI | 🔲 Optional | Manage containers without SSH |
| **Vaultwarden** — self-hosted Bitwarden | 🔲 Optional | Password manager |

---

### 🔲 Story 7 — PPT Integration
Point PPT services at the server instead of running on Mac Mini.

| Task | Status | Notes |
|---|---|---|
| Update PPT orchestrator to use Plane API at `10.0.0.50` | 🔲 Todo | Replace Mac Mini hosting |
| Point Uptime Kuma at all PPT services (board, notify daemon, etc.) | 🔲 Todo | |
| Add server metrics to PPT board (`/api/board`) | 🔲 Todo | CPU, RAM, disk from Prometheus |
| Morning digest includes server health summary | 🔲 Todo | "All services up ✓" |

---

### 🟡 Story 2 — Security Hardening (In Progress)

| Task | Status | Notes |
|---|---|---|
| Add user to sudo group | ✅ Done 2026-05-31 | `debian` user |
| Disable root SSH login (`PermitRootLogin no`) | ✅ Done 2026-05-31 | |
| Copy Mac SSH public key → server | ✅ Done 2026-05-31 | `debian@10.0.0.50` |
| Disable SSH password auth (`PasswordAuthentication no`) | ✅ Done 2026-05-31 | Keys only |
| Install + configure UFW firewall | ✅ Done 2026-05-31 | Ports: 22, 80, 443, 5001 open |
| Update all packages (`sudo apt upgrade -y`) | ✅ Done 2026-05-31 | Debian Trixie up to date |
| Install Fail2ban | 🟡 In Progress | |
| Enable unattended security upgrades | 🔲 Todo | `sudo apt install unattended-upgrades` |

---

### 🟡 Story 8 — CI/CD: Self-Hosted GitHub Actions Runner
Automated deploys from GitHub to Debian — no port forwarding, no SSH keys in CI.

**HOW IT WORKS:**
  Runner process on the server opens an outbound websocket to GitHub.
  GitHub sends deploy jobs through that connection — zero inbound ports needed.

**Runner user:** `debian` (existing system user, already in `docker` group).
  Simpler than a dedicated runner user for a single personal server.
  If this ever becomes a team server, create a dedicated `github-runner` user.

| Task | Status | Notes |
|---|---|---|
| Clone PPT repo to `~/PPT` | ✅ Done 2026-05-31 | `git clone https://github.com/kranthibasaraju/PPT.git ~/PPT` |
| Add GitHub Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | ✅ Done 2026-05-31 | Repo → Settings → Secrets → Actions |
| Install Docker on Debian | 🔲 Todo | `curl -fsSL https://get.docker.com \| sh` |
| Add `debian` user to `docker` group | 🔲 Todo | `sudo usermod -aG docker debian && newgrp docker` |
| Register runner: `bash ~/PPT/scripts/setup-runner.sh <repo-url> <token>` | 🔲 Todo | Token from GitHub → Settings → Actions → Runners (expires 1h) |
| Verify runner Online in GitHub → Actions → Runners | 🔲 Todo | |
| Trigger first deploy via `workflow_dispatch` | 🔲 Todo | Writes `.env` from secrets, builds image, starts ppt-notify |
| Rotate Telegram bot token (was briefly in public repo) | 🔲 Todo | BotFather → /mybots → Revoke → update Secret + local settings.py |

**Key files:**
- `scripts/setup-runner.sh` — install + systemd registration (v2.334.0, user: `debian`)
- `.github/workflows/deploy.yml` — runs on `[self-hosted, ppt-server]`
- `docker-compose.yml` — ppt-notify container, reads `staging/ppt-notify/.env`

---

### 🔲 Story 9 — System Status Monitoring
Track Debian server health — CPU, RAM, disk, services — visible on the PPT board.

**WHY track system status:**
  When services are deployed to the server, you need to know at a glance if
  it's healthy — disk not full, RAM not exhausted, services running.
  Two layers: real-time metrics (Netdata) + service uptime (Uptime Kuma).

**Quick win — Netdata (zero config, beautiful, single command):**
  Netdata installs in one line and gives a full real-time dashboard at port 19999.
  No Prometheus, no Grafana config needed. Add Grafana later for historical data.

| Task | Status | Notes |
|---|---|---|
| Install Netdata on Debian server | 🔲 Todo | `curl https://my-netdata.io/kickstart.sh \| sh` |
| Open port 19999 in UFW | 🔲 Todo | `sudo ufw allow 19999/tcp comment 'Netdata'` |
| Verify at `http://10.0.0.50:19999` | 🔲 Todo | Real-time CPU, RAM, disk, network |
| Install Uptime Kuma via Docker | 🔲 Todo | Port 3001 — monitors services are up |
| Add PPT Board health check to Uptime Kuma | 🔲 Todo | HTTP check: `http://localhost:5001/health` |
| Add Telegram alert in Uptime Kuma when service goes down | 🔲 Todo | Uses PPT bot token |
| Add `/board/system` page to PPT board | 🔲 Todo | Shows server CPU/RAM/disk via Netdata API |
| Add system metrics strip to PPT board dashboard | 🔲 Todo | `CPU: 12% · RAM: 2.1/7.7GB · Disk: 45GB free` |
| Add Netdata + Uptime Kuma URLs to UFW docs | 🔲 Todo | Update `docs/SERVER_FIREWALL.md` |

---

## Open Questions

| # | Question | Status |
|---|---|---|
| OQ-S1 | Keep Plane on Mac Mini or move fully to server? | → Move to server (offload Mac Mini) |
| OQ-S2 | Should server also run PPT backend (STT/LLM) or stay as infra only? | Open — Mac Mini has Apple Silicon advantage for LLM |
| OQ-S3 | Tailscale vs local-only — how much remote access do you need? | Open |
| OQ-S4 | Headless vs desktop — keep GNOME desktop or switch to CLI-only? | Open — CLI saves ~500MB RAM |

---

## Build Order

```
Story 1 (done) → Story 2 (harden) → Story 3 (Docker) → Story 4 (services)
                                                       → Story 5 (Tailscale)
                                                       → Story 6 (optional)
                                                       → Story 7 (PPT integration)
```

---

## Progress Log

| Date | Update |
|---|---|
| 2026-05-30 | Started Debian install attempt on old Windows PC |
| 2026-05-31 | Story 1 complete — Debian up, static IP `10.0.0.50`, SSH confirmed from Mac |
| 2026-05-31 | Story 2 in progress — root login disabled, SSH keys set up, UFW active, packages updated. Fail2ban remaining. |
| 2026-05-31 | Story 8 started — repo cloned to Debian, GitHub Secrets added. Runner registration next. Runner runs as `debian` user (not dedicated github-runner user). |

---

## Related Files

- `docs/EPIC_PPT_INFRA.md` — this file
- `TODO.md` — Infrastructure section mirrors story tasks
