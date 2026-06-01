#!/bin/bash
# setup-runner.sh — Install GitHub Actions self-hosted runner on Debian
#
# WHY: The runner process lives on YOUR server and opens an outbound websocket
# to GitHub. GitHub pushes jobs through that connection — no inbound ports needed.
#
# USAGE:
#   1. Go to your GitHub repo → Settings → Actions → Runners → New self-hosted runner
#   2. Copy the token shown there (valid 1 hour)
#   3. On your Debian server: bash setup-runner.sh <REPO_URL> <TOKEN>
#
# EXAMPLE:
#   bash setup-runner.sh https://github.com/rana/ppt abc123tokenhere

set -euo pipefail

REPO_URL="${1:?Usage: $0 <repo-url> <token>}"
TOKEN="${2:?Usage: $0 <repo-url> <token>}"
RUNNER_VERSION="2.334.0"
RUNNER_USER="github-runner"
RUNNER_DIR="/opt/actions-runner"

echo "==> Installing GitHub Actions self-hosted runner"
echo "    Repo:    $REPO_URL"
echo "    Version: $RUNNER_VERSION"

# ── 1. Create a dedicated system user (no login shell, safer) ────────────────
# WHY: Never run the runner as root. A dedicated user limits blast radius.
if ! id "$RUNNER_USER" &>/dev/null; then
  sudo useradd -m -s /usr/sbin/nologin "$RUNNER_USER"
  echo "==> Created user: $RUNNER_USER"
fi

# Give the runner user Docker access so it can run docker compose
sudo usermod -aG docker "$RUNNER_USER"

# ── 2. Download runner ───────────────────────────────────────────────────────
sudo mkdir -p "$RUNNER_DIR"
sudo chown "$RUNNER_USER:$RUNNER_USER" "$RUNNER_DIR"

cd "$RUNNER_DIR"
ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$ARCHIVE" ]; then
  sudo -u "$RUNNER_USER" curl -fsSL \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}" \
    -o "$ARCHIVE"
fi
sudo -u "$RUNNER_USER" tar xzf "$ARCHIVE"

# ── 3. Configure the runner ──────────────────────────────────────────────────
# WHY: --unattended skips interactive prompts; --labels lets you target this
# specific runner from the workflow with runs-on: [self-hosted, ppt-server]
sudo -u "$RUNNER_USER" ./config.sh \
  --url "$REPO_URL" \
  --token "$TOKEN" \
  --name "ppt-debian-server" \
  --labels "self-hosted,ppt-server,debian" \
  --work "_work" \
  --unattended \
  --replace

# ── 4. Install as a systemd service ─────────────────────────────────────────
# WHY: systemd restarts the runner if it crashes and starts it on boot.
sudo ./svc.sh install "$RUNNER_USER"
sudo ./svc.sh start

echo ""
echo "✅ Runner installed and running as systemd service."
echo "   Check status: sudo systemctl status actions.runner.*"
echo "   View logs:    journalctl -u actions.runner.* -f"
echo ""
echo "Next: push to main and watch the Actions tab in GitHub."
