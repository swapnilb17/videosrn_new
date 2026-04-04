# Full setup: EC2 tools, S3, and automated `git pull` on deploy

**Cursor / AI cannot SSH into your EC2 or use your `.pem`.** Use your Mac Terminal: [SSH_DEPLOY_FROM_YOUR_MAC.md](SSH_DEPLOY_FROM_YOUR_MAC.md).

Follow this once per environment. Cursor pushes to GitHub; **GitHub Actions** SSHs to EC2 and runs [scripts/deploy_on_ec2.sh](../scripts/deploy_on_ec2.sh), which does **`git pull`** (no manual push *to* EC2 — the server only pulls).

---

## Part A — AWS (S3 + IAM)

1. **S3 bucket** (any unique name, same region as EC2 is simplest):
   - S3 → Create bucket → **Block all public access** ON.
   - Note the bucket name and region (e.g. `ap-south-1`).

2. **IAM role for the EC2 instance** (attach as instance profile):
   - Allow `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on `arn:aws:s3:::YOUR_BUCKET/jobs/*`
   - Allow `s3:ListBucket` on the bucket with prefix `jobs/`  
   - Exact JSON: [AWS_PREREQS.md](AWS_PREREQS.md)

3. **Launch / select EC2**: Ubuntu 22.04+ or **Amazon Linux 2023** (user **`ec2-user`**), attach the role above, security group: **22** (your IP or wider if using GitHub-hosted deploy), **80** and **443** (HTTP/HTTPS). On Amazon Linux 2023, **`ffmpeg` is not in default `dnf` repos**; [scripts/bootstrap_ec2.sh](../scripts/bootstrap_ec2.sh) installs a **static** `ffmpeg`/`ffprobe` under `/opt/ffmpeg-static` and symlinks into `/usr/local/bin`. The app requires **Python 3.11+**; the bootstrap script installs **`python3.11`** and builds `.venv` with it (default `python3` on AL2023 is often 3.9 and will fail `pip install -e .`).

---

## Part B — GitHub (read-only deploy key for `git pull` on EC2)

The server must pull **without** your personal password.

**Private repo:** `raw.githubusercontent.com` URLs return **404**. Use **`scp` from your Mac** or a **GitHub API token** — see [SSH_DEPLOY_FROM_YOUR_MAC.md](SSH_DEPLOY_FROM_YOUR_MAC.md) (sections 2a / 2b).

1. SSH to EC2, then either:
   - **scp** [scripts/setup_github_readonly_deploy_key.sh](../scripts/setup_github_readonly_deploy_key.sh) to `/tmp/` and run it, **or**
   - use the token-based `curl` commands in **SSH_DEPLOY_FROM_YOUR_MAC.md**.

2. Copy the printed **public** key.

3. In GitHub: **Videosrv** → **Settings** → **Deploy keys** → **Add deploy key**  
   - Title: `EC2 readonly`  
   - Key: paste `.pub`  
   - **Allow write access**: OFF (read-only is enough for `git pull`)

---

## Part C — Bootstrap EC2 (packages + clone + venv)

Still on EC2 — use **`scp`** or **API + token** for [scripts/bootstrap_ec2.sh](../scripts/bootstrap_ec2.sh) the same way as the setup script ([SSH_DEPLOY_FROM_YOUR_MAC.md](SSH_DEPLOY_FROM_YOUR_MAC.md)). Do **not** rely on `raw.githubusercontent.com` for a private repo.

```bash
chmod +x /tmp/bootstrap_ec2.sh   # or /tmp/bootstrap.sh if you named it that
/tmp/bootstrap_ec2.sh
```

Default: clones to `/opt/avatar-video-creator`. Override:

```bash
APP_DIR=/opt/avatar-video-creator GIT_REPO=git@github.com:swapnilb17/Videosrv.git /tmp/bootstrap_ec2.sh
```

If you already copied the repo tarball instead of clone, create `$APP_DIR`, put files there, then only run the package-install parts manually or adjust the script.

---

## Part D — PostgreSQL, `.env`, migrations, systemd, nginx

Do this on EC2 exactly as in [DEPLOY_EC2.md](DEPLOY_EC2.md):

- Create DB role + database, grant schema.
- `cp .env.example .env` → set at least:
  - `DATABASE_URL=postgresql+asyncpg://...`
  - `S3_BUCKET`, `S3_REGION`, `S3_PREFIX=jobs/`
  - `ARTIFACT_ROOT=/var/lib/avatar/jobs`
  - API keys (OpenAI, ElevenLabs, etc.)
- Optional Google sign-in: [GOOGLE_OAUTH.md](GOOGLE_OAUTH.md)
- `cd /opt/avatar-video-creator && .venv/bin/alembic upgrade head`
- Install **systemd** unit and **nginx** from that doc; **Let’s Encrypt / Certbot** when you have a domain (Ubuntu steps in §7; **Amazon Linux 2023** in [DEPLOY_EC2.md](DEPLOY_EC2.md#amazon-linux-2023)).

Ensure the **systemd** service user can read `.env` and write `ARTIFACT_ROOT` (see DEPLOY_EC2 for `chown` / `acl` if needed).

After the app runs: run **`sudo ./scripts/setup_log_retention.sh`** once so **journald** keeps logs to **~7 days** and caps disk use (see DEPLOY_EC2 §6b).

---

## Part E — GitHub Actions deploy (already configured)

Repository **Secrets** (you said these are set):

- `EC2_SSH_PRIVATE_KEY` — key whose **public** half is in `~/.ssh/authorized_keys` on EC2 for `EC2_USER`
- `EC2_USER`, `EC2_HOST`
- Optional: `EC2_APP_DIR`, `EC2_SYSTEMD_SERVICE`

Workflow [.github/workflows/deploy-ec2.yml](../.github/workflows/deploy-ec2.yml) runs on **push to `main`** and on **workflow_dispatch**. Each run:

1. SSH to EC2  
2. `cd APP_DIR && ./scripts/deploy_on_ec2.sh`  
3. That script: **`git pull --ff-only`**, `pip install -e ".[coqui]"` (unless `SKIP_COQUI=1`), `alembic upgrade head`, `systemctl restart`

So **you never “git push to EC2”** — you push to **GitHub**; the server **pulls** during deploy.

---

## Verify

```bash
curl -sS http://127.0.0.1:8000/health
# or https://your-domain/health
```

After a push to `main`, check **Actions** → latest **Deploy to EC2** run.

---

## Troubleshooting

| Issue | What to check |
|--------|----------------|
| `git pull` fails on EC2 | Deploy key added? `ssh -T git@github.com` should say “successfully authenticated”. |
| Deploy workflow fails SSH | `EC2_SSH_PRIVATE_KEY` matches the key on the instance for `EC2_USER`; security group allows GitHub (or use manual **Run workflow** from a runner that can reach your IP — for strict SG, use VPN or self-hosted runner). |
| S3 errors | Instance profile attached? Bucket name/region in `.env` match IAM policy prefix `jobs/*`. |
| 502 from nginx | `systemctl status avatar-video-creator`, uvicorn on `127.0.0.1:8000`. |

**Note:** GitHub-hosted runners use **dynamic IPs**; locking port 22 to “your IP only” blocks Actions. Options: temporarily open 22 to `0.0.0.0/0` (weak), use a **self-hosted runner** on EC2/VPC, or keep **manual** `./scripts/deploy_on_ec2.sh` over SSH from your laptop.
