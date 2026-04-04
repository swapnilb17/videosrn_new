# Deploy from your Mac (we cannot SSH from Cursor’s cloud)

Your **`.pem` must stay on your machine**. Run everything below in **Terminal.app** on your Mac (replace `YOURKEY.pem` and paths as needed).

## Why `curl raw.githubusercontent.com` shows **404**

That URL **does not work for private repositories** (GitHub returns 404 without auth). It also 404s if the file was **never pushed** to branch **`main`**, or the path/branch name is wrong.

**Use Option A (scp) or Option B (token) below.**

---

## 1. Key permissions and SSH

```bash
chmod 400 ~/Downloads/YOURKEY.pem
ssh -i ~/Downloads/YOURKEY.pem ec2-user@YOUR_EC2_IP
```

Match **EC2_USER** / **EC2_HOST** to your GitHub Action secrets if you use automated deploy.

---

## 2a. Copy scripts from your Mac (**recommended** for a **private** repo)

On your **Mac**, from the folder where you have the repo (e.g. Cursor project):

```bash
cd /path/to/Avatar_Video_creator   # or Videosrv clone

scp -i ~/Downloads/YOURKEY.pem \
  scripts/setup_github_readonly_deploy_key.sh \
  scripts/bootstrap_ec2.sh \
  ec2-user@YOUR_EC2_IP:/tmp/
```

**On EC2:**

```bash
chmod +x /tmp/setup_github_readonly_deploy_key.sh /tmp/bootstrap_ec2.sh
/tmp/setup_github_readonly_deploy_key.sh
```

Copy the printed **public** key → GitHub **Videosrv** → **Settings** → **Deploy keys** → Add (**read-only**).

Then:

```bash
/tmp/bootstrap_ec2.sh
```

---

## 2b. Download with a **GitHub token** (private repo, no scp)

Create a **fine-grained PAT** (read-only on `Videosrv`) or classic PAT with `repo`. On **EC2**:

```bash
export GH_TOKEN="paste_token_here"   # remove from shell history after: history -d

curl -fsSL \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/swapnilb17/Videosrv/contents/scripts/setup_github_readonly_deploy_key.sh?ref=main" \
  -o /tmp/setup_key.sh

curl -fsSL \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/swapnilb17/Videosrv/contents/scripts/bootstrap_ec2.sh?ref=main" \
  -o /tmp/bootstrap.sh

chmod +x /tmp/setup_key.sh /tmp/bootstrap.sh
```

Then run `/tmp/setup_key.sh`, add deploy key on GitHub, then `/tmp/bootstrap.sh`.

**Do not** leave `GH_TOKEN` in scripts or commit it.

---

## 2c. **Public** repo only — raw URL

If the repo is **public** and `main` contains these files:

```bash
curl -fsSL https://raw.githubusercontent.com/swapnilb17/Videosrv/main/scripts/setup_github_readonly_deploy_key.sh -o /tmp/setup_key.sh
chmod +x /tmp/setup_key.sh && /tmp/setup_key.sh
```

---

## 3. Postgres, `.env`, Alembic, systemd, nginx

Follow [DEPLOY_EC2.md](DEPLOY_EC2.md). On **Amazon Linux**, PostgreSQL service names may differ (e.g. `postgresql15`).

---

## 4. Ongoing deploys

- Push to **`main`** → GitHub **Actions** → **Deploy to EC2**, **or**
- From your Mac:

  ```bash
  ssh -i ~/Downloads/YOURKEY.pem ec2-user@YOUR_EC2_IP \
    'cd /opt/avatar-video-creator && ./scripts/deploy_on_ec2.sh'
  ```

## Security

- Do not commit `.pem` or paste private keys or PATs into chat.
- Restrict **SSH** when you can; GitHub-hosted runners need port **22** reachable from the internet unless you use a self-hosted runner or manual deploy.
