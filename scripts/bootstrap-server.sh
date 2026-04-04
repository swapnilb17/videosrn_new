#!/usr/bin/env bash
# First-time server setup. Run as a user with sudo (not root).
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/enably-vgen}"
GIT_REPO_SSH="${GIT_REPO_SSH:-git@github.com:swapnilb17/videosrn_new.git}"
GIT_REPO_HTTPS="${GIT_REPO_HTTPS:-https://github.com/swapnilb17/videosrn_new.git}"

if [[ "${EUID:-0}" -eq 0 ]]; then
  echo "Run as a normal user with sudo (not root)."
  exit 1
fi

# ── 1. Docker ────────────────────────────────────────────────
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

# ── 2. Directories ───────────────────────────────────────────
echo ">>> Creating application directory"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

echo ">>> Creating data directories"
sudo mkdir -p /opt/enably/pgdata
sudo mkdir -p /opt/enably/gcp-credentials
sudo mkdir -p /mnt/scratch/jobs

# ── 3. Deploy key (BEFORE clone) ────────────────────────────
echo ">>> Setting up deploy key for GitHub"
mkdir -p ~/.ssh
chmod 700 ~/.ssh

if [[ ! -f ~/.ssh/deploy_key ]]; then
  ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N "" -C "deploy@$(hostname)"

  if ! grep -q "Host github.com" ~/.ssh/config 2>/dev/null; then
    cat >> ~/.ssh/config <<'SSHEOF'
Host github.com
  IdentityFile ~/.ssh/deploy_key
  IdentitiesOnly yes
SSHEOF
    chmod 600 ~/.ssh/config
  fi
fi

ssh-keyscan -H github.com >> ~/.ssh/known_hosts 2>/dev/null

echo ""
echo "=========================================="
echo "  DEPLOY KEY (add to GitHub before continuing)"
echo "  Repo → Settings → Deploy keys → Add deploy key"
echo "=========================================="
cat ~/.ssh/deploy_key.pub
echo "=========================================="
echo ""
read -rp "Press ENTER after you've added the key to GitHub... "

# ── 4. Clone ─────────────────────────────────────────────────
echo ">>> Cloning repository"
if [[ ! -d "$APP_DIR/.git" ]]; then
  if git clone "$GIT_REPO_SSH" "$APP_DIR"; then
    echo "Cloned via SSH"
  else
    echo "SSH clone failed — falling back to HTTPS (read-only)"
    git clone "$GIT_REPO_HTTPS" "$APP_DIR"
    echo "NOTE: Switch remote to SSH later for deploy pulls:"
    echo "  cd $APP_DIR && git remote set-url origin $GIT_REPO_SSH"
  fi
else
  echo "Repo already present at $APP_DIR — skipping clone"
fi

# ── 5. Configure git remote to use SSH for pulls ─────────────
cd "$APP_DIR"
CURRENT_URL=$(git remote get-url origin 2>/dev/null || true)
if [[ "$CURRENT_URL" != "$GIT_REPO_SSH" ]]; then
  git remote set-url origin "$GIT_REPO_SSH"
  echo "Remote origin set to SSH: $GIT_REPO_SSH"
fi

echo ""
echo "=========================================="
echo "  Bootstrap complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1) Copy .env.docker.example to .env and fill in secrets:"
echo "       cd $APP_DIR && cp .env.docker.example .env && nano .env"
echo "  2) Place GCP service-account.json in /opt/enably/gcp-credentials/"
echo "  3) Set up HTTPS with certbot:"
echo "       sudo certbot certonly --standalone -d ai.enablyai.com"
echo "  4) Start the app:"
echo "       cd $APP_DIR && docker compose up -d"
echo "  5) Add these GitHub repo secrets for auto-deploy (Settings → Secrets → Actions):"
echo "       SERVER_SSH_PRIVATE_KEY  — your SSH private key to this server"
echo "       SERVER_HOST             — server IP or hostname"
echo "       SERVER_USER             — SSH username (e.g. ec2-user)"
