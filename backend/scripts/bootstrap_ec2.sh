#!/usr/bin/env bash
# First-time EC2 setup. Run over SSH as a user with sudo (ubuntu on Ubuntu AMI, ec2-user on Amazon Linux).
# Before this: run setup_github_readonly_deploy_key.sh and add the public key to GitHub Deploy keys.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/avatar-video-creator}"
GIT_REPO="${GIT_REPO:-git@github.com:swapnilb17/Videosrv.git}"

if [[ "${EUID:-0}" -eq 0 ]]; then
  echo "Run as a normal user with sudo (not root)."
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck source=/dev/null
  . /etc/os-release
fi
OS_ID="${ID:-unknown}"

# Amazon Linux 2023 has no ffmpeg in default repos; use a static build (johnvansickle.com).
install_ffmpeg_static() {
  local arch url tmpd dir
  arch=$(uname -m)
  case "$arch" in
    x86_64) url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" ;;
    aarch64) url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz" ;;
    *)
      echo "No static ffmpeg URL for arch=$arch; install ffmpeg manually."
      return 1
      ;;
  esac
  tmpd=$(mktemp -d)
  echo "    fetching $url"
  if ! curl -fsSL "$url" | tar -xJ -C "$tmpd"; then
    rm -rf "$tmpd"
    return 1
  fi
  dir=$(find "$tmpd" -maxdepth 1 -type d -name 'ffmpeg-*-static' | head -1)
  if [[ -z "$dir" || ! -x "$dir/ffmpeg" ]]; then
    echo "Unpack failed or ffmpeg binary missing under $tmpd"
    ls -la "$tmpd" || true
    rm -rf "$tmpd"
    return 1
  fi
  sudo rm -rf /opt/ffmpeg-static
  sudo mv "$dir" /opt/ffmpeg-static
  sudo mkdir -p /usr/local/bin
  sudo ln -sf /opt/ffmpeg-static/ffmpeg /usr/local/bin/ffmpeg
  sudo ln -sf /opt/ffmpeg-static/ffprobe /usr/local/bin/ffprobe
  hash -r 2>/dev/null || true
  ffmpeg -version | head -1
  rm -rf "$tmpd"
}

install_packages() {
  case "$OS_ID" in
    ubuntu|debian)
      echo ">>> apt packages (Ubuntu/Debian)"
      sudo apt-get update
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        git curl ca-certificates ffmpeg nginx postgresql postgresql-contrib \
        python3-venv python3-pip certbot python3-certbot-nginx build-essential acl
      ;;
    amzn)
      echo ">>> dnf packages (Amazon Linux)"
      # Do NOT install package "curl": it conflicts with the default "curl-minimal" (curl already works).
      # App needs Python >=3.11 (pyproject.toml); AL2023 default python3 is often 3.9.
      sudo dnf install -y git ca-certificates nginx python3.11 python3.11-pip gcc make tar xz findutils
      echo ">>> ffmpeg (not in default Amazon Linux 2023 repos — static binaries)"
      if command -v ffmpeg >/dev/null 2>&1; then
        ffmpeg -version | head -1
      else
        install_ffmpeg_static
      fi
      if sudo dnf install -y postgresql15-server postgresql15 2>/dev/null; then
        if [[ ! -f /var/lib/pgsql/data/PG_VERSION ]]; then
          sudo postgresql-setup --initdb || true
        fi
        sudo systemctl enable postgresql --now || sudo systemctl enable postgresql15 --now || true
      else
        echo "!!! PostgreSQL not installed automatically — install server packages for your AMI or use RDS."
      fi
      if sudo dnf install -y certbot python3-certbot-nginx 2>/dev/null; then
        :
      else
        echo "!!! certbot not in repos — install later for HTTPS (see docs)."
      fi
      ;;
    *)
      echo "Unsupported OS ID=$OS_ID (expected ubuntu, debian, or amzn)."
      echo "Use Ubuntu 22.04+ or Amazon Linux 2023, or install deps manually."
      exit 1
      ;;
  esac
}

install_packages

echo ">>> artifact directory"
sudo mkdir -p /var/lib/avatar/jobs
sudo chown root:root /var/lib/avatar/jobs
sudo chmod 755 /var/lib/avatar/jobs

echo ">>> application directory + clone"
sudo mkdir -p "$(dirname "$APP_DIR")"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$GIT_REPO" "$APP_DIR"
else
  echo "Repo already present at $APP_DIR — skipping clone"
fi

cd "$APP_DIR"

echo ">>> Python venv + install"
PY="python3"
if [[ "$OS_ID" == "amzn" ]]; then
  PY="python3.11"
  if ! command -v "$PY" >/dev/null 2>&1; then
    echo "Missing $PY — run: sudo dnf install -y python3.11 python3.11-pip"
    exit 1
  fi
fi
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -U pip
# Coqui (TTS) is required for ElevenLabs fallback (e.g. Hindi if ElevenLabs key is wrong).
# On very small instances set SKIP_COQUI=1 and fix ELEVENLABS_API_KEY instead.
if [[ "${SKIP_COQUI:-0}" == "1" ]]; then
  pip install -e "."
else
  pip install -e ".[coqui]"
fi

echo ""
echo ">>> Bootstrap done (OS=$OS_ID)."
echo "Next (one-time):"
echo "  1) PostgreSQL user+DB — see docs/DEPLOY_EC2.md (paths may differ on Amazon Linux)"
echo "  2) cp .env.example .env && nano .env  (DATABASE_URL, S3_*, API keys, ARTIFACT_ROOT=/var/lib/avatar/jobs)"
echo "  3) alembic upgrade head"
echo "  4) Install systemd + nginx from docs/DEPLOY_EC2.md (Amazon Linux: use dnf paths if needed)"
echo "  5) GitHub Actions deploy: push to main"
