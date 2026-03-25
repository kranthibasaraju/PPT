# Chapter 3 — Infrastructure
## Where Does It All Run?

---

## What Infrastructure Means

Infrastructure is everything that is not your application code. It is the hardware your software runs on, the operating system it lives in, the network it talks across, and the processes that keep it running when you close your laptop and go to bed.

Good infrastructure is invisible. You don't think about it because it just works. Bad infrastructure is the thing that wakes you up at 3am because the service crashed and nobody restarted it.

For a personal project like PPT, "production-grade" is overkill — but the infrastructure still needs to be solid enough that PPT works reliably day after day without manual intervention.

---

## The Hardware

PPT runs on two physical devices.

### Raspberry Pi 4

**Role:** Always-on edge node. Handles wake word detection, microphone input, and speaker output.

**Why the Pi?** It is purpose-built for this role. It consumes roughly 3 watts when idle, runs cool without a fan (with a basic heatsink), and runs a full Linux operating system. You plug it in, set it up once, and it runs indefinitely.

The Pi does not need to be fast. OpenWakeWord runs a small neural network on short audio windows. This is well within the Pi's capabilities. The heavy work — STT, LLM, TTS — is offloaded to the Mac Mini.

**Operating system:** Raspberry Pi OS Lite (no desktop environment). Headless — no monitor needed. Accessed via SSH.

**Peripherals needed:**
- USB microphone (any basic desk mic, $10–20)
- USB speaker or 3.5mm speaker

### Mac Mini (Apple Silicon)

**Role:** Processing hub. Runs Whisper, Ollama, and Piper TTS. Also hosts Plane (via Docker) and the Discord bot.

**Why the Mac Mini?** It is already owned. Apple Silicon (M-series chip) is exceptional at running machine learning workloads. Whisper runs at near real-time speeds. Ollama can run Llama 3 models efficiently. The Mac Mini can be left on permanently or configured to wake from sleep when the Pi sends a network request.

**Operating system:** macOS. Services run via `launchd` (macOS's built-in daemon manager) or Docker.

---

## The Network

Both devices connect to the same home WiFi network (or LAN). They communicate with each other via local IP addresses. No internet connection is required for any part of the voice pipeline.

### IP Setup

For reliability, assign static local IP addresses to both devices. This prevents the router from changing their addresses after a reboot.

**Option 1 — Router DHCP reservation:** Set the router to always give each device the same IP based on its MAC address. No configuration needed on the devices themselves.

**Option 2 — Static IP on device:** Configure a fixed IP directly in the OS network settings.

Recommended IPs (example — adjust to your router's range):
- RPi4: `192.168.1.100`
- Mac Mini: `192.168.1.101`

### Communication Protocol

The RPi4 and Mac Mini communicate via HTTP. When the Pi detects a wake word and records speech, it sends the audio file to the Mac Mini's processing service as an HTTP POST request. The Mac Mini responds with audio data after processing.

HTTP is used because it is simple, widely understood, and works well on a local network. WebSockets could be used for streaming (lower latency) in a future version.

---

## Running Services (macOS — launchd)

On macOS, long-running background services are managed by `launchd`. A launchd plist (property list) file describes a service: what command to run, when to start it, what to do if it crashes.

### Creating a launchd service

A plist file for the PPT processor looks like this:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ppt.processor</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/rdy/Documents/Projects/PPT/.venv/bin/python</string>
    <string>/Users/rdy/Documents/Projects/PPT/src/orchestrator/pipeline.py</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>/Users/rdy/Documents/Projects/PPT/logs/ppt.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/rdy/Documents/Projects/PPT/logs/ppt-error.log</string>
</dict>
</plist>
```

`KeepAlive: true` means launchd restarts the service automatically if it crashes. This is essential for an always-on assistant.

To load a service:
```bash
launchctl load ~/Library/LaunchAgents/com.ppt.processor.plist
```

### Running Services (RPi4 — systemd)

On Raspberry Pi OS (Linux), services are managed by `systemd`. A unit file describes the service:

```ini
[Unit]
Description=PPT Wake Word Detector
After=network.target sound.target

[Service]
ExecStart=/home/pi/ppt/.venv/bin/python /home/pi/ppt/src/wake/detector.py
WorkingDirectory=/home/pi/ppt
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

`Restart=always` ensures the service restarts if it crashes. `RestartSec=5` prevents rapid restart loops.

To enable a service to start at boot:
```bash
sudo systemctl enable ppt-wake.service
sudo systemctl start ppt-wake.service
```

---

## Docker and Plane

Plane (the project management dashboard) runs in Docker on the Mac Mini.

### What is Docker?

Docker is a tool for running applications in isolated containers. A container packages an application and all its dependencies together, so it runs the same way regardless of what else is installed on the host machine.

Think of it like a shipping container: standardised, portable, self-contained.

### Why Docker for Plane?

Plane is a complex application with multiple services (web server, database, background workers). Running it natively would require installing and configuring each service individually. Docker Compose allows all of them to start with a single command.

### Docker Compose

Plane provides an official `docker-compose.yml` file. To start Plane:

```bash
# Download the official setup
git clone https://github.com/makeplane/plane.git
cd plane

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start all services
docker compose up -d
```

`-d` means "detached" — runs in the background. After this, Plane is accessible on the local network at `http://192.168.1.101:3000` (the Mac Mini's IP, port 3000).

### Accessing Plane from the Phone

Since Plane runs on the Mac Mini's local IP, it is only accessible from within your home network. The Plane Android app can connect to a self-hosted instance by entering the URL.

For access outside the home network (optional, future), options include:
- Tailscale — creates a private VPN between your devices, free for personal use
- Cloudflare Tunnel — exposes local services via a secure tunnel

---

## Storage

All data lives on the devices themselves.

| Data | Location | Notes |
|---|---|---|
| Project/task data | Plane (PostgreSQL in Docker, Mac Mini) | Managed by Plane |
| Voice context / session history | SQLite file (Mac Mini) | Simple, no server needed |
| Audio files (temp) | RAM / /tmp | Deleted after processing |
| Logs | /logs/ directory (Mac Mini) | Rotated daily |
| Config | config/settings.py | Checked into git |

No data goes to external cloud services. All backups (if desired) are simple file copies.

---

## Resilience Considerations

A personal assistant that isn't running is useless. Several things can make it stop working:

**Power outage:** Both devices need to be set to auto-start services on boot. launchd and systemd both support this. The Pi starts faster than the Mac Mini — the wake detector will be ready before the processing hub, which is fine.

**WiFi outage:** If the Pi can't reach the Mac Mini, it should queue the request and retry. For now (Phase 0), we accept that the pipeline fails gracefully and loops back to listening.

**Mac Mini goes to sleep:** macOS can be configured to disable sleep. In System Settings → Energy → Prevent computer from sleeping automatically. The Mac Mini can also be woken remotely via Wake-on-LAN if needed.

**Service crash:** launchd and systemd restart services automatically. Logs capture what went wrong.

---

## Phase 0 Infrastructure (Simplified)

In Phase 0, there is no RPi4. Everything runs on the Mac Mini. The infrastructure is:

- Python virtual environment (.venv/) with all dependencies installed
- Four Python scripts run manually from the terminal
- No daemon setup, no Docker, no network communication
- macOS built-in audio in/out

This is the right starting point. Get the software working first, worry about making it robust later.

---

*Next: [Chapter 4 — Design Patterns →](../04-design-patterns/README.md)*
