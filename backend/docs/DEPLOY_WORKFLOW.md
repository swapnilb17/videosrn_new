# Deploy from Cursor to EC2 (“ship this change to my infra”)

You develop in **Cursor** on your laptop; the server only needs a **fast, repeatable update** after you push code. You do **not** need to re-edit files manually on EC2.

Use your **GitHub** repo as the single source of truth: Cursor pushes there; EC2 `git pull`s the same `origin`.

## Recommended loop

1. **Cursor** — commit and `git push origin main` (or open a PR and merge to `main`).
2. **Deploy** — either SSH and run [scripts/deploy_on_ec2.sh](../scripts/deploy_on_ec2.sh), or use **GitHub Actions** ([.github/workflows/deploy-ec2.yml](../.github/workflows/deploy-ec2.yml)) so a push to `main` deploys automatically.

```text
Cursor  →  git push origin main  →  GitHub  →  (Actions SSH)  →  EC2: deploy_on_ec2.sh
                              or  →  you SSH and run deploy_on_ec2.sh
```

## One-time setup on EC2

1. **End-to-end first time:** [EC2_FULL_SETUP.md](EC2_FULL_SETUP.md) (S3, IAM, deploy key, bootstrap, then [DEPLOY_EC2.md](DEPLOY_EC2.md) for Postgres, nginx, systemd, `.env`). AWS reference: [AWS_PREREQS.md](AWS_PREREQS.md).
2. Clone **your GitHub repo** (same URL you use from Cursor). For a **private** repo use a [fine-grained PAT](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) or an [SSH deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys) — never commit tokens.

   ```bash
   sudo mkdir -p /opt/avatar-video-creator
   sudo chown "$USER:$USER" /opt/avatar-video-creator
   git clone git@github.com:YOUR_ORG/YOUR_REPO.git /opt/avatar-video-creator
   # or: git clone https://github.com/YOUR_ORG/YOUR_REPO.git
   cd /opt/avatar-video-creator
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[coqui]"
   cp .env.example .env   # then edit .env (secrets, DATABASE_URL, S3_*, ARTIFACT_ROOT)
   alembic upgrade head
   ```

3. Install the **systemd** unit (example name `avatar-video-creator`) so the app restarts cleanly. Point `WorkingDirectory` at `/opt/avatar-video-creator` and run uvicorn from `.venv`.

4. Make the deploy script executable:

   ```bash
   chmod +x /opt/avatar-video-creator/scripts/deploy_on_ec2.sh
   ```

Your **`.env` on EC2** is local to the server and is **not** replaced by `git pull` (keep it out of git). Secrets and `DATABASE_URL` / S3 settings stay put across deploys. Optional **Google OAuth**: [GOOGLE_OAUTH.md](GOOGLE_OAUTH.md).

## Every deploy (after pushing from Cursor)

SSH to the instance, then:

```bash
cd /opt/avatar-video-creator
./scripts/deploy_on_ec2.sh
```

Optional environment overrides:

| Variable        | Default                    | Meaning                          |
|----------------|----------------------------|----------------------------------|
| `APP_DIR`      | `/opt/avatar-video-creator`| Repo path on server              |
| `VENV`         | `$APP_DIR/.venv`           | Virtualenv path                  |
| `SERVICE`      | `avatar-video-creator`     | `systemctl restart` target     |
| `SKIP_COQUI`   | `0`                        | Set to `1` to skip `pip install .[coqui]` (not recommended for Hindi fallback) |
| `SKIP_ALEMBIC` | `0`                        | Set to `1` to skip DB migrations   |

Example:

```bash
SERVICE=my-app ./scripts/deploy_on_ec2.sh
```

## GitHub Actions

- **CI** — [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs **pytest** on every push/PR to `main` (no secrets).
- **Deploy to EC2** — [.github/workflows/deploy-ec2.yml](../.github/workflows/deploy-ec2.yml) runs on **push to `main`** and on **Run workflow**. It SSHs to EC2 and runs `scripts/deploy_on_ec2.sh` (**`git pull`**, pip, Alembic, systemd restart). If this job fails, check [EC2_FULL_SETUP.md](EC2_FULL_SETUP.md) (secrets, deploy key, security group port 22).

Add these **repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Example | Purpose |
|--------|---------|---------|
| `EC2_SSH_PRIVATE_KEY` | PEM for a key whose **public** key is in `~/.ssh/authorized_keys` on EC2 | GitHub runner authenticates as your deploy user |
| `EC2_USER` | `ubuntu` | SSH login user |
| `EC2_HOST` | `ec2-…amazonaws.com` or Elastic IP | Server hostname |
| `EC2_APP_DIR` | *(optional)* `/opt/avatar-video-creator` | Repo path on server (default if omitted) |
| `EC2_SYSTEMD_SERVICE` | *(optional)* `avatar-video-creator` | systemd unit name (default if omitted) |

The workflow uses `ssh-keyscan` so the runner trusts your host key on first connect. Restrict the deploy SSH key to that one user and disable shell features you do not need if you want tighter security.

## Optional: develop on the box with Cursor

You can use **Cursor Remote SSH** and open `/opt/avatar-video-creator` on EC2 directly. You still should **commit and push** from there to your remote so your laptop and server stay in sync; the deploy script remains useful when you work only on the laptop.

## Checklist after deploy

- `curl -sS https://your-domain/health | jq` — includes `database_ready` when persistence is on.
- Hit the UI and run one short `/generate` if you changed the pipeline.
