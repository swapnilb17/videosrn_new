# EC2 host setup (web + PostgreSQL + nginx)

Pick one path below:

- **Ubuntu 22.04 / 24.04 LTS** — sections 1–8.
- **Amazon Linux 2023** — [Amazon Linux 2023](#amazon-linux-2023) (nginx + Let’s Encrypt); PostgreSQL/Python/bootstrap notes in [EC2_FULL_SETUP.md](EC2_FULL_SETUP.md).

Paths match [DEPLOY_WORKFLOW.md](DEPLOY_WORKFLOW.md) and [scripts/deploy_on_ec2.sh](../scripts/deploy_on_ec2.sh); change `APP_DIR` / `SERVICE` if you use different names.

AWS networking and S3 IAM: [AWS_PREREQS.md](AWS_PREREQS.md).

## 1. Packages

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib nginx git ffmpeg python3.12-venv build-essential certbot python3-certbot-nginx
```

Use **Python 3.11+** (`python3.12-venv` or `python3.11-venv` depending on Ubuntu).

## 2. PostgreSQL

```bash
sudo -u postgres psql <<'SQL'
CREATE USER avatar_app WITH PASSWORD 'CHANGE_ME_STRONG';
CREATE DATABASE avatar OWNER avatar_app;
GRANT ALL PRIVILEGES ON DATABASE avatar TO avatar_app;
SQL
```

For SQLAlchemy/Alembic with Postgres 15+ you may need:

```bash
sudo -u postgres psql -d avatar -c 'GRANT ALL ON SCHEMA public TO avatar_app;'
```

Listen on localhost only (default). App URL:

`DATABASE_URL=postgresql+asyncpg://avatar_app:CHANGE_ME_STRONG@127.0.0.1:5432/avatar`

## 3. App user and directories

```bash
sudo useradd --system --home /opt/avatar-video-creator --shell /usr/sbin/nologin avatar || true
sudo mkdir -p /opt/avatar-video-creator /var/lib/avatar/jobs
sudo chown -R avatar:avatar /opt/avatar-video-creator /var/lib/avatar/jobs
```

Deploy user (e.g. `ubuntu`) that runs `git pull` should own or be able to write `/opt/avatar-video-creator`; the **service** runs as `avatar`.

## 4. Clone and venv (as deploy user)

```bash
sudo -u avatar git clone git@github.com:YOUR_ORG/YOUR_REPO.git /opt/avatar-video-creator
# or: sudo -u avatar git clone https://github.com/YOUR_ORG/YOUR_REPO.git ...
cd /opt/avatar-video-creator
sudo -u avatar python3 -m venv .venv
sudo -u avatar .venv/bin/pip install -U pip
sudo -u avatar .venv/bin/pip install -e ".[coqui]"
```

Copy and edit `.env` (mode `600`): API keys, `DATABASE_URL`, `S3_BUCKET`, `S3_REGION`, `ARTIFACT_ROOT=/var/lib/avatar/jobs`, etc. See [.env.example](../.env.example).

## 5. Alembic (migrations)

```bash
cd /opt/avatar-video-creator
sudo -u avatar .venv/bin/alembic upgrade head
```

## 6. systemd

`/etc/systemd/system/avatar-video-creator.service`:

```ini
[Unit]
Description=Avatar Video Creator (FastAPI)
After=network.target postgresql.service

[Service]
Type=simple
User=avatar
Group=avatar
WorkingDirectory=/opt/avatar-video-creator
EnvironmentFile=/opt/avatar-video-creator/.env
ExecStart=/opt/avatar-video-creator/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now avatar-video-creator
sudo systemctl status avatar-video-creator
```

### 6b. Journal log retention (avoid a full disk)

Uvicorn logs go to **systemd-journald** by default. Without limits, the journal can grow until the volume fills.

From the app directory on the server (after clone), run **once**:

```bash
cd /opt/avatar-video-creator
sudo ./scripts/setup_log_retention.sh
```

This installs `deploy/journald-retention.conf` as `/etc/systemd/journald.conf.d/99-avatar-retention.conf` with:

- **MaxRetentionSec=7day** — discard journal entries older than one week
- **SystemMaxUse=512M** — cap total journal size on disk

It also adds `/etc/cron.weekly/avatar-journal-vacuum` as a backup `journalctl --vacuum-time=7d`.

Check usage: `journalctl --disk-usage` · Follow app logs: `journalctl -u avatar-video-creator -f`

**nginx** access/error logs: Ubuntu usually ships `/etc/logrotate.d/nginx` (weekly rotation). If you customized log paths, ensure a matching logrotate snippet.

## 7. nginx

`/etc/nginx/sites-available/avatar-video-creator`:

```nginx
server {
    listen 80;
    server_name your.domain.example;
    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/avatar-video-creator /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

TLS:

```bash
sudo certbot --nginx -d your.domain.example
```

On Ubuntu, the **certbot** package normally installs a **systemd timer** that runs `certbot renew` twice daily; it is **enabled by default**. Confirm with `systemctl list-timers | grep certbot` and `sudo certbot renew --dry-run`.

## 8. Deploy updates

Push from Cursor to GitHub, then on the server:

```bash
cd /opt/avatar-video-creator
./scripts/deploy_on_ec2.sh
```

Or use [GitHub Actions](../.github/workflows/deploy-ec2.yml).

## Smoke test

```bash
curl -sS http://127.0.0.1:8000/health | jq
```

Expect `persistence_enabled: true` and `database_ready: true` when `.env` has DB + S3 configured.

---

## Amazon Linux 2023

Use this when your instance is **Amazon Linux 2023** (`ec2-user`). Nginx keeps vhosts under **`/etc/nginx/conf.d/`** (there is no `sites-available` tree like on Ubuntu).

### Packages

```bash
sudo dnf update -y
sudo dnf install -y nginx certbot python3-certbot-nginx
```

If `dnf install certbot` fails, run `sudo dnf makecache` and retry, or follow [Certbot’s install steps for your OS](https://certbot.eff.org/instructions) (choose **nginx** and **Amazon Linux**).

### nginx site (HTTP first)

Create `/etc/nginx/conf.d/avatar-video-creator.conf` (replace the domain):

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name videoai.enablyai.com;
    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

```bash
sudo nginx -t && sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

**DNS:** `A` (or `AAAA`) record for `videoai.enablyai.com` must point at this instance (or your load balancer). **Security group:** inbound **80** and **443** from the internet for Let’s Encrypt and browsers.

### Let’s Encrypt (Certbot + nginx)

```bash
sudo certbot --nginx -d videoai.enablyai.com
```

Certbot edits the server block for **443** and optional HTTP→HTTPS redirect. Test renewal:

```bash
sudo certbot renew --dry-run
```

The **dnf** Certbot packages on Amazon Linux 2023 usually **enable** automatic renewal out of the box: a **systemd** unit/timer (often `certbot-renew.timer`) runs `certbot renew` periodically. You do not normally need to configure cron yourself.

Confirm it is active:

```bash
systemctl status certbot-renew.timer
systemctl list-timers | grep -i certbot
sudo certbot renew --dry-run
```

If `certbot-renew.timer` is missing, check `rpm -q certbot` and the [Certbot](https://certbot.eff.org/instructions) install path you used; some install methods require adding a cron job manually.

### App behind TLS (Google OAuth / secure cookies)

Full checklist: [GOOGLE_OAUTH.md](GOOGLE_OAUTH.md).

After HTTPS works, set in `.env`:

- `GOOGLE_OAUTH_REDIRECT_URI=https://videoai.enablyai.com/auth/google/callback`
- `SESSION_COOKIE_SECURE=true`

Restart the app. Uvicorn must trust **X-Forwarded-Proto** from nginx so the app sees HTTPS (needed for secure session cookies). Use:

```text
ExecStart=.../uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

in your **systemd** unit (see section 6 above), or the equivalent if you manage the service another way.

### PostgreSQL, Python, ffmpeg on Amazon Linux

PostgreSQL service names, **Python 3.11+**, and a static **ffmpeg** path differ from Ubuntu. Use [EC2_FULL_SETUP.md](EC2_FULL_SETUP.md) and [scripts/bootstrap_ec2.sh](../scripts/bootstrap_ec2.sh) for those pieces, then return here for nginx and Certbot.
