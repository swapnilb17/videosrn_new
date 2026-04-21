# Enably Admin Console — Living Context

_Last updated: 2026-04-19 after shipping Credit codes + Activity log. Templates in progress._

This doc is the single source of truth for the admin/observability console
project. Every future session should read this first, then only dive into
code for specifics.

---

## 1. Goal & guardrails

Standalone admin console for Enably with:
1. Active users + activity feed
2. Per-user credit balance
3. Template management (upload trendy images/videos → sync to user dashboard) — **in progress**
4. Credit-code generation UI
5. Payment status

**Hard constraints (do not violate):**
- No impact on the existing `EnablyAI_VGEN` app, now or in future.
- Minimize API calls to the existing app server (60s BFF cache).
- Keep the blast radius of admin code isolated from user-facing code paths.

---

## 2. Architecture (one-page)

```
┌─────────────────────────────┐        private VPC         ┌──────────────────────────────┐
│  Admin EC2 (65.0.170.188)   │  172.31.7.232 → 172.31.44.54 │ FastAPI EC2 (3.108.74.193) │
│                             │ ───────────────────────────▶ │                              │
│  Nginx :80                  │   x-internal-api-key header  │  Nginx :80/:443              │
│   └ Next.js 16.2 standalone │                              │   └ docker compose:          │
│      "enably-admin" (BFF)   │                              │       backend (FastAPI)      │
│      port 3000              │                              │       frontend (Next.js)     │
│                             │                              │       db (Postgres)          │
└─────────────────────────────┘                              └──────────────────────────────┘
       public: admin dashboard                                      public: ai.enablyai.com
       (login-gated)                                                (user-facing app)
```

- **Repos:**
  - `EnablyAI_VGEN` (FastAPI backend + user Next.js) — github.com/swapnilb17/videosrn_new
  - `enably-admin` (Next.js admin BFF + UI) — github.com/swapnilb17/enably-admin
- **Pattern:** BFF. Only the admin Next.js server talks to FastAPI. Browser never sees `INTERNAL_API_SECRET`.
- **Auth chain:** admin login (password → JWT cookie) → Next.js route → FastAPI `/internal/admin/*` guarded by shared `INTERNAL_API_SECRET`.

---

## 3. Infrastructure inventory

### FastAPI EC2 (existing user-facing app)
| Item | Value |
|---|---|
| Public IP | `3.108.74.193` (DNS `ai.enablyai.com`) |
| Private IP | `172.31.44.54` |
| SSH | `ec2-user@3.108.74.193`, key `~/Downloads/EnablyAI_KeyPair_New.pem` |
| App dir | `/home/ec2-user/enably-vgen` |
| Stack | docker compose (backend + frontend + db + nginx) |
| Backend entrypoint | `scripts/docker-entrypoint-backend.sh` runs `alembic upgrade head` on every container start |
| Private-IP binding | `backend` service maps `172.31.44.54:8000:8000` (so admin BFF can reach it without touching public TLS) |

### Admin EC2 (this project)
| Item | Value |
|---|---|
| Public IP | `65.0.170.188` |
| Private IP | `172.31.7.232` |
| SSH | `ec2-user@65.0.170.188`, key `~/Downloads/EnablyAI-Observability.pem` |
| Build dir | `/home/ec2-user/admin-build` (disk-backed; do NOT use `/tmp` — it's a 459MB tmpfs that ENOSPCs during `npm ci`) |
| Release layout | `/srv/enably-admin/releases/<sha>` + symlink `/srv/enably-admin/current` |
| Runtime | Next.js standalone via `systemd` unit `enably-admin.service` (listens 127.0.0.1:3000) |
| Frontend proxy | Nginx → `127.0.0.1:3000`, passes `Host` + `X-Forwarded-Proto` |
| Env file | `/etc/enably-admin.env` (systemd loads `EnvironmentFile=`) |
| Memory | 916 MB RAM, 1 GB swap (needed for `next build` with `NODE_OPTIONS=--max-old-space-size=1024`) |
| Disk | 8 GB root, ~4.8 GB free |
| Password | `0nUP0TPwBChqEoHUCqAJ` (admin login form) |
| IAM role | Admin EC2 instance profile granted S3 access to the main media bucket (prefix `templates/`) |

### Database (on FastAPI EC2)
- Runs in `enably-vgen-db-1` container.
- Admin-added tables: `credit_codes`, `credit_code_redemptions` (+ `content_templates` coming).
- Unchanged existing tables we rely on: `users`, `razorpay_payments`, `credit_ledger`, `credit_promo_redemptions`.

---

## 4. Environment variables

### `/etc/enably-admin.env` (admin EC2)
```
BACKEND_URL=http://172.31.44.54:8000        # private IP, FastAPI
INTERNAL_API_SECRET=<same value as FastAPI>  # piped via ssh from FastAPI EC2
ADMIN_PASSWORD=0nUP0TPwBChqEoHUCqAJ
ADMIN_SESSION_SECRET=<random 32 bytes>
ADMIN_CACHE_TTL=60
```

### FastAPI EC2 `.env` (used by docker compose)
Contains `INTERNAL_API_SECRET`, `POSTGRES_USER`, `POSTGRES_DB`, Razorpay, Google creds, AWS S3 config, etc. **Do not leak — never `cat` it into assistant output.**

Helper pattern for retrieving the secret at runtime (avoids copy-paste):
```bash
ssh -i ~/Downloads/EnablyAI_KeyPair_New.pem ec2-user@3.108.74.193 \
  'cd /home/ec2-user/enably-vgen && sudo docker compose exec -T backend printenv INTERNAL_API_SECRET' | tr -d '\r\n'
```

---

## 5. What's shipped

### 5.1 Backend (`EnablyAI_VGEN`)

**Read-only admin router** in `backend/app/routers/internal_admin.py`, included in `main.py` as:
```python
from app.routers.internal_admin import router as _internal_admin_router
app.include_router(_internal_admin_router)
```
All endpoints guarded by a **local copy** of `_require_internal_api_key` to stay decoupled from `main.py` internals. No other files in `main.py` were modified beyond that single include.

| Endpoint | Purpose | Shipped in commit |
|---|---|---|
| `GET /internal/admin/health` | DB ping | `020b27c` |
| `GET /internal/admin/users` | Paginated users + plan + balance (q filter) | `020b27c` |
| `GET /internal/admin/payments` | Razorpay payments joined with user | `020b27c` |
| `POST /internal/admin/codes` | Generate N credit codes | `84ce3e5` |
| `GET /internal/admin/codes` | List codes with redemption counts | `84ce3e5` |
| `POST /internal/admin/codes/{code}/deactivate` | Soft-disable a code | `84ce3e5` |
| `GET /internal/admin/activity` | Ledger-sourced activity feed (filters: q, reason, kind) | `742754a` |

**New tables (migration `0007_credit_codes`):**
- `credit_codes` — catalog: `id`, `code`, `code_normalized` (unique), `credits_each`, `max_redemptions` (0 = unlimited), `redeemed_count`, `expires_at`, `campaign`, `active`, `created_by`, `created_at`.
- `credit_code_redemptions` — `(code_normalized, user_id)` PK, `credits_amount`, `created_at`.

**Redeem flow extension in `credit_service.py`:**
Order of lookup is now:
1. `credit_codes` table (admin-issued) — new
2. Legacy hardcoded `PROMO_CREDIT_CODES` dict — preserved unchanged
3. `STARTER_REDEEM_CODE` invite — preserved unchanged

Ledger `reason="admin_credit_code"` is emitted on admin-code redeems (shows up in Activity log).

**Activity log design choice:** sourced entirely from the existing `credit_ledger` — no new "audit_events" table, no changes to any emit site in `main.py`/`credit_service.py`/`credit_holds.py`. Known reason→kind/label map lives in `internal_admin.py`:

```
signup_grant                → grant  "Signup credits"
starter_redeem_grant        → grant  "Starter unlocked"
promo_code_grant            → grant  "Legacy promo redeemed"
admin_credit_code           → grant  "Admin code redeemed"
razorpay_starter_purchase   → grant  "Razorpay payment captured"
refund_failed_job           → refund "Refund (failed job)"
refund_veo_failed           → refund "Refund (Veo failed)"
standard_video              → spend  "Standard video"
generate_image              → spend  "Image generated"
veo_image_to_ad             → spend  "Veo image-to-ad"
tts_generate                → spend  "TTS generated"
```
If you add a new `reason=` anywhere, add it to `_REASON_KIND` + `_REASON_LABEL` so the Activity page shows a nice label.

### 5.2 Admin app (`enably-admin`)

Structure:
```
app/
  login/             public password form
  (admin)/           auth-gated (requireSession)
    layout.tsx       sidebar NAV
    page.tsx         Overview (health + refresh)
    users/           paginated users table + search
    activity/        ledger-sourced feed
    payments/        Razorpay list
    codes/           generate + list + deactivate
    templates/       in progress
  api/admin/
    login/           POST → set session cookie
    logout/          POST → clear cookie
    health/          proxied backend health
    refresh/         POST → bust all caches (revalidateTag for TAG.*)
lib/
  env.ts             lazy Proxy-based env validation
  admin-api.ts       BFF: all /internal/admin/* calls here
  admin-auth.ts      JWT helpers (jose)
  public-url.ts      honours X-Forwarded-Host for redirects behind Nginx
proxy.ts             auth middleware (was middleware.ts pre-Next-16)
```

**Cache strategy:** every read helper in `admin-api.ts` uses `unstable_cache` with `revalidate: 60s` and a tag (`TAG.health/users/payments/codes/activity/templates`). Writes call `revalidateTag(tag, "max")`. The Refresh button on Overview calls `refreshAll()` which busts every tag.

**Crucial gotcha:** Server Actions in Next.js 16 **cannot** be driven by raw curl — they need the framework's `Next-Action` header + client bundle. If you see `Error: Failed to find Server Action` in `journalctl -u enably-admin`, it's almost certainly you (or a test script) trying to curl a form action. Browser flow works; test via the real UI or direct backend curl.

---

## 6. Deployment recipes

### 6.1 FastAPI EC2 — pick up backend changes
```bash
ssh -i ~/Downloads/EnablyAI_KeyPair_New.pem ec2-user@3.108.74.193
cd /home/ec2-user/enably-vgen
git fetch --quiet origin main && git reset --hard origin/main
sudo docker compose up -d --build backend    # alembic auto-runs; ~2s user-visible downtime
sudo docker compose logs --tail=20 backend   # confirm "Migrations complete" + Uvicorn ready
```

Quick-check public app is unharmed after every deploy:
```bash
curl -sS https://ai.enablyai.com/health | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])"
```

### 6.2 Admin EC2 — ship a new admin release
```bash
ssh -i ~/Downloads/EnablyAI-Observability.pem ec2-user@65.0.170.188
cd /home/ec2-user/admin-build
git fetch --quiet origin main && git reset --hard origin/main
SHA=$(git rev-parse --short HEAD)
export NODE_OPTIONS="--max-old-space-size=1024"
export NEXT_TELEMETRY_DISABLED=1
npm ci --no-audit --no-fund --prefer-offline
npx --no-install next build

REL=/srv/enably-admin/releases/$SHA
sudo mkdir -p $REL
sudo rsync -a --delete .next/standalone/ $REL/
sudo mkdir -p $REL/.next
sudo rsync -a .next/static/  $REL/.next/static/
sudo rsync -a public/        $REL/public/ 2>/dev/null || true
sudo chown -R ec2-user:ec2-user $REL
sudo ln -sfn $REL /srv/enably-admin/current
sudo systemctl restart enably-admin
systemctl is-active enably-admin
```

### 6.3 Smoke tests (post-deploy)
Backend (from FastAPI EC2):
```bash
K=$(sudo docker compose exec -T backend printenv INTERNAL_API_SECRET | tr -d '\r\n')
B=http://172.31.44.54:8000
curl -fsS -H "x-internal-api-key: $K" "$B/internal/admin/health"
curl -fsS -H "x-internal-api-key: $K" "$B/internal/admin/activity?page_size=3" | python3 -m json.tool | head -40
```

Admin dashboard (from anywhere):
```bash
JAR=$(mktemp)
curl -sS -c "$JAR" -o /dev/null -X POST http://65.0.170.188/api/admin/login --data-urlencode "password=0nUP0TPwBChqEoHUCqAJ"
curl -sS -b "$JAR" -o /dev/null -w "%{http_code}\n" http://65.0.170.188/activity    # expect 200
curl -sS -b "$JAR" -o /dev/null -w "%{http_code}\n" http://65.0.170.188/codes       # expect 200
rm -f "$JAR"
```

---

## 7. Pending work

### 7.1 Templates ✅ shipped 2026-04-19

Backend (`EnablyAI_VGEN`, commits `908f42d` + `9cc45c3`):
- New table `content_templates` (migration `0008_content_templates`).
- `internal_admin.py` extended with `POST /internal/admin/templates/upload`,
  `GET /internal/admin/templates`, `PATCH /internal/admin/templates/{id}`,
  `POST /internal/admin/templates/{id}/publish`, `DELETE /internal/admin/templates/{id}`.
- New router `templates_public.py` exposes `GET /api/templates/feed`
  (unauthenticated, returns published templates with short-lived presigned
  GET URLs). Wired into `main.py` via a single `app.include_router(...)`.
- File caps: 10 MB images, 50 MB videos. Allowed MIME types are
  `image/{png,jpeg,webp,gif}` + `video/{mp4,webm,quicktime}`.

Admin app (`enably-admin`, commit `11b0aa0`):
- `lib/admin-api.ts` adds `listTemplates`, `uploadTemplate`,
  `updateTemplate`, `toggleTemplatePublish`, `deleteTemplate`.
- `/templates` page: upload form + gallery grid with inline preview, publish
  toggle, delete.
- `next.config.ts`: `experimental.serverActions.bodySizeLimit = "55mb"`.
- Nginx on admin EC2: `client_max_body_size 60m;` (was 25m).

User dashboard (`EnablyAI_VGEN`, commit `9cc45c3`):
- New `/dashboard/templates` route + `Sparkles` sidebar entry.
- Client-side gallery (kind filter + search) backed by `/api/templates/feed`.
- Hover-to-play video previews; lazy-loaded image previews.
- No nginx changes needed — `/api/*` already proxies to FastAPI.

Storage:
- Bucket: existing `videosrv` in `ap-south-1`.
- Prefix: `templates/`.
- Object key layout: `templates/<uuid>.<ext>`.
- IAM: FastAPI EC2 role `ec2-learncast-s3` was extended with inline policy
  **`videosrv-templates-write`** granting `s3:PutObject`, `s3:GetObject`,
  `s3:DeleteObject` on `arn:aws:s3:::videosrv/templates/*`. Without this
  policy the upload endpoint returns 502 (botocore `AccessDenied`).

### 7.2 Backlog / nice-to-haves
- Expose per-user ledger drilldown (`/users/<id>/activity`). Easy: reuse `listActivity` with `q=<email>`.
- Export CSV from Activity + Payments pages.
- HTTPS + proper domain (e.g. `admin.enablyai.com`) + Certbot on admin EC2.
- Rate-limit admin login (currently just password + JWT).
- Gate production deploys via GitHub Actions `deploy.yml` (workflow exists but requires setting `ADMIN_EC2_HOST/USER/SSH_KEY` secrets; steps are correctly gated on secret presence).

---

## 8. Commit timeline (for archaeology)

| Repo | Commit | Message |
|---|---|---|
| EnablyAI_VGEN | `020b27c` | Add read-only /internal/admin/* routes for observability console |
| EnablyAI_VGEN | `84ce3e5` | admin: db-backed credit codes (catalog + redeem path) |
| EnablyAI_VGEN | `742754a` | admin: add /internal/admin/activity feed sourced from credit_ledger |
| EnablyAI_VGEN | `908f42d` | admin: content templates (upload + publish + public feed) |
| EnablyAI_VGEN | `9cc45c3` | dashboard: Templates gallery backed by /api/templates/feed |
| enably-admin  | `1f6c8f9` | Use X-Forwarded-Host for login/logout redirects |
| enably-admin  | `a7ea447` | codes: list + deactivate UI, show generated codes once |
| enably-admin  | `784a3cc` | activity: new Activity log page sourced from credit ledger |
| enably-admin  | `11b0aa0` | templates: full CRUD UI backed by /internal/admin/templates |

---

## 9. Known gotchas (hard-won)

1. **`/tmp` is a 459 MB tmpfs on admin EC2.** Any `npm ci` there ENOSPCs and truncates `package.json`. Always build in `/home/ec2-user/admin-build`.
2. **Memory is tight (916 MB).** Always `NODE_OPTIONS=--max-old-space-size=1024` + ensure swap is on (`free -m` should show ~1 GB swap).
3. **Next.js behind Nginx generates `http://0.0.0.0:3000/…` redirects by default.** Fixed by `lib/public-url.ts` which reads `X-Forwarded-Host` + `X-Forwarded-Proto`. Any new route that does `NextResponse.redirect()` must use the `publicUrl()` helper.
4. **Next.js 16 deprecations:** `middleware.ts` → `proxy.ts`, `revalidateTag(tag)` now needs a second argument (`"max"`).
5. **Environment variables are validated lazily** via a `Proxy` in `lib/env.ts`. This is why `next build` in CI works without all secrets — but evaluation at request time must stay inside route handlers / Server Components (which is why all `(admin)` pages export `dynamic = "force-dynamic"`).
6. **`docker-compose.yml` on FastAPI EC2:** the `ports: "172.31.44.54:8000:8000"` mapping on the `backend` service is **load-bearing** for admin connectivity. If you ever edit `docker-compose.yml`, preserve this stanza inside the existing `backend:` block (don't append a duplicate `backend:` at the end — that caused an outage once; see transcript).
7. **BFF cache TTL is 60s.** After any admin write, the list below the form may lag by up to a minute. Operator can click **Refresh** on Overview to force-invalidate everything instantly.
8. **Templates uploads need THREE body-size bumps.** All of these must be raised in lock-step with the FastAPI cap (`_MAX_VIDEO_BYTES` in `internal_admin.py`, currently 50 MB):
   - `client_max_body_size 60m;` — `/etc/nginx/conf.d/enably-admin.conf` on admin EC2.
   - `experimental.proxyClientMaxBodySize: "55mb"` — `next.config.ts`. This one is easy to miss: `proxy.ts` buffers bodies with a separate 10 MB default (distinct from the Server Action cap). Uploads > 10 MB silently truncate and surface as "Unexpected end of form" / the generic "server error" splash.
   - `experimental.serverActions.bodySizeLimit: "55mb"` — `next.config.ts`.
9. **FastAPI EC2 IAM role `ec2-learncast-s3`** must include the inline policy `videosrv-templates-write` (PutObject/GetObject/DeleteObject on `arn:aws:s3:::videosrv/templates/*`). Without it template upload returns 502 with `AccessDenied`.

---

## 10. Quick-start for a future session

"I'm continuing work on the Enably admin console. Read
`backend/docs/ADMIN_CONSOLE_CONTEXT.md`. The next task is: <task>."

That file covers architecture, infra, envs, all shipped endpoints, all
known gotchas, and the exact deploy commands. The only things not in
this doc are secret values and the full source — both of which live in
the repos linked above.
