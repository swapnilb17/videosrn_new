#!/usr/bin/env bash
# First-time server setup. Run as a user with sudo (not root).
# Before running: add a GitHub Deploy Key so the server can git pull.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/enably/videosrn}"
GIT_REPO="${GIT_REPO:-git@github.com:swapnilb17/videosrn_new.git}"

if [[ "${EUID:-0}" -eq 0 ]]; then
  echo "Run as a normal user with sudo (not root)."
  exit 1
fi

echo ">>> Installing Docker (if not present)"
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. You may need to log out and back in for group changes."
fi

echo ">>> Enabling Docker service"
sudo systemctl enable docker --now

echo ">>> Installing Docker Compose plugin (if not present)"
if ! docker compose version &>/dev/null; then
  sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null \
    || sudo dnf install -y docker-compose-plugin 2>/dev/null \
    || echo "Install docker-compose-plugin manually."
fi

echo ">>> Creating application directory"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

echo ">>> Creating data directories"
sudo mkdir -p /opt/enably/pgdata
sudo mkdir -p /opt/enably/gcp-credentials
sudo mkdir -p /mnt/scratch/jobs

echo ">>> Cloning repository"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$GIT_REPO" "$APP_DIR"
else
  echo "Repo already present at $APP_DIR — skipping clone"
fi

echo ">>> Setting up deploy key for GitHub"
if [[ ! -f ~/.ssh/deploy_key ]]; then
  ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N "" -C "deploy@$(hostname)"
  echo ""
  echo "=========================================="
  echo "Add this public key as a Deploy Key on GitHub:"
  echo "  Repo → Settings → Deploy keys → Add deploy key"
  echo "=========================================="
  cat ~/.ssh/deploy_key.pub
  echo "=========================================="
  echo ""

  mkdir -p ~/.ssh
  cat >> ~/.ssh/config <<SSHEOF
Host github.com
  IdentityFile ~/.ssh/deploy_key
  IdentitiesOnly yes
SSHEOF
  chmod 600 ~/.ssh/config
fi

echo ""
echo ">>> Bootstrap complete."
echo ""
echo "Next steps:"
echo "  1) Add the deploy key above to GitHub (if not already done)"
echo "  2) Copy .env.docker.example to .env and fill in secrets:"
echo "       cd $APP_DIR && cp .env.docker.example .env && nano .env"
echo "  3) Place GCP service-account.json in /opt/enably/gcp-credentials/"
echo "  4) Set up HTTPS with certbot:"
echo "       sudo certbot certonly --standalone -d ai.enablyai.com"
echo "  5) Start the app:"
echo "       cd $APP_DIR && docker compose up -d"
echo "  6) Add these GitHub repo secrets for auto-deploy:"
echo "       SERVER_SSH_PRIVATE_KEY  — your SSH private key to this server"
echo "       SERVER_HOST             — server IP or hostname"
echo "       SERVER_USER             — SSH username (e.g. ubuntu)"
