#!/usr/bin/env bash
# Run on EC2 **before** cloning a private GitHub repo (or if git pull asks for auth).
# Generates a read-only SSH key and prints the public key for GitHub → Settings → Deploy keys.
set -euo pipefail

KEY="${GITHUB_DEPLOY_KEY_PATH:-$HOME/.ssh/github_videosrv_readonly}"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ ! -f "$KEY" ]]; then
  ssh-keygen -t ed25519 -f "$KEY" -N "" -C "ec2-videosrv-readonly-$(hostname)"
  chmod 600 "$KEY"
fi

CONFIG="$HOME/.ssh/config"
touch "$CONFIG"
chmod 600 "$CONFIG"
if ! grep -q "Host github.com" "$CONFIG" 2>/dev/null; then
  cat >> "$CONFIG" <<EOF

Host github.com
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
fi

echo ""
echo "=== Add this deploy key to GitHub (read-only) ==="
echo "Repo: https://github.com/swapnilb17/Videosrv → Settings → Deploy keys → Add deploy key"
echo "Title: EC2 $(hostname) readonly"
echo "Paste:"
echo ""
cat "${KEY}.pub"
echo ""
echo "=== Then clone or pull using SSH URL ==="
echo "  git@github.com:swapnilb17/Videosrv.git"
