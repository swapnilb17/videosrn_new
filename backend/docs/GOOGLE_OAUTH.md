# Google OAuth (LearnCast sign-in)

When **all four** variables below are set in `.env`, the app enables **Sign in with Google** and **`POST /generate`** requires a signed-in user. If any variable is empty, OAuth stays off and `/generate` behaves as before.

## 1. Google Cloud Console

1. Open [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**.
2. Open your **OAuth 2.0 Client ID** (type **Web application**), or create one.
3. **Authorized JavaScript origins** — add the site origin only (no path), for example:
   - `https://videoai.enablyai.com`
4. **Authorized redirect URIs** — add the **exact** callback URL (must match `.env`):
   - `https://videoai.enablyai.com/auth/google/callback`

You can keep other apps on the **same** client (e.g. `https://app.enablyai.com/auth/google/callback`) by adding **additional** origins and redirect URIs; one Web client supports many.

**HTTPS:** For a public hostname, prefer `https://` origins and redirect URIs. Plain `http://` works only in limited cases (e.g. localhost) and conflicts with **`SESSION_COOKIE_SECURE=true`**.

**Consent screen:** If the project already has an OAuth consent screen and test users / publishing status, you usually only add the new URIs above.

## 2. `.env` on the server (and locally if you test OAuth)

| Variable | Purpose |
|----------|---------|
| `SESSION_SECRET` | Server-only secret that signs the session cookie. Generate once: `openssl rand -hex 32`. Use a different value per environment if you can. |
| `GOOGLE_OAUTH_CLIENT_ID` | From the same Credentials screen. Alias: `GOOGLE_CLIENT_ID`. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Client secret for that client. Alias: `GOOGLE_CLIENT_SECRET`. |
| `GOOGLE_OAUTH_REDIRECT_URI` | Must **match** an authorized redirect URI **exactly**, e.g. `https://videoai.enablyai.com/auth/google/callback`. Alias: `GOOGLE_REDIRECT_URI`. |
| `SESSION_COOKIE_SECURE` | `true` when users use **HTTPS** (recommended). Set `false` only for local HTTP testing. Requires nginx to forward **`X-Forwarded-Proto`** and uvicorn **`--proxy-headers`** when TLS terminates at nginx. |

Example (values are illustrative):

```env
SESSION_SECRET=paste_output_of_openssl_rand_hex_32
GOOGLE_OAUTH_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxxxx
GOOGLE_OAUTH_REDIRECT_URI=https://videoai.enablyai.com/auth/google/callback
SESSION_COOKIE_SECURE=true
```

Keep `.env` mode `600` and **never** commit it. See [.env.example](../.env.example).

## 3. App routes (for Console verification)

| URL | Role |
|-----|------|
| `GET /auth/google/login` | Starts OAuth; redirects to Google. |
| `GET /auth/google/callback` | Google redirects here; must be the URI you registered. |
| `GET /auth/logout` | Clears session. |

When **Google OAuth** and **PostgreSQL + S3** are both enabled, **`GET /media/...`** requires a **signed-in session**. Each job stores the creator’s Google `sub`; only that account can presign/fetch that job’s files (jobs created before this feature may have no `sub` and remain readable by any signed-in user). Run **`alembic upgrade head`** after deploy so the `owner_sub` column exists.

## 4. After changing `.env`

Restart the app (e.g. `sudo systemctl restart avatar-video-creator`).

## 5. Verify

- `GET /health` returns `"google_oauth_enabled": true` when all four core variables are set.
- When signed in, `GET /health` includes `"google_user_email": "you@example.com"` (or similar).
- Open the site → **Sign in with Google** → after success, **Generate video** should work.

## 6. EC2 / nginx

- TLS and nginx: [DEPLOY_EC2.md](DEPLOY_EC2.md) (Ubuntu §7 or [Amazon Linux 2023](DEPLOY_EC2.md#amazon-linux-2023)).
- Uvicorn should run with **`--proxy-headers`** behind nginx so secure cookies and redirects see HTTPS.

## 7. Troubleshooting

| Symptom | Check |
|---------|--------|
| `redirect_uri_mismatch` | Redirect URI in Console and `GOOGLE_OAUTH_REDIRECT_URI` must match **exactly** (scheme, host, path, no extra slash). |
| Sign-in works but session lost / 401 on generate | `SESSION_COOKIE_SECURE=true` with HTTP only, or missing **`--proxy-headers`** / **`X-Forwarded-Proto`** behind nginx. |
| OAuth “not configured” / 404 on `/auth/google/login` | One of the four required variables is empty, or the server was not restarted after editing `.env`. |
| `ModuleNotFoundError: itsdangerous` after deploy | Run `pip install -e .` (or `./scripts/deploy_on_ec2.sh`) so the `itsdangerous` dependency from `pyproject.toml` is installed. |
| systemd: `Ignoring invalid environment assignment '$AWS_PROFILE='` | `.env` must be `KEY=value` lines only — no `$VAR=` syntax. Use `AWS_PROFILE=` or remove the line. |

OAuth is only read at process start for **SessionMiddleware**; changing `.env` always requires a **restart**.
